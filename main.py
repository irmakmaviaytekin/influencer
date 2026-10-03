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
"""
import html
import sys
import time
import traceback
from datetime import datetime

import anthropic

import config
import export_report
from scraper import scrape_profile
from analyzer import (
    detect_brand_deals, detect_content, detect_competitor,
    CONTENT_CATEGORIES,
)

CAT_LABELS = {
    "drinking": "Drinking",
    "smoking": "Smoking",
    "partying": "Partying",
    "gambling": "Gambling",
    "swearing": "Swearing",
}
# Badge colors per category.
CAT_COLORS = {
    "drinking": "#c0392b",
    "smoking": "#8e44ad",
    "partying": "#d35400",
    "gambling": "#16704a",
    "swearing": "#2c3e50",
}

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
    return {b.lower() for b in load_list(config.COMPETITOR_BRANDS_FILE)}


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
def text_pass(username: str, competitors: set[str]) -> dict:
    posts = scrape_profile(username)
    self_handle = username.lower()

    deal_details = []
    all_brands = set()
    reject_reason = None
    video_posts = []

    for post in posts:
        deal = detect_brand_deals(post)
        if deal["is_deal"]:
            brands = [b for b in deal["brands"] if b.lower() != self_handle]
            all_brands.update(brands)
            deal_details.append({"url": post["url"], "brands": brands,
                                 "signals": deal["signals"]})

        if reject_reason is None:
            post_brands = {b.lower() for b in deal["brands"]}
            comp = detect_competitor(post.get("caption", ""), post_brands, competitors)
            if comp:
                reject_reason = f'mentions competitor "{comp}"'

        if post.get("video_url"):
            video_posts.append(post)

    if config.MAX_VIDEOS_PER_PROFILE is not None:
        video_posts = video_posts[:config.MAX_VIDEOS_PER_PROFILE]

    return {
        "username": username,
        "posts_analyzed": len(posts),
        "deal_count": len(deal_details),
        "brands": sorted(all_brands),
        "deal_details": deal_details,
        "rejected": reject_reason is not None,
        "reject_reason": reject_reason,
        "vision_run": False,
        "vision_error": None,
        "video_count": len(video_posts),
        "vision_failed_count": 0,
        "cat_counts": {c: 0 for c in CONTENT_CATEGORIES},
        "flagged_video_count": 0,
        "flag_details": [],
        "_video_posts": video_posts,
    }


def failed_row(username: str, reason: str) -> dict:
    return {
        "username": username, "posts_analyzed": 0, "deal_count": 0,
        "brands": [], "deal_details": [], "rejected": True, "reject_reason": reason,
        "vision_run": False, "vision_error": None, "video_count": 0, "vision_failed_count": 0,
        "cat_counts": {c: 0 for c in CONTENT_CATEGORIES},
        "flagged_video_count": 0, "flag_details": [], "_video_posts": [],
    }


# ---------------------------------------------------------------------------
# Vision pass
# ---------------------------------------------------------------------------
def vision_pass(row: dict, client: anthropic.Anthropic) -> None:
    video_posts = row.get("_video_posts", [])
    cat_counts = {c: 0 for c in CONTENT_CATEGORIES}
    flag_details = []
    failed = 0

    for post in video_posts:
        try:
            result = detect_content(post, client)
        except Exception:  # noqa: BLE001 - one bad video must not sink the profile
            failed += 1
            continue
        if result["error"]:
            failed += 1
            continue
        content = result["categories"]
        hits = [c for c in CONTENT_CATEGORIES if content[c]["present"]]
        if hits:
            for c in hits:
                cat_counts[c] += 1
            flag_details.append({
                "url": post["url"],
                "hits": hits,
                "evidence": {c: content[c]["evidence"] for c in hits},
            })

    row["cat_counts"] = cat_counts
    row["flagged_video_count"] = len(flag_details)
    row["flag_details"] = flag_details
    row["vision_run"] = True
    row["vision_failed_count"] = failed


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------
def _status(r: dict) -> str:
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
    elif status == "error":
        banner = (f'<p class="status-banner error">Vision pass failed — '
                  f'{html.escape(r["vision_error"])}</p>')
    elif status == "pending":
        banner = '<p class="status-banner pending">Vision pass pending…</p>'
    elif status == "reviewed" and r.get("vision_failed_count"):
        banner = (f'<p class="status-banner error">⚠ {r["vision_failed_count"]} of '
                  f'{r.get("video_count", r["vision_failed_count"])} videos could not be '
                  f'downloaded/analyzed (expired link or error) — category counts below are '
                  f'incomplete, not a clean result. Delete cache/{u}.json and re-run for a '
                  f'fresh scrape.</p>')
    else:
        banner = ""

    flagged_stat_val = str(r["flagged_video_count"]) if status == "reviewed" else "—"
    counts_row = "".join(
        f'<div class="stat"><span class="num" style="color:{CAT_COLORS[c]}">'
        f'{r["cat_counts"][c] if status == "reviewed" else "—"}</span>'
        f'<span class="lbl">{CAT_LABELS[c]}</span></div>'
        for c in CONTENT_CATEGORIES)

    # Flagged videos table.
    if status == "rejected":
        flags_html = '<p class="none">Not analyzed — auto-rejected before the vision pass.</p>'
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
        flags_html = '<p class="none">No flagged videos.</p>'

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
          <span class="lbl">posts (12mo)</span></div>
        <div class="stat"><span class="num">{r['deal_count']}</span>
          <span class="lbl">brand deals</span></div>
        <div class="stat"><span class="num">{flagged_stat_val}</span>
          <span class="lbl">flagged videos</span></div>
      </div>
      <div class="catstats">{counts_row}</div>
      <h3>Flagged videos</h3>
      {flags_html}
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
            f'<td>{len(r["brands"])}</td><td>{r["flagged_video_count"]}</td>{cells}</tr>')


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
    <thead><tr><th>Influencer</th><th>Status</th><th>Posts</th><th>Deals</th><th>Brands</th>
      <th>Flagged</th>{cat_ths}</tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  {cards}

  <p class="note">
    Flags come from an AI vision model reviewing {config.FRAMES_PER_VIDEO} sampled
    frames per video. They indicate content <em>worth reviewing</em>, not verified
    fact — check the reasoning and the linked post. "Swearing" only detects profanity
    visible in on-screen text, not spoken audio. "Rejected" profiles mentioned a
    competitor brand in a caption/mention and never reached the vision pass — their
    category counts are 0 because they were never analyzed.
  </p>
</div></body></html>"""

    config.OUTPUT_HTML.write_text(doc, encoding="utf-8")


def export_current_report():
    """Re-derive influencer_report.csv/.xlsx from the HTML just written."""
    text = config.OUTPUT_HTML.read_text(encoding="utf-8")
    summary, flagged_videos, brand_deals = export_report.parse_report(text)
    export_report.write_csv(summary, config.ROOT / "influencer_report.csv")
    export_report.write_xlsx(summary, flagged_videos, brand_deals,
                             config.ROOT / "influencer_report.xlsx")


# ---------------------------------------------------------------------------
def main():
    if not config.APIFY_TOKEN or not config.ANTHROPIC_API_KEY:
        sys.exit("Set APIFY_TOKEN and ANTHROPIC_API_KEY in your .env first.")

    profiles = sys.argv[1:] or load_profiles()
    competitors = load_competitors()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # --- Text pass ---
    print(f"--- Text pass: brand deals + competitor screen ({len(profiles)} profiles) ---")
    text_start = time.time()
    rows = []
    for i, username in enumerate(profiles, 1):
        print(f"[{i}/{len(profiles)}] {username} ...", flush=True)
        try:
            row = text_pass(username, competitors)
            if row["rejected"]:
                print(f"    REJECTED: {row['reject_reason']}", flush=True)
            else:
                print(f"    {row['posts_analyzed']} posts | {row['deal_count']} deals | "
                      f"{len(row['_video_posts'])} videos pending vision", flush=True)
            rows.append(row)
        except Exception:  # noqa: BLE001 - keep going if one profile fails
            print(f"  FAILED: {username}")
            traceback.print_exc()
            rows.append(failed_row(username, "scrape/analysis error"))

    text_elapsed = time.time() - text_start
    print(f"\nText pass done in {format_duration(text_elapsed)}.")

    write_report(rows, vision_complete=False)
    export_current_report()
    print(f"Brand-deal report written to {config.OUTPUT_HTML} (+ .csv/.xlsx) — open it now, "
          f"vision pass continues below.\n")

    pending_rows = [r for r in rows if not r["rejected"]]
    pending_videos = sum(len(r["_video_posts"]) for r in pending_rows)
    est_seconds = pending_videos * config.EST_SECONDS_PER_VIDEO
    print(f"Estimated vision-pass time: ~{format_duration(est_seconds)} "
          f"({pending_videos} videos across {len(pending_rows)} profile(s))\n")

    # --- Vision pass ---
    print(f"--- Vision pass: content flagging ---")
    vision_start = time.time()
    for row in pending_rows:
        print(f"[{row['username']}] analyzing {len(row['_video_posts'])} videos ...", flush=True)
        try:
            vision_pass(row, client)
            msg = f"    {row['flagged_video_count']} flagged videos"
            if row["vision_failed_count"]:
                msg += f" | {row['vision_failed_count']} could not be analyzed (download/link error)"
            print(msg, flush=True)
        except Exception as e:  # noqa: BLE001 - keep going if one profile fails
            print(f"  FAILED (vision): {row['username']}")
            traceback.print_exc()
            row["vision_error"] = str(e)

        # Persist after every profile, not just at the end - an interrupted run
        # (crash, kill, network outage) must not lose already-completed analysis.
        write_report(rows, vision_complete=False)
        export_current_report()

    vision_elapsed = time.time() - vision_start
    total_failed_videos = sum(r["vision_failed_count"] for r in pending_rows)
    if total_failed_videos:
        print(f"\n⚠ {total_failed_videos} video(s) across {len(pending_rows)} profile(s) "
              f"failed to download/analyze — commonly expired CDN links from an old cache "
              f"entry. Delete the affected cache/<username>.json file(s) and re-run for a "
              f"fresh scrape. See the report for which profiles are affected.")
    print(f"\nVision pass done in {format_duration(vision_elapsed)} "
          f"(estimated {format_duration(est_seconds)}).")

    for row in rows:
        row.pop("_video_posts", None)
    write_report(rows, vision_complete=True)
    export_current_report()
    print(f"Full report written to {config.OUTPUT_HTML} (+ .csv/.xlsx)")


if __name__ == "__main__":
    main()
