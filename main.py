"""Orchestrator: scrape -> analyze -> Excel report (3 tabs).

Usage:
    python main.py                 # run all profiles in profiles.txt
    python main.py user1 user2     # run only these usernames
"""
import sys
import traceback

import anthropic
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

import config
from scraper import scrape_profile
from analyzer import detect_brand_deals, detect_alcohol

HEAD_FILL = PatternFill("solid", fgColor="222E3C")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def load_profiles() -> list[str]:
    lines = config.PROFILES_FILE.read_text().splitlines()
    return [l.strip().lstrip("@") for l in lines
            if l.strip() and not l.strip().startswith("#")]


def analyze_profile(username: str, client: anthropic.Anthropic) -> dict:
    posts = scrape_profile(username)
    self_handle = username.lower()

    deal_details = []      # one dict per brand-deal post
    alcohol_details = []   # one dict per post where alcohol was detected
    all_brands = set()

    for post in posts:
        deal = detect_brand_deals(post)
        if deal["is_deal"]:
            # Drop the influencer's own handle from the brand list.
            brands = [b for b in deal["brands"] if b.lower() != self_handle]
            all_brands.update(brands)
            deal_details.append({
                "url": post["url"],
                "brands": brands,
                "signals": deal["signals"],
            })

        if post.get("video_url"):
            alc = detect_alcohol(post, client)
            if alc.get("alcohol"):
                alcohol_details.append({
                    "url": post["url"],
                    "confidence": alc.get("confidence"),
                    "evidence": alc.get("evidence", ""),
                })

    return {
        "username": username,
        "posts_analyzed": len(posts),
        "deal_count": len(deal_details),
        "brands": sorted(all_brands),
        "alcohol_count": len(alcohol_details),
        "deal_details": deal_details,
        "alcohol_details": alcohol_details,
    }


def _style_header(ws):
    for cell in ws[1]:
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(vertical="top", wrap_text=True)


def _autosize(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def write_report(rows: list[dict]):
    wb = Workbook()

    # --- Tab 1: Summary (one row per influencer) ---
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Influencer", "Posts analyzed (12mo)", "Brand-deal posts",
               "# Brands", "Brands mentioned", "Alcohol videos"])
    for r in rows:
        ws.append([r["username"], r["posts_analyzed"], r["deal_count"],
                   len(r["brands"]), ", ".join(r["brands"]), r["alcohol_count"]])
    _style_header(ws)
    _autosize(ws, [22, 16, 14, 9, 60, 12])

    # --- Tab 2: Alcohol detail (one row per flagged post) ---
    wa = wb.create_sheet("Alcohol detail")
    wa.append(["Influencer", "Post URL", "Confidence", "Model reasoning"])
    for r in rows:
        for a in r["alcohol_details"]:
            wa.append([r["username"], a["url"], a["confidence"], a["evidence"]])
    _style_header(wa)
    _autosize(wa, [22, 48, 12, 60])

    # --- Tab 3: Brand-deal detail (one row per deal post) ---
    wd = wb.create_sheet("Brand deals detail")
    wd.append(["Influencer", "Post URL", "Brands", "Signals detected"])
    for r in rows:
        for d in r["deal_details"]:
            wd.append([r["username"], d["url"], ", ".join(d["brands"]),
                       ", ".join(d["signals"])])
    _style_header(wd)
    _autosize(wd, [22, 48, 40, 40])

    wb.save(config.OUTPUT_XLSX)
    print(f"\nReport written to {config.OUTPUT_XLSX}")


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
            print(f"    {row['posts_analyzed']} posts | "
                  f"{row['deal_count']} deals | "
                  f"{row['alcohol_count']} alcohol videos", flush=True)
            rows.append(row)
        except Exception:  # noqa: BLE001 - keep going if one profile fails
            print(f"  FAILED: {username}")
            traceback.print_exc()
            rows.append({"username": username, "posts_analyzed": 0,
                         "deal_count": 0, "brands": [], "alcohol_count": 0,
                         "deal_details": [], "alcohol_details": []})

    write_report(rows)


if __name__ == "__main__":
    main()