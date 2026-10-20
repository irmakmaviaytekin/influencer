"""Re-apply a different sensitivity to a finished run - no API calls, no cost.

A run saves every observation the model made (category, level 1-3, reason), so a
brand's sensitivity can change afterwards. This prints which posts would be
flagged under new minimum levels, per profile, and can write a CSV.

Usage:
    python rethreshold.py runs/20261020-175949.json
    python rethreshold.py runs/X.json --min drinking=notable,violence=notable
    python rethreshold.py runs/X.json --min drinking=incidental --csv out.csv

Categories not named in --min use the default (heavy). Level names:
incidental, notable, heavy.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

LEVELS = {"incidental": 1, "notable": 2, "heavy": 3}
NAMES = {v: k for k, v in LEVELS.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("run", help="runs/<timestamp>.json")
    ap.add_argument("--min", default="", help="e.g. drinking=notable,swearing=incidental")
    ap.add_argument("--default", default="heavy", choices=LEVELS, help="minimum for other categories")
    ap.add_argument("--csv", help="write the flagged posts to this CSV")
    args = ap.parse_args()

    mins = {}
    for part in filter(None, (p.strip() for p in args.min.split(","))):
        cat, _, lvl = part.partition("=")
        if lvl.strip() not in LEVELS:
            raise SystemExit(f"'{part}': level must be one of {list(LEVELS)}")
        mins[cat.strip()] = LEVELS[lvl.strip()]

    run = json.loads(Path(args.run).read_text())
    posts = run["per_post"]
    if not any("levels" in p for p in posts):
        raise SystemExit("This run predates saved levels - it only has yes/no flags.")

    flagged = []  # (profile, url, category, level, reason)
    per_profile = defaultdict(lambda: defaultdict(int))
    analyzed = defaultdict(int)
    for p in posts:
        prof = p.get("profile", "?")
        if p.get("error"):
            continue
        analyzed[prof] += 1
        for cat, lvl in (p.get("levels") or {}).items():
            if lvl >= mins.get(cat, LEVELS[args.default]):
                flagged.append((prof, p["url"], cat, lvl, (p.get("observations") or {}).get(cat, "")))
                per_profile[prof][cat] += 1

    used = ", ".join(f"{c}>={NAMES[l]}" for c, l in mins.items()) or "none"
    print(f"Default minimum: {args.default} | overrides: {used}")
    print(f"{len(flagged)} flags on {len({f[1] for f in flagged})} posts, "
          f"{sum(analyzed.values())} posts analyzed in the run\n")
    for prof in sorted(per_profile, key=lambda x: -sum(per_profile[x].values())):
        cats = ", ".join(f"{c} {n}" for c, n in sorted(per_profile[prof].items()))
        print(f"  {prof}: {sum(per_profile[prof].values())} flags ({cats}) of {analyzed[prof]} posts")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Influencer", "Post URL", "Category", "Level", "Reason"])
            for prof, url, cat, lvl, why in flagged:
                w.writerow([prof, url, cat, NAMES[lvl], why])
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
