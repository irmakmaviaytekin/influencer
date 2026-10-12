"""Compare two runs (runs/<timestamp>.json) for time, cost and flags.

Usage:
    python compare_runs.py runs/BEFORE.json runs/AFTER.json [--reference OLD_REPORT.html]

--reference takes an earlier influencer_report.html and checks whether the
posts it flagged are still flagged in both runs (CLAUDE.md: speed changes
must not lose known flags).
"""
import argparse
import json
from pathlib import Path

import export_report


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def flags_by_url(run: dict) -> dict[str, list[str]]:
    return {v["url"]: v["hits"] for v in run["per_video"] if v["hits"]}


def failed_urls(run: dict) -> set[str]:
    return {v["url"] for v in run["per_video"] if v["error"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--reference", help="earlier influencer_report.html to check flags against")
    args = ap.parse_args()
    a, b = load(args.before), load(args.after)

    print(f"{'':22}{'before':>12}{'after':>12}")
    for key, label in [("total_s", "total time (s)"), ("text_pass_s", "text pass (s)"),
                       ("vision_pass_s", "vision pass (s)"), ("videos", "videos"),
                       ("videos_failed", "not analyzed"), ("videos_flagged", "flagged videos"),
                       ("input_tokens", "input tokens"), ("output_tokens", "output tokens"),
                       ("vision_cost_usd", "vision cost ($)")]:
        print(f"{label:22}{a[key]:>12}{b[key]:>12}")
    for key in ("video_workers", "scrape_workers"):
        print(f"{key:22}{a['settings'].get(key, 1):>12}{b['settings'].get(key, 1):>12}")
    if b["vision_pass_s"]:
        print(f"\nvision pass speedup: {a['vision_pass_s'] / b['vision_pass_s']:.1f}x")
    n_a, n_b = a["videos"] - a["videos_failed"], b["videos"] - b["videos_failed"]
    if n_a and n_b:
        print(f"cost per analyzed video: ${a['vision_cost_usd'] / n_a:.4f} -> "
              f"${b['vision_cost_usd'] / n_b:.4f}")
        print(f"mean download per video: {a['sum_download_s'] / a['videos']:.1f}s -> "
              f"{b['sum_download_s'] / b['videos']:.1f}s")

    fa, fb = flags_by_url(a), flags_by_url(b)
    print(f"\nflag differences ({len(set(fa) | set(fb))} posts flagged in either run):")
    same = True
    for url in sorted(set(fa) | set(fb)):
        if fa.get(url) != fb.get(url):
            same = False
            note = " (not analyzed in after)" if url in failed_urls(b) else ""
            note = note or (" (not analyzed in before)" if url in failed_urls(a) else "")
            print(f"  {url}: {fa.get(url, [])} -> {fb.get(url, [])}{note}")
    if same:
        print("  none - identical flags")

    if args.reference:
        _, ref_flags, _ = export_report.parse_report(Path(args.reference).read_text())
        urls_a = {v["url"] for v in a["per_video"]}
        print(f"\nreference flags from {args.reference}:")
        for f in ref_flags:
            url = f["url"]
            if url not in urls_a:
                print(f"  {url} [{f['flags']}]: not in this scrape (outside 12-month window?)")
                continue
            print(f"  {url} [{f['flags']}]: before {fa.get(url, 'not flagged')}, "
                  f"after {fb.get(url, 'not flagged')}")


if __name__ == "__main__":
    main()
