# Influencer audit pipeline

Screens up to 40 Instagram profiles for brand-fit issues before a partnership:
brand deals with other companies, mentions of a competitor, and (via AI vision)
drinking, smoking, partying, gambling, or swearing visible in their videos.
Output is an HTML report plus CSV/XLSX exports.

## How it works

Runs in two passes so the slow/expensive part (vision) only touches profiles
worth analyzing:

1. **Text pass** (fast, no LLM calls) — for each profile:
   - **scraper.py** pulls posts via the Apify Instagram Scraper actor, filters
     to the last 12 months, and caches raw results to `cache/` so re-runs are free.
   - **analyzer.py** scans captions/metadata for `#ad`, "paid partnership"
     labels, sponsor phrases, and `@mentioned`/tagged brand accounts (brand deals).
   - It also checks captions/mentions against `competitor_brands.txt`. A match
     **auto-rejects** the profile — it's shown in the report with the reason,
     but skips the vision pass entirely (no video download, no API spend).
   - The report is written immediately after this pass so you can see brand
     deals and rejections right away, before the vision pass even starts.
2. **Vision pass** (slower, costs API calls) — for every profile that wasn't
   rejected: downloads each video, samples 6 evenly-spaced frames, and asks a
   Claude vision model whether drinking, smoking, partying, gambling, or
   swearing (visible on-screen text only) is present. Content categories are
   decided *only* by this pass — caption keyword matching was tried and
   dropped, since words like "vodka" match harmless captions like "spicy vodka
   pizza" too often to auto-reject on.
3. **main.py** orchestrates both passes, prints elapsed time for the text pass
   plus an estimated time for the vision pass, then writes the final report
   once vision completes.
4. **export_report.py** parses the generated HTML (no re-scrape, no re-run of
   the vision model) into `influencer_report.csv` / `.xlsx`.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with two keys:
- **APIFY_TOKEN** from https://console.apify.com/account/integrations
- **ANTHROPIC_API_KEY** from https://console.anthropic.com/

```
APIFY_TOKEN=...
ANTHROPIC_API_KEY=...
```

`.env` is gitignored — never commit it.

Put your usernames (one per line, up to 40) in `profiles.txt`, and any
competitor brand names/handles (one per line) in `competitor_brands.txt`.
Lines starting with `#` are ignored in both files.

## Run

```bash
python main.py                 # all profiles in profiles.txt
python main.py natgeo nike     # just these two
```

Re-runs reuse cached scrapes, so you only pay Apify once per profile. Delete a
file in `cache/` to force a fresh scrape — this is also the fix if the report
shows videos as "could not be analyzed": Instagram's video CDN links expire
(usually within hours), so a vision pass run against an old cache entry will
fail to download the videos. The report calls this out explicitly per profile
rather than silently reporting it as clean.

Export CSV/XLSX from the last HTML report at any time:

```bash
python export_report.py                 # all profiles -> influencer_report.csv/.xlsx
python export_report.py natgeo nike      # just these two -> influencer_report_selected.csv/.xlsx
```

## Tuning (config.py)

- `MONTHS_LOOKBACK` — how far back to analyze (default 12).
- `FRAMES_PER_VIDEO` — more frames = better recall, higher cost.
- `VISION_MODEL` — any Anthropic vision-capable model.
- `DEAL_HASHTAGS` / `DEAL_PHRASES` — brand-deal signals to match.
- `EST_SECONDS_PER_VIDEO` — used only for the printed time estimate before the
  vision pass; doesn't affect behavior.

## Report status column

Each profile shows one of:
- **Rejected** — mentioned a competitor brand; vision pass never ran.
- **Pending** — text pass done, waiting on the vision pass (only visible if
  you open the report while a run is still in progress).
- **Reviewed** — vision pass completed. If some videos couldn't be
  downloaded/analyzed, the card shows a warning and the CSV/XLSX "Analysis
  gaps" column notes how many — treat those as not-yet-analyzed, not clean.
- **Error** — the vision pass itself failed for the whole profile (e.g. API error).

## Important caveats

- **ToS / legality.** Scraping Instagram is against its Terms of Service. Apify
  runs the scraping off your own IP, but you are still responsible for how you use
  the data. Only public profiles are accessible. Consider whether your use case
  needs consent, especially if results feed decisions about these people.
- **Accuracy.** Vision detection is fully automated with no human review by
  default. Expect some false positives (a wine bottle in the background) and
  false negatives (a can with the label hidden). The report includes the
  flagged post URLs so you can spot-check.
- **Cost.** Roughly Apify scrape (~$0.50–2 per profile depending on post count) +
  one vision call per video for non-rejected profiles. Videos dominate cost; a
  profile with 100 videos = 100 vision calls.
- **Stories/Reels.** The actor returns feed posts and Reels. Stories (24h) are not
  reliably retrievable.
