"""Orchestrator: text pass (fast) -> vision pass (slow) -> HTML report.

The text pass scrapes each profile and screens captions for competitor
brands - no video download, no LLM call. A competitor mention auto-rejects
the profile and skips the vision pass entirely. Content categories
(drinking, smoking, etc.) are never used to auto-reject - caption keyword
matching for those is too unreliable (e.g. "vodka" matching inside "spicy
vodka pizza"), so they're determined exclusively by the vision pass. The
report is written once right after the text pass (brand deals + rejections
visible immediately) and again after the vision pass completes.

Usage:
    python main.py                 # all profiles in profiles.txt
    python main.py user1 user2     # only these usernames
    python main.py --text-only ... # stop after the text pass (shows vision estimate)

Per-job settings live in a job file: python main.py --job quiet-luxury reads
jobs/quiet-luxury.json (creators, lookback, model, categories and their
sensitivity, competitors, review brands - see jobs/example.json). Environment
variables (CATEGORY_SET, MIN_LEVELS, REPORT_NAME, ...) override the file.
"""
import os
import sys

# --job <name|path> must be applied before config is imported (it reads JOB at import).
if "--job" in sys.argv:
    _i = sys.argv.index("--job")
    if _i + 1 >= len(sys.argv):
        sys.exit("--job needs a job name or file, e.g. --job quiet-luxury")
    os.environ["JOB"] = sys.argv[_i + 1]
    del sys.argv[_i:_i + 2]

import html
import json
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import anthropic

import config
import export_report
from scraper import scrape_profile
from analyzer import (
    detect_brand_deals, detect_content, detect_competitor, detect_review_brand, media_kind,
    CONTENT_CATEGORIES,
)

CAT_LABELS = {k: c["label"] for k, c in config.CONTENT_CATEGORIES.items()}
CAT_COLORS = {k: c["color"] for k, c in config.CONTENT_CATEGORIES.items()}

STATUS_LABELS = {"rejected": "Rejected", "pending": "Pending", "reviewed": "Reviewed",
                  "error": "Error"}


def load_list(path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [l.strip().lstrip("@") for l in lines
            if l.strip() and not l.strip().startswith("#")]


def load_profiles() -> list[str]:
    return load_list(config.PROFILES_FILE)


def load_competitors() -> set[str]:
    if config.JOB_COMPETITORS is not None:
        return {b.strip().lstrip("@").lower() for b in config.JOB_COMPETITORS if b.strip()}
    return {b.lower() for b in load_list(config.COMPETITOR_BRANDS_FILE)}


def load_review_brands() -> list[str]:
    if config.JOB_REVIEW_BRANDS is not None:
        return [b.strip().lstrip("@") for b in config.JOB_REVIEW_BRANDS if b.strip()]
    return load_list(config.REVIEW_BRANDS_FILE)


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Text pass
# ---------------------------------------------------------------------------
def text_pass(username: str, competitors: set[str], review_brands: list[str]) -> dict:
    posts = scrape_profile(username)
    self_handle = username.lower()

    deal_details = []
    all_brands = set()
    reject_reason = None
    media_posts = []

    for post in posts:
        deal = detect_brand_deals(post)
        if deal["is_deal"]:
            brands = [b for b in deal["brands"] if b.lower() != self_handle]
            all_brands.update(brands)
            # Deals with a review brand are flagged for a person, never rejected.
            review = detect_review_brand(post.get("caption", ""), brands, review_brands)
            deal_details.append({"url": post["url"], "brands": brands,
                                 "signals": deal["signals"], "review": review})

        if reject_reason is None:
            post_brands = {b.lower() for b in deal["brands"]}
            comp = detect_competitor(post.get("caption", ""), post_brands, competitors)
            if comp:
                reject_reason = f'mentions competitor "{comp}"'

        # Every post with a photo, video or carousel goes to the vision pass.
        kind = media_kind(post)
        if kind and (kind == "video" or not config.VIDEOS_ONLY):
            media_posts.append(post)

    if config.MAX_VISION_POSTS_PER_PROFILE is not None:
        media_posts = media_posts[:config.MAX_VISION_POSTS_PER_PROFILE]

    return {
        "username": username,
        "posts_analyzed": len(posts),
        "deal_count": len(deal_details),
        "brands": sorted(all_brands),
        "deal_details": deal_details,
        "review_deals": [d for d in deal_details if d["review"]],
        "rejected": reject_reason is not None,
        "reject_reason": reject_reason,
        "vision_run": False,
        "vision_error": None,
        "media_count": len(media_posts),
        "vision_failed_count": 0,
        "cat_counts": {c: 0 for c in CONTENT_CATEGORIES},
        "flagged_post_count": 0,
        "flag_details": [],
        "_media_posts": media_posts,
    }


def failed_row(username: str, reason: str) -> dict:
    """Row for a profile that could not be scraped - shown as an error, never as
    rejected or clean."""
    return {
        "username": username, "posts_analyzed": 0, "deal_count": 0, "scrape_error": reason,
        "brands": [], "deal_details": [], "review_deals": [],
        "rejected": False, "reject_reason": None,
        "vision_run": False, "vision_error": None, "media_count": 0, "vision_failed_count": 0,
        "cat_counts": {c: 0 for c in CONTENT_CATEGORIES},
        "flagged_post_count": 0, "flag_details": [], "_media_posts": [],
    }


# ---------------------------------------------------------------------------
# Vision pass
# ---------------------------------------------------------------------------
# Set when the API refuses every call (no credits, bad key): the rest of the
# run skips its videos instead of downloading them just to fail.
STOP = threading.Event()
STOP_REASON: list[str] = []


def short_reason(err: str) -> str:
    """A short, human reason for a post's error, for console and summaries."""
    e = (err or "").lower()
    if "run stopped" in e:
        return "skipped after run stopped"
    if "credit balance" in e:
        return "Anthropic credit balance too low"
    if "authentication" in e or "invalid x-api-key" in e or "permission" in e:
        return "API key rejected"
    if "download" in e:
        return "download failed"
    if "vision error" in e:
        return "vision API error"
    return (err or "unknown")[:60]


def analyze_post(post: dict, client: anthropic.Anthropic) -> dict:
    """Analyze one post. Runs in a worker thread and never raises - any
    failure is returned as `error`, which the report shows as "not analyzed"."""
    start = time.monotonic()
    if STOP.is_set():
        return {"url": post["url"], "error": f"skipped - run stopped: {STOP_REASON[0]}",
                "hits": [], "evidence": {}, "total_s": 0.0}
    try:
        result = detect_content(post, client)
    except Exception as e:  # noqa: BLE001 - one bad post must not sink the profile
        result = {"error": f"unexpected error: {e}", "categories": None, "metrics": {}}
    content = result["categories"]
    if result.get("fatal") and not STOP.is_set():
        STOP_REASON.append(short_reason(result["error"]))
        STOP.set()
    hits = ([] if result["error"]
            else [c for c in CONTENT_CATEGORIES if content[c]["present"]])
    # Everything the model saw is kept (even below the flag threshold) so the
    # sensitivity can be re-applied later without re-analyzing.
    seen = ({} if result["error"]
            else {c: content[c] for c in CONTENT_CATEGORIES if content[c]["level"] > 0})
    return {"url": post["url"], "error": result["error"], "hits": hits,
            "evidence": {c: f"[{config.LEVEL_NAMES[content[c]['level']]}] {content[c]['evidence']}"
                         for c in hits},
            "levels": {c: v["level"] for c, v in seen.items()},
            "observations": {c: v["evidence"] for c, v in seen.items()},
            "total_s": time.monotonic() - start, **result["metrics"]}


def apply_post_results(row: dict, records: list[dict]) -> None:
    """Fold a profile's per-post results (in post order) into its report row."""
    cat_counts = {c: 0 for c in CONTENT_CATEGORIES}
    flag_details = []
    failed = 0

    for rec in records:
        if rec["error"]:
            failed += 1
            continue
        if rec["hits"]:
            for c in rec["hits"]:
                cat_counts[c] += 1
            flag_details.append({"url": rec["url"], "hits": rec["hits"],
                                 "evidence": rec["evidence"]})

    row["cat_counts"] = cat_counts
    row["flagged_post_count"] = len(flag_details)
    row["flag_details"] = flag_details
    row["vision_run"] = True
    row["vision_failed_count"] = failed
    row["_post_metrics"] = records


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------
def _status(r: dict) -> str:
    if r.get("scrape_error"):
        return "error"
    if r["rejected"]:
        return "rejected"
    if r.get("vision_error"):
        return "error"
    if r.get("vision_run"):
        return "reviewed"
    return "pending"


def _badge(cat: str) -> str:
    return (f'<span class="badge" style="background:{CAT_COLORS[cat]}">'
            f'{CAT_LABELS[cat]}</span>')


def _profile_card(r: dict) -> str:
    u = html.escape(r["username"])
    status = _status(r)

    if status == "rejected":
        banner = (f'<p class="status-banner rejected">Auto-rejected — '
                  f'{html.escape(r["reject_reason"])}</p>')
    elif r.get("scrape_error"):
        banner = (f'<p class="status-banner error">Scrape failed — '
                  f'{html.escape(r["scrape_error"])} (check the username)</p>')
    elif status == "error":
        banner = (f'<p class="status-banner error">Vision pass failed — '
                  f'{html.escape(r["vision_error"])}</p>')
    elif status == "pending":
        banner = '<p class="status-banner pending">Vision pass pending…</p>'
    elif status == "reviewed" and r.get("vision_failed_count"):
        banner = (f'<p class="status-banner error">⚠ {r["vision_failed_count"]} of '
                  f'{r.get("media_count", r["vision_failed_count"])} posts could not be '
                  f'downloaded/analyzed (expired link or error) — category counts below are '
                  f'incomplete, not a clean result. Delete cache/{u}.json and re-run for a '
                  f'fresh scrape.</p>')
    else:
        banner = ""

    flagged_stat_val = str(r["flagged_post_count"]) if status == "reviewed" else "—"
    counts_row = "".join(
        f'<div class="stat"><span class="num" style="color:{CAT_COLORS[c]}">'
        f'{r["cat_counts"][c] if status == "reviewed" else "—"}</span>'
        f'<span class="lbl">{CAT_LABELS[c]}</span></div>'
        for c in CONTENT_CATEGORIES)

    # Flagged posts table.
    if status == "rejected":
        flags_html = '<p class="none">Not analyzed — auto-rejected before the vision pass.</p>'
    elif r.get("scrape_error"):
        flags_html = '<p class="none">Not analyzed — the profile could not be scraped.</p>'
    elif status in ("pending", "error"):
        flags_html = '<p class="none">Vision pass not yet complete for this profile.</p>'
    elif r["flag_details"]:
        flag_rows = ""
        for f in r["flag_details"]:
            badges = " ".join(_badge(c) for c in f["hits"])
            ev = "; ".join(f'{CAT_LABELS[c]}: {html.escape(f["evidence"][c])}'
                           for c in f["hits"] if f["evidence"][c])
            url = html.escape(f["url"])
            flag_rows += (
                f'<tr><td>{badges}</td>'
                f'<td class="ev">{html.escape(ev)}</td>'
                f'<td><a href="{url}" target="_blank">view&nbsp;post ↗</a></td></tr>')
        flags_html = (
            '<table class="detail"><thead><tr><th>Flags</th>'
            '<th>Why (model reasoning)</th><th>Link</th></tr></thead>'
            f'<tbody>{flag_rows}</tbody></table>')
    else:
        flags_html = '<p class="none">No flagged posts.</p>'

    # Deals with a review brand (text pass) - flagged for a person to check.
    if r.get("scrape_error"):
        review_html = '<p class="none">Not checked — the profile could not be scraped.</p>'
    elif r["review_deals"]:
        review_rows = "".join(
            f'<tr class="review"><td>{html.escape(d["review"])}</td>'
            f'<td>{html.escape(", ".join(d["brands"]) or "—")}</td>'
            f'<td><a href="{html.escape(d["url"])}" target="_blank">view&nbsp;post ↗</a>'
            f'</td></tr>'
            for d in r["review_deals"])
        review_html = (
            '<table class="detail"><thead><tr><th>Matched</th><th>Brands mentioned</th>'
            f'<th>Link</th></tr></thead><tbody>{review_rows}</tbody></table>')
    else:
        review_html = '<p class="none">None found.</p>'

    # Brand deals (always available - computed in the text pass).
    if r["deal_details"]:
        brand_chips = " ".join(f'<span class="chip">{html.escape(b)}</span>'
                               for b in r["brands"]) or "—"
        deal_links = " · ".join(
            f'<a href="{html.escape(d["url"])}" target="_blank">deal {i+1} ↗</a>'
            for i, d in enumerate(r["deal_details"]))
        deals_html = (f'<div class="brands">{brand_chips}</div>'
                      f'<div class="deallinks">{deal_links}</div>')
    else:
        deals_html = '<p class="none">No brand deals detected.</p>'

    return f"""
    <section class="card">
      <div class="card-head">
        <h2>@{u}</h2>
        <a class="ig" href="https://www.instagram.com/{u}/" target="_blank">
          instagram.com/{u} ↗</a>
      </div>
      {banner}
      <div class="topstats">
        <div class="stat"><span class="num">{r['posts_analyzed']}</span>
          <span class="lbl">posts ({config.MONTHS_LOOKBACK}mo)</span></div>
        <div class="stat"><span class="num">{r['deal_count']}</span>
          <span class="lbl">brand deals</span></div>
        <div class="stat"><span class="num">{len(r['review_deals'])}</span>
          <span class="lbl">deals to review</span></div>
        <div class="stat"><span class="num">{flagged_stat_val}</span>
          <span class="lbl">flagged posts</span></div>
      </div>
      <div class="catstats">{counts_row}</div>
      <h3>Flagged posts</h3>
      {flags_html}
      <h3>Deals to review</h3>
      {review_html}
      <h3>Brand deals</h3>
      {deals_html}
    </section>"""


def _summary_row(r: dict) -> str:
    u = html.escape(r["username"])
    status = _status(r)
    cells = "".join(
        f'<td class="{"hot" if r["cat_counts"][c] else ""}">{r["cat_counts"][c]}</td>'
        for c in CONTENT_CATEGORIES)
    return (f'<tr><td class="uname"><a href="#{u}">@{u}</a></td>'
            f'<td class="status status-{status}">{STATUS_LABELS[status]}</td>'
            f'<td>{r["posts_analyzed"]}</td><td>{r["deal_count"]}</td>'
            f'<td>{len(r["brands"])}</td>'
            f'<td class="{"hot" if r["review_deals"] else ""}">{len(r["review_deals"])}</td>'
            f'<td>{r["flagged_post_count"]}</td>{cells}</tr>')


def _sensitivity_note() -> str:
    """Tell the reader which sensitivity this job used - a flag means 'at least this level'."""
    groups: dict[str, list[str]] = {}
    for key, c in config.CONTENT_CATEGORIES.items():
        groups.setdefault(config.LEVEL_NAMES[config.min_level(key)], []).append(c["label"])
    parts = [f"{', '.join(labels)}: {lvl}" for lvl, labels in groups.items()]
    return ("Sensitivity for this job - a post is flagged only at or above these levels "
            "(incidental &lt; notable &lt; heavy): " + "; ".join(parts) + ". Milder "
            "cases were seen but not flagged. ")


def _text_only_note() -> str:
    labels = [f"<strong>{c['label']}</strong>" for c in config.CONTENT_CATEGORIES.values()
              if c["text_only"]]
    if not labels:
        return ""
    names = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    verb = "is" if len(labels) == 1 else "are"
    return (f"{names} {verb} only checked in captions and on-screen text, "
            f"not spoken audio.")


def write_report(rows: list[dict], vision_complete: bool):
    generated = datetime.now().strftime("%b %d, %Y %H:%M")
    cat_ths = "".join(f'<th>{CAT_LABELS[c]}</th>' for c in CONTENT_CATEGORIES)
    summary_rows = "".join(_summary_row(r) for r in rows)
    cards = "".join(
        f'<a name="{html.escape(r["username"])}"></a>' + _profile_card(r)
        for r in rows)

    if vision_complete:
        phase_note = "Vision pass complete."
    else:
        pending_n = sum(1 for r in rows if not r["rejected"])
        phase_note = (f"Text pass complete — vision pass running for {pending_n} "
                      f"profile(s). Refresh this file once it finishes.")

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Influencer content audit</title>
<style>
  :root {{ --ink:#1a2230; --muted:#6b7280; --line:#e5e9f0; --bg:#f6f8fb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:32px 20px 80px; }}
  header h1 {{ margin:0 0 4px; font-size:26px; }}
  header p {{ margin:0; color:var(--muted); }}
  header p.phase {{ margin-top:4px; font-weight:600; color:#1f3a5f; }}
  h2 {{ margin:0; font-size:20px; }}
  h3 {{ margin:22px 0 8px; font-size:14px; text-transform:uppercase;
    letter-spacing:.04em; color:var(--muted); }}
  table {{ width:100%; border-collapse:collapse; background:#fff; }}
  .summary {{ margin:20px 0 40px; border:1px solid var(--line); border-radius:12px;
    overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
  .summary th, .summary td {{ padding:10px 12px; text-align:center;
    border-bottom:1px solid var(--line); font-size:14px; }}
  .summary th {{ background:#1f3a5f; color:#fff; font-weight:600; }}
  .summary td.uname {{ text-align:left; font-weight:600; }}
  .summary td.hot {{ background:#fce8e6; color:#b02a37; font-weight:700; }}
  .summary tr:hover td {{ background:#f0f4fa; }}
  .summary td.status {{ font-weight:700; border-radius:6px; }}
  .summary td.status-rejected {{ background:#fce8e6; color:#b02a37; }}
  .summary td.status-pending {{ background:#fff8e1; color:#8a6d00; }}
  .summary td.status-reviewed {{ background:#e6f4ea; color:#1e7e34; }}
  .summary td.status-error {{ background:#fde2c8; color:#9a4c00; }}
  a {{ color:#1155cc; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:14px;
    padding:22px 24px; margin:0 0 22px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
  .card-head {{ display:flex; align-items:baseline; justify-content:space-between;
    flex-wrap:wrap; gap:8px; border-bottom:1px solid var(--line); padding-bottom:12px; }}
  .card-head .ig {{ font-size:13px; color:var(--muted); }}
  .status-banner {{ margin:12px 0 0; font-size:14px; }}
  .status-banner.rejected {{ color:#b02a37; font-weight:600; }}
  .status-banner.pending {{ color:#8a6d00; font-weight:600; font-style:italic; }}
  .status-banner.error {{ color:#9a4c00; font-weight:600; }}
  .topstats, .catstats {{ display:flex; gap:26px; flex-wrap:wrap; margin-top:14px; }}
  .catstats {{ margin-top:10px; padding-top:12px; border-top:1px dashed var(--line); }}
  .stat {{ display:flex; flex-direction:column; }}
  .stat .num {{ font-size:22px; font-weight:700; }}
  .stat .lbl {{ font-size:12px; color:var(--muted); }}
  table.detail {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  table.detail th, table.detail td {{ padding:9px 12px; text-align:left;
    border-bottom:1px solid var(--line); font-size:14px; vertical-align:top; }}
  table.detail th {{ background:#f2f5f8; font-weight:600; color:#374151; }}
  td.ev {{ color:#4b5563; }}
  .badge {{ display:inline-block; color:#fff; border-radius:999px;
    padding:2px 10px; font-size:12px; font-weight:600; margin:1px 2px; }}
  .chip {{ display:inline-block; background:#eef2f7; border:1px solid var(--line);
    border-radius:6px; padding:2px 9px; margin:2px; font-size:13px; }}
  .deallinks {{ margin-top:10px; font-size:14px; }}
  .none {{ color:var(--muted); font-style:italic; }}
  .note {{ margin-top:40px; font-size:12.5px; color:var(--muted);
    border-top:1px solid var(--line); padding-top:16px; }}
</style></head>
<body><div class="wrap">
  <header>
    <h1>Influencer content audit</h1>
    <p>{len(rows)} profiles · last {config.MONTHS_LOOKBACK} months · generated {generated}</p>
    <p class="phase">{phase_note}</p>
  </header>

  <table class="summary">
    <thead><tr><th>Influencer</th><th>Status</th><th>Posts</th><th>Deals</th><th>Brands</th><th>Deals to review</th>
      <th>Flagged</th>{cat_ths}</tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  {cards}

  <p class="note">
    Flags come from an AI vision model reviewing each post's images — for a video its
    cover image and {config.FRAMES_PER_VIDEO} sampled frames, for a photo the photo, for
    a carousel every slide ({config.FRAMES_PER_CAROUSEL_VIDEO} frames per video slide) —
    plus the caption. They indicate content <em>worth reviewing</em>, not verified
    fact — check the reasoning and the linked post. {_sensitivity_note()}{_text_only_note()}
    Posts whose images could not be downloaded are counted as not analyzed, not as
    clean. "Deals to review" are brand deals that mention a brand from this job's
    review list (in a tagged/mentioned account or the caption) — flagged for a person
    to check, not rejected. "Rejected" profiles mentioned a competitor brand in a
    caption/mention and never reached the vision pass — their category counts are 0
    because they were never analyzed.
  </p>
</div></body></html>"""

    config.OUTPUT_HTML.write_text(doc, encoding="utf-8")


def export_current_report():
    """Re-derive the .csv/.xlsx next to the HTML report just written."""
    text = config.OUTPUT_HTML.read_text(encoding="utf-8")
    summary, flagged_videos, brand_deals, review_deals = export_report.parse_report(text)
    export_report.write_csv(summary, config.OUTPUT_HTML.with_suffix(".csv"))
    export_report.write_xlsx(summary, flagged_videos, brand_deals, review_deals,
                             config.OUTPUT_HTML.with_suffix(".xlsx"))


def write_run_metrics(rows: list[dict], started: datetime, text_s: float,
                      vision_s: float) -> dict:
    """Save timing, token usage, cost and per-post results to runs/<timestamp>.json."""
    posts = [v for r in rows for v in r.get("_post_metrics", [])]
    input_tokens = sum(v.get("input_tokens", 0) for v in posts)
    output_tokens = sum(v.get("output_tokens", 0) for v in posts)
    cost = (input_tokens * config.PRICE_INPUT_PER_MTOK
            + output_tokens * config.PRICE_OUTPUT_PER_MTOK) / 1_000_000
    summary = {
        "started": started.isoformat(timespec="seconds"),
        "profiles": [r["username"] for r in rows],
        "job": config.job_snapshot(),
        "settings": {"vision_model": config.VISION_MODEL,
                     "frames_per_video": config.FRAMES_PER_VIDEO,
                     "include_video_cover": config.INCLUDE_VIDEO_COVER,
                     "frames_per_carousel_video": config.FRAMES_PER_CAROUSEL_VIDEO,
                     "scrape_workers": config.SCRAPE_WORKERS,
                     "vision_workers": config.VISION_WORKERS,
                     "category_set": config.CATEGORY_SET,
                     "min_levels": {c: config.LEVEL_NAMES[config.min_level(c)]
                                    for c in config.CONTENT_CATEGORIES},
                     "review_brands_file": config.REVIEW_BRANDS_FILE.name,
                     "report": str(config.OUTPUT_HTML)},
        "text_pass_s": round(text_s, 1),
        "vision_pass_s": round(vision_s, 1),
        "total_s": round(text_s + vision_s, 1),
        "posts": len(posts),
        "posts_by_kind": dict(Counter(v.get("kind") for v in posts)),
        "posts_failed": sum(1 for v in posts if v["error"]),
        "posts_flagged": sum(1 for v in posts if v["hits"]),
        "images": sum(v.get("images", 0) for v in posts),
        "sum_media_s": round(sum(v.get("media_s", 0) for v in posts), 1),
        "sum_vision_s": round(sum(v.get("vision_s", 0) for v in posts), 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "vision_cost_usd": round(cost, 4),
        "per_post": posts,
    }
    config.RUNS_DIR.mkdir(exist_ok=True)
    path = config.RUNS_DIR / f"{started.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(summary, indent=2))
    summary["path"] = path
    return summary


# ---------------------------------------------------------------------------
def main():
    if not config.APIFY_TOKEN or not config.ANTHROPIC_API_KEY:
        sys.exit("Set APIFY_TOKEN and ANTHROPIC_API_KEY in your .env first.")

    args = sys.argv[1:]
    text_only = "--text-only" in args
    profiles = ([a.lstrip("@") for a in args if a != "--text-only"]
                or [p.strip().lstrip("@") for p in (config.JOB_PROFILES or []) if p.strip()]
                or load_profiles())
    competitors = load_competitors()
    review_brands = load_review_brands()
    print(f"Job: categories={config.CATEGORY_SET} ({', '.join(CAT_LABELS.values())}) | "
          f"competitors={len(competitors)} | review brands={len(review_brands)} "
          f"({config.REVIEW_BRANDS_FILE.name}) | report={config.OUTPUT_HTML}")
    # Concurrent requests can hit rate limits; the SDK backs off and retries 429s.
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                 max_retries=config.API_MAX_RETRIES)
    run_started = datetime.now()

    # --- Text pass ---
    # Profiles are scraped in parallel; rows keep the input order.
    print(f"--- Text pass: brand deals + competitor screen ({len(profiles)} profiles, "
          f"{config.SCRAPE_WORKERS} at a time) ---")
    text_start = time.time()
    rows: list[dict] = [None] * len(profiles)
    with ThreadPoolExecutor(config.SCRAPE_WORKERS) as pool:
        futures = {pool.submit(text_pass, u, competitors, review_brands): i
                   for i, u in enumerate(profiles)}
        for done, fut in enumerate(as_completed(futures), 1):
            i = futures[fut]
            username = profiles[i]
            try:
                row = fut.result()
                if row["rejected"]:
                    print(f"[{done}/{len(profiles)}] {username}: REJECTED: "
                          f"{row['reject_reason']}", flush=True)
                else:
                    print(f"[{done}/{len(profiles)}] {username}: {row['posts_analyzed']} posts | "
                          f"{row['deal_count']} deals ({len(row['review_deals'])} to review) | "
                          f"{len(row['_media_posts'])} posts pending vision", flush=True)
            except Exception as e:  # noqa: BLE001 - keep going if one profile fails
                print(f"[{done}/{len(profiles)}] {username}: FAILED - {e}")
                traceback.print_exc()
                row = failed_row(username, str(e) or "scrape/analysis error")
            rows[i] = row

    text_elapsed = time.time() - text_start
    print(f"\nText pass done in {format_duration(text_elapsed)}.")

    write_report(rows, vision_complete=False)
    export_current_report()
    print(f"Brand-deal report written to {config.OUTPUT_HTML} (+ .csv/.xlsx) — open it now, "
          f"vision pass continues below.\n")

    failed = [r["username"] for r in rows if r.get("scrape_error")]
    if failed:
        print(f"⚠ {len(failed)} profile(s) could not be scraped - check the spelling: "
              f"{', '.join(failed)}")

    pending_rows = [r for r in rows if not r["rejected"] and not r.get("scrape_error")]
    pending_posts = sum(len(r["_media_posts"]) for r in pending_rows)
    est_seconds = pending_posts * config.EST_SECONDS_PER_POST / config.VISION_WORKERS
    print(f"Estimated vision-pass time: ~{format_duration(est_seconds)} with "
          f"{config.VISION_WORKERS} at a time, up to "
          f"~{format_duration(pending_posts * config.EST_SECONDS_PER_POST)} if downloads "
          f"don't speed up ({pending_posts} posts across {len(pending_rows)} profile(s))\n")
    if text_only:
        print("--text-only: stopping before the vision pass.")
        return

    # --- Vision pass ---
    # All videos from all profiles go through one shared pool of workers
    # (download + frames + vision call each). Profiles are queued in order, so
    # they finish roughly in order; each is written to the report as it finishes.
    print(f"--- Vision pass: content flagging ({config.VISION_WORKERS} posts at a time) ---")
    vision_start = time.time()
    records = [[None] * len(r["_media_posts"]) for r in pending_rows]
    remaining = [len(r["_media_posts"]) for r in pending_rows]

    def finish_profile(p: int) -> None:
        row = pending_rows[p]
        try:
            apply_post_results(row, records[p])
            msg = (f"[{row['username']}] done: {len(records[p])} posts | "
                   f"{row['flagged_post_count']} flagged")
            if row["vision_failed_count"]:
                why = Counter(short_reason(r["error"]) for r in records[p] if r["error"])
                msg += (f" | {row['vision_failed_count']} could not be analyzed ("
                        + ", ".join(f"{n}× {w}" for w, n in why.most_common(2)) + ")")
            print(msg, flush=True)
        except Exception as e:  # noqa: BLE001 - keep going if one profile fails
            print(f"  FAILED (vision): {row['username']}")
            traceback.print_exc()
            row["vision_error"] = str(e)
        # Persist after every profile, not just at the end - an interrupted run
        # (crash, kill, network outage) must not lose already-completed analysis.
        write_report(rows, vision_complete=False)
        export_current_report()

    for p, n in enumerate(remaining):
        if n == 0:
            finish_profile(p)

    announced = False
    pool = ThreadPoolExecutor(config.VISION_WORKERS)
    try:
        futures = {pool.submit(analyze_post, post, client): (p, v)
                   for p, row in enumerate(pending_rows)
                   for v, post in enumerate(row["_media_posts"])}
        for done, fut in enumerate(as_completed(futures), 1):
            p, v = futures[fut]
            records[p][v] = fut.result()  # analyze_post never raises
            records[p][v]["profile"] = pending_rows[p]["username"]
            if STOP.is_set() and not announced:
                announced = True
                print(f"\n!!! STOPPING: {STOP_REASON[0]}. Remaining videos are being skipped "
                      f"(not downloaded, not charged). Fix this, then rerun - finished "
                      f"profiles are already saved.\n", flush=True)
            remaining[p] -= 1
            if remaining[p] == 0:
                finish_profile(p)
            elif done % 10 == 0:
                print(f"    {done}/{len(futures)} posts analyzed", flush=True)
    finally:
        # On Ctrl-C, drop queued videos instead of waiting for all of them.
        pool.shutdown(wait=True, cancel_futures=True)

    vision_elapsed = time.time() - vision_start
    total_failed_posts = sum(r["vision_failed_count"] for r in pending_rows)
    if total_failed_posts:
        why = Counter(short_reason(r["error"]) for row in pending_rows
                      for r in row.get("_post_metrics", []) if r["error"])
        print(f"\n⚠ {total_failed_posts} post(s) across {len(pending_rows)} profile(s) were "
              f"not analyzed: " + ", ".join(f"{n}× {w}" for w, n in why.most_common()) +
              ". Posts with a download failure may need a fresh scrape (delete "
              "cache/<username>.json). See the report for which profiles are affected.")
    print(f"\nVision pass done in {format_duration(vision_elapsed)} "
          f"(estimated {format_duration(est_seconds)}).")

    for row in rows:
        row.pop("_media_posts", None)
    write_report(rows, vision_complete=True)
    export_current_report()
    print(f"Full report written to {config.OUTPUT_HTML} (+ .csv/.xlsx)")

    m = write_run_metrics(rows, run_started, text_elapsed, vision_elapsed)
    print(f"Run metrics: {format_duration(m['total_s'])} total | {m['posts']} posts "
          f"({m['posts_failed']} failed, {m['posts_flagged']} flagged) | "
          f"vision cost ${m['vision_cost_usd']:.2f} -> {m['path']}")
    if STOP.is_set():
        sys.exit(f"Run stopped early: {STOP_REASON[0]}. The report is incomplete - rerun "
                 f"after fixing this.")


if __name__ == "__main__":
    main()
