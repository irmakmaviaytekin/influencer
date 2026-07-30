"""Export influencer_report.html to CSV/Excel.

Parses the generated HTML report (no need to re-scrape or re-run the
vision model) and writes:
  - influencer_report.csv   summary table, one row per profile
  - influencer_report.xlsx  Summary + Flagged Videos + Brand Deals sheets

Usage:
    python export_report.py
"""
import csv
import html
import re

import openpyxl
from openpyxl.styles import Font

import config

CATS = ["Drinking", "Smoking", "Partying", "Gambling", "Swearing"]

SUMMARY_ROW_RE = re.compile(
    r'<tr><td class="uname"><a href="#[^"]*">@([^<]+)</a></td>'
    r'<td>(\d+)</td><td>(\d+)</td><td>(\d+)</td><td>(\d+)</td>'
    r'<td class="[^"]*">(\d+)</td><td class="[^"]*">(\d+)</td>'
    r'<td class="[^"]*">(\d+)</td><td class="[^"]*">(\d+)</td>'
    r'<td class="[^"]*">(\d+)</td></tr>'
)

CARD_RE = re.compile(
    r'<a name="([^"]*)"></a>\s*<section class="card">(.*?)</section>', re.S
)

FLAG_ROW_RE = re.compile(
    r'<tr><td>(.*?)</td><td class="ev">(.*?)</td>'
    r'<td><a href="([^"]*)"[^>]*>view&nbsp;post ↗</a></td></tr>', re.S
)
BADGE_RE = re.compile(r'<span class="badge"[^>]*>([^<]*)</span>')

DEAL_CHIP_RE = re.compile(r'<span class="chip">([^<]*)</span>')
DEAL_LINK_RE = re.compile(r'<a href="([^"]*)"[^>]*>deal \d+ ↗</a>')


def unesc(s: str) -> str:
    # The source data was double-escaped upstream (e.g. "&amp;#x27;"),
    # so unescape repeatedly until it stabilizes.
    prev = None
    while prev != s:
        prev, s = s, html.unescape(s)
    return s.strip()


def parse_report(text: str):
    summary = [
        {
            "username": unesc(m.group(1)),
            "posts": int(m.group(2)),
            "deals": int(m.group(3)),
            "brands": int(m.group(4)),
            "flagged": int(m.group(5)),
            "cats": dict(zip(CATS, map(int, m.groups()[5:]))),
        }
        for m in SUMMARY_ROW_RE.finditer(text)
    ]

    flagged_videos, brand_deals = [], []
    for card_m in CARD_RE.finditer(text):
        username, body = unesc(card_m.group(1)), card_m.group(2)

        for row_m in FLAG_ROW_RE.finditer(body):
            badges_html, evidence, url = row_m.groups()
            flags = ", ".join(BADGE_RE.findall(badges_html))
            flagged_videos.append({
                "username": username,
                "flags": flags,
                "evidence": unesc(evidence),
                "url": url,
            })

        chips = ", ".join(unesc(c) for c in DEAL_CHIP_RE.findall(body))
        links = DEAL_LINK_RE.findall(body)
        for i, url in enumerate(links):
            brand_deals.append({
                "username": username,
                "deal_index": i + 1,
                "brands": chips if i == 0 else "",
                "url": url,
            })

    return summary, flagged_videos, brand_deals


def write_csv(summary, path):
    header = ["Influencer", "Posts analyzed (12mo)", "Brand deals", "Brands mentioned"] + CATS
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in summary:
            w.writerow([r["username"], r["posts"], r["deals"], r["brands"]]
                       + [r["cats"][c] for c in CATS])
    print(f"Wrote {path}")


def write_xlsx(summary, flagged_videos, brand_deals, path):
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Summary"
    header = ["Influencer", "Posts analyzed (12mo)", "Brand deals", "Brands mentioned",
              "Flagged videos"] + CATS
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in summary:
        ws.append([r["username"], r["posts"], r["deals"], r["brands"], r["flagged"]]
                   + [r["cats"][c] for c in CATS])
    ws.freeze_panes = "A2"
    for col, width in zip(ws.columns, [22, 18, 12, 16, 14, 10, 10, 10, 10, 10]):
        ws.column_dimensions[col[0].column_letter].width = width

    ws2 = wb.create_sheet("Flagged Videos")
    ws2.append(["Influencer", "Flags", "Evidence", "Post URL"])
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    for r in flagged_videos:
        ws2.append([r["username"], r["flags"], r["evidence"], r["url"]])
    for col, width in zip(ws2.columns, [22, 20, 60, 40]):
        ws2.column_dimensions[col[0].column_letter].width = width

    ws3 = wb.create_sheet("Brand Deals")
    ws3.append(["Influencer", "Deal #", "Brands mentioned", "Post URL"])
    for cell in ws3[1]:
        cell.font = Font(bold=True)
    for r in brand_deals:
        ws3.append([r["username"], r["deal_index"], r["brands"], r["url"]])
    for col, width in zip(ws3.columns, [22, 8, 50, 40]):
        ws3.column_dimensions[col[0].column_letter].width = width

    wb.save(path)
    print(f"Wrote {path}")


def main():
    text = config.OUTPUT_HTML.read_text(encoding="utf-8")
    summary, flagged_videos, brand_deals = parse_report(text)
    if not summary:
        raise SystemExit("No summary rows found — is influencer_report.html up to date?")

    write_csv(summary, config.ROOT / "influencer_report.csv")
    write_xlsx(summary, flagged_videos, brand_deals, config.ROOT / "influencer_report.xlsx")


if __name__ == "__main__":
    main()
