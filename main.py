"""Orchestrator: scrape -> analyze -> HTML report.

Usage:
    python main.py                 # all profiles in profiles.txt
    python main.py user1 user2     # only these usernames
"""
import html
import sys
import traceback
from datetime import datetime

import anthropic

import config
from scraper import scrape_profile
from analyzer import detect_brand_deals, detect_content, CONTENT_CATEGORIES

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


def load_profiles() -> list[str]:
    lines = config.PROFILES_FILE.read_text().splitlines()
    return [l.strip().lstrip("@") for l in lines
            if l.strip() and not l.strip().startswith("#")]


def analyze_profile(username: str, client: anthropic.Anthropic) -> dict:
    posts = scrape_profile(username)
    self_handle = username.lower()

    deal_details, flag_details = [], []
    all_brands = set()
    cat_counts = {c: 0 for c in CONTENT_CATEGORIES}

    for post in posts:
        deal = detect_brand_deals(post)
        if deal["is_deal"]:
            brands = [b for b in deal["brands"] if b.lower() != self_handle]
            all_brands.update(brands)
            deal_details.append({"url": post["url"], "brands": brands,
                                 "signals": deal["signals"]})

        if post.get("video_url"):
            content = detect_content(post, client)
            hits = [c for c in CONTENT_CATEGORIES if content[c]["present"]]
            if hits:
                for c in hits:
                    cat_counts[c] += 1
                flag_details.append({
                    "url": post["url"],
                    "hits": hits,
                    "evidence": {c: content[c]["evidence"] for c in hits},
                })

    return {
        "username": username,
        "posts_analyzed": len(posts),
        "deal_count": len(deal_details),
        "brands": sorted(all_brands),
        "cat_counts": cat_counts,
        "flagged_video_count": len(flag_details),
        "deal_details": deal_details,
        "flag_details": flag_details,
    }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------
def _badge(cat: str) -> str:
    return (f'<span class="badge" style="background:{CAT_COLORS[cat]}">'
            f'{CAT_LABELS[cat]}</span>')


def _profile_card(r: dict) -> str:
    u = html.escape(r["username"])
    counts_row = "".join(
        f'<div class="stat"><span class="num" style="color:{CAT_COLORS[c]}">'
        f'{r["cat_counts"][c]}</span><span class="lbl">{CAT_LABELS[c]}</span></div>'
        for c in CONTENT_CATEGORIES)

    # Flagged videos table.
    if r["flag_details"]:
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

    # Brand deals.
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
      <div class="topstats">
        <div class="stat"><span class="num">{r['posts_analyzed']}</span>
          <span class="lbl">posts (12mo)</span></div>
        <div class="stat"><span class="num">{r['deal_count']}</span>
          <span class="lbl">brand deals</span></div>
        <div class="stat"><span class="num">{r['flagged_video_count']}</span>
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
    cells = "".join(
        f'<td class="{"hot" if r["cat_counts"][c] else ""}">{r["cat_counts"][c]}</td>'
        for c in CONTENT_CATEGORIES)
    return (f'<tr><td class="uname"><a href="#{u}">@{u}</a></td>'
            f'<td>{r["posts_analyzed"]}</td><td>{r["deal_count"]}</td>'
            f'<td>{len(r["brands"])}</td><td>{r["flagged_video_count"]}</td>{cells}</tr>')


def write_report(rows: list[dict]):
    generated = datetime.now().strftime("%b %d, %Y %H:%M")
    cat_ths = "".join(f'<th>{CAT_LABELS[c]}</th>' for c in CONTENT_CATEGORIES)
    summary_rows = "".join(_summary_row(r) for r in rows)
    cards = "".join(
        f'<a name="{html.escape(r["username"])}"></a>' + _profile_card(r)
        for r in rows)

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
  .summary td.hot {{ /* keep hot color on hover */ }}
  a {{ color:#1155cc; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:14px;
    padding:22px 24px; margin:0 0 22px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
  .card-head {{ display:flex; align-items:baseline; justify-content:space-between;
    flex-wrap:wrap; gap:8px; border-bottom:1px solid var(--line); padding-bottom:12px; }}
  .card-head .ig {{ font-size:13px; color:var(--muted); }}
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
  </header>

  <table class="summary">
    <thead><tr><th>Influencer</th><th>Posts</th><th>Deals</th><th>Brands</th>
      <th>Flagged</th>{cat_ths}</tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  {cards}

  <p class="note">
    Flags come from an AI vision model reviewing {config.FRAMES_PER_VIDEO} sampled
    frames per video. They indicate content <em>worth reviewing</em>, not verified
    fact — check the reasoning and the linked post. "Swearing" only detects profanity
    visible in on-screen text, not spoken audio.
  </p>
</div></body></html>"""

    config.OUTPUT_HTML.write_text(doc, encoding="utf-8")
    print(f"\nReport written to {config.OUTPUT_HTML}")


def main():
    if not config.APIFY_TOKEN or not config.ANTHROPIC_API_KEY:
        sys.exit("Set APIFY_TOKEN and ANTHROPIC_API_KEY in your .env first.")

    profiles = sys.argv[1:] or load_profiles()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    rows = []
    for i, username in enumerate(profiles, 1):
        print(f"[{i}/{len(profiles)}] {username} ...", flush=True)
        try:
            row = analyze_profile(username, client)
            print(f"    {row['posts_analyzed']} posts | {row['deal_count']} deals | "
                  f"{row['flagged_video_count']} flagged videos", flush=True)
            rows.append(row)
        except Exception:  # noqa: BLE001 - keep going if one profile fails
            print(f"  FAILED: {username}")
            traceback.print_exc()
            rows.append({"username": username, "posts_analyzed": 0, "deal_count": 0,
                         "brands": [], "cat_counts": {c: 0 for c in CONTENT_CATEGORIES},
                         "flagged_video_count": 0, "deal_details": [], "flag_details": []})

    write_report(rows)


if __name__ == "__main__":
    main()