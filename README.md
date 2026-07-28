# Influencer audit pipeline

Scans up to 40 Instagram profiles, pulls the last 12 months of posts, flags brand
deals, and uses an AI vision model to detect alcohol consumption in videos. Output
is a single CSV report.

## How it works

1. **scraper.py** pulls public posts for each profile via the Apify Instagram
   Scraper actor, filters to the last 12 months, and caches raw results to `cache/`.
2. **analyzer.py**
   - *Brand deals*: scans captions/metadata for `#ad`, "paid partnership" labels,
     sponsor phrases, and collects `@mentioned`/tagged brand accounts.
   - *Alcohol*: downloads each video, samples 6 evenly-spaced frames, and asks a
     Claude vision model whether alcohol is being consumed or clearly visible.
3. **main.py** runs everything and writes `influencer_report.csv`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then paste in your keys
```

You need two keys:
- **APIFY_TOKEN** from https://console.apify.com/account/integrations
- **ANTHROPIC_API_KEY** from https://console.anthropic.com/

Put your 40 usernames (one per line) in `profiles.txt`.

## Run

```bash
python main.py                 # all profiles in profiles.txt
python main.py natgeo nike     # just these two
```

Re-runs reuse cached scrapes, so you only pay Apify once per profile. Delete a
file in `cache/` to force a fresh scrape.

## Tuning (config.py)

- `MONTHS_LOOKBACK` — how far back to analyze (default 12).
- `FRAMES_PER_VIDEO` — more frames = better recall, higher cost.
- `VISION_MODEL` — any Anthropic vision-capable model.
- `DEAL_HASHTAGS` / `DEAL_PHRASES` — brand-deal signals to match.

## Important caveats

- **ToS / legality.** Scraping Instagram is against its Terms of Service. Apify
  runs the scraping off your own IP, but you are still responsible for how you use
  the data. Only public profiles are accessible. Consider whether your use case
  needs consent, especially if results feed decisions about these people.
- **Accuracy.** Alcohol detection is fully automated with no human review (per your
  choice). Expect some false positives (a wine bottle in the background) and false
  negatives (a can with the label hidden). The report includes the flagged post
  URLs so you can spot-check.
- **Cost.** Roughly Apify scrape (~$0.50–2 per profile depending on post count) +
  one vision call per video. Videos dominate cost; a profile with 100 videos =
  100 vision calls.
- **Stories/Reels.** The actor returns feed posts and Reels. Stories (24h) are not
  reliably retrievable.
