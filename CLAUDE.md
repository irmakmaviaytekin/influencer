# CLAUDE.md — Influencer brand-safety screening tool

## What this is

An internal tool for a talent company that connects influencers with brands. Before a creator is
approved for a brand campaign, the team screens the creator's recent Instagram posts for:

- previous brand partnerships, and any **competitor** of the brand
- swearing (captions and spoken audio)
- the brand's own **deal-breakers** for that campaign (e.g. alcohol, violence, sexual content)

Goal: cut approval time to one or two days by making criteria written, explicit and reusable,
and giving legal/brand a report with evidence so they can sign off without re-watching content.

It is an **internal tool for one company for now**, not a multi-customer product. Users are the
company's own team (influencer managers, legal/brand reviewers). No billing, no customer accounts.
But tag every scan, criteria set and decision with the brand/campaign it belongs to, so a
multi-customer version is possible later without a rewrite.

## Current code (Python)

- `main.py` — runs the pipeline: text pass, then vision pass, writes reports after the text pass,
  after each profile and at the end. Profiles are scraped `SCRAPE_WORKERS` (4) at a time; posts
  from all profiles go through one shared pool, `VISION_WORKERS` (8) at a time. `--text-only`
  stops after the text pass and prints a time estimate.
- `scraper.py` — pulls posts via Apify `apify/instagram-scraper` (max 200 per profile — a busy
  creator can hit that before the lookback window ends), keeps the last `MONTHS_LOOKBACK` months,
  caches to `cache/`. A profile that returns no posts fails (shown as Error) instead of being cached.
- `analyzer.py` — text pass: brand-deal detection (labels, hashtags, phrases, mentions),
  competitor match, review-brand deal flags. Vision pass: downloads what each post shows —
  video: cover image + 6 evenly spaced frames; photo: the photo; carousel: every slide, video
  slides as 3 frames — and sends the labeled images plus caption, paid-partnership label,
  tagged accounts and Instagram's alt-text description to Anthropic.
- `export_report.py` — CSV/XLSX export alongside the HTML report.
- `compare_runs.py` — compares two `runs/` files: time, cost, per-post flag differences, and
  whether an earlier report's flags are still found.
- `config.py` — all settings; keys come from `.env`.
- `jobs/<name>.json` — one brand/campaign's whole setup, run with `python main.py --job <name>`:
  creators, `months_lookback`, `videos_only`, `vision_model`, `default_min_level`, `competitors`,
  `review_brands`, and `categories` (each with a description of what counts / doesn't, optional
  level meanings and its own `min_level`). `jobs/example.json` shows the format; real jobs are
  gitignored (they list real creators). Environment variables still override the file. Every run
  saves the exact criteria it used under `"job"` in `runs/*.json`. Bad job files fail with a
  specific message before anything is scraped or charged. Per job, set by environment variable:
  `CATEGORY_SET` (named category sets: `standard`, `pizza`, `quiet_luxury`), `REVIEW_BRANDS_FILE`,
  `MONTHS_LOOKBACK`, `VISION_MODEL`, `REPORT_NAME`, `VIDEOS_ONLY=1` (skip photos/carousels).
- Inputs: `profiles.txt`, `competitor_brands.txt`, optional review-brands file. Output:
  `<REPORT_NAME>.html/.csv/.xlsx` (default `influencer_report.*`; use `reports/<job>` per job) and
  `runs/<timestamp>.json` (time, tokens, cost, per-post results).

Vision step: categories come from the chosen set in `config.py`, each with the definition sent
to the model; the prompt says to flag when unsure, since a person reviews every flag. Default
model is Sonnet 4.5 (temperature 0); Sonnet 5.5 also works (medium effort; it rejects temperature,
so results can vary slightly between runs). A post whose media can't be downloaded, or that the
model declines, is reported as not analyzed.

Measured: ot.lorena (138 posts, 977 images) takes ~2 min and $3.85 on Sonnet 4.5 (~$0.028 per
post). A 17-profile job (975 videos) took 19 min and $18 on Sonnet 5.5.

## Design decisions (and why) — do not undo without asking

- **Competitor match is the only automatic reject.** It is exact, whole-word matching, cheap and
  reliable. Everything else is flagged for a human to decide.
- **No keyword matching for content categories.** It was tried and removed: "rave" matched inside
  "traveled", "vodka" inside "spicy vodka pizza". Content judgments go to the AI, not keyword lists.
- **A failed download is reported as "not analyzed", never as clean.** A profile once showed
  "0 flags" with 22 of 22 videos unanalyzed.
- **Reports are written incrementally** (after the text pass, after each profile, at the end) so a
  crash never loses finished work.
- **A human makes the final call.** The tool flags with evidence; people approve or reject.
- **Flags have a sensitivity (added 2026-10-20).** The model rates every category 0-3 per post
  (none / incidental / notable / heavy) and says why; a post is *flagged* only at or above the
  job's minimum level (default **heavy** for every category; override per job with
  `MIN_LEVELS="drinking=notable,..."`). Brands mostly don't care about a glass of wine or a bottle
  on a shelf - only heavy cases. Every observation is saved in `runs/*.json`, so sensitivity can be
  changed later for free with `rethreshold.py` (no re-analysis). The prompt still says to report
  minor cases at level 1 - never drop them; the threshold decides what gets flagged.

## Target architecture

**Deal-breakers are new for every run.** So separate the expensive work from the per-run work:

1. **Describe once (cached per post, permanent):** a neutral record of each post — what's on screen,
   visible brands/logos, on-screen text, audio transcript, caption, alt text, tags, partnership label.
   Expensive (download + vision + transcription); done once per post and reused forever.
2. **Judge per run (cheap, text-only):** check the saved descriptions against that run's structured
   criteria. Re-checking a known creator for a new brand only needs new posts described.
3. **Targeted second look:** when a criterion is specific and visual (e.g. a particular product),
   go back to the saved frames of relevant posts instead of re-watching everything.

**Criteria format** (entered at the start of each run; a chat helper drafts it, a person confirms):
each item has a category, a severity (`reject` / `flag` / `note`), and examples of what counts and
what doesn't. Save the exact criteria with every result so decisions can be explained later.

**Every flag carries evidence:** post link, timestamp, frame thumbnail, and the reason.

**Media links expire.** Instagram video URLs in a scrape stop working within days (403); image
URLs last somewhat longer. So per-post descriptions must be made soon after scraping, and any
frames needed for later re-checks (step 3, evidence thumbnails) must be stored as files — a
saved scrape can't be re-watched later.

**Interface:** a Streamlit app — upload a creator list, enter criteria, watch progress, review flags
with evidence, approve/override with a note (logged), export a report for legal.

## Roadmap

- **Phase 0 — Cleanup.** Rotate the old Apify and Anthropic keys (they're in git history).
  The Anthropic key was replaced on 2026-10-12 (the old one had been revoked); Apify now uses
  the organization's token — confirm the old personal Apify token is revoked.
  ~~Stop tracking `cache/`, `__pycache__/`, the vendor sample PDFs and generated reports.~~
  Done (now in `.gitignore`), but they are still in git history.
- **Phase 1 — Fast, complete engine.**
  - ~~Process profiles and video downloads in parallel~~ Done: ot.lorena's 132 videos in ~2 min
    (vs ~26 min estimated one at a time), 5 reference flags kept.
  - Add audio transcription (spoken swearing is currently undetected; also catches spoken sponsors).
  - ~~Cover image and carousel posts~~ Done (2026-10-16): photos, every carousel slide and
    video covers are checked (~29% of posts were skipped before). ot.lorena: 6 more posts, 2 new
    flags, 5 reference flags kept; cost +23%, time +6%.
  - Use free data already in the scrape: ~~alt text~~ (done; also paid-partnership label and
    tagged accounts), comments, audio info. Alt text only has a real description on ~3% of
    posts and ~16% of carousel slides; its effect isn't measured yet (ot.lorena has none).
  - Smarter frame sampling (scene changes instead of fixed spacing).
  - Store output as the reusable per-post descriptions above, not just yes/no flags.
  - Measure time and cost per profile before and after every change (`runs/` +
    `compare_runs.py`).
- **Phase 2 — Criteria-based judging.** *Criteria are now saved job files (2026-10-20); the chat helper, per-run judging against cached descriptions and evidence thumbnails are still open.* Structured criteria, chat helper to draft them, per-run
  judging against cached descriptions, competitor list per run, evidence on every flag.
- **Phase 3 — Streamlit app** for the team.
- **Phase 4 — Monitoring after go-live.** Scheduled re-scans of active creators' new posts, alerts
  on new flags, decision log / audit trail.

## Testing

Use **ot.lorena** as the regression profile. On 2026-10-16 its last 12 months were 138 posts
(132 videos, 6 carousels), 0 failures, 11 flagged. The 5 flags from the 2026-08-07 report (kept
locally in `cache/archive/`) must stay flagged after any speed or sampling change: run before and
after on the same fresh scrape (links expire), then
`compare_runs.py BEFORE AFTER --reference <that report>`. Report time, cost and flag differences.

**Baseline under review (2026-10-20):** most of those flags are restaurant/bar drinking or small
parties, which the sensitivity levels now rate *incidental* (not flagged by default). With levels,
compare models/settings on the same run with `rethreshold.py`. Result on ot.lorena: at `notable`
and `heavy`, Sonnet 4.5 and Haiku 4.5 flagged the identical posts (at `heavy` none; at `notable`
only the nightclub/DJ-booth post, partying=notable), and Haiku cost $1.41 vs $4.12. A person still
needs to confirm which ot.lorena posts are a real problem before a new reference list replaces the
old one.

**Default model is now Haiku 4.5 (2026-10-20).** Chosen for cost (about $0.01/post vs $0.03 for
Sonnet 4.5). It matched Sonnet 4.5 on ot.lorena at `notable`/`heavy`, but ot.lorena has no truly
heavy content, so it is not yet validated on high-flag creators (e.g. food_with_howie, muaeleni).
Override per job with `VISION_MODEL=claude-sonnet-4-5`.

## Rules

- Never commit `.env`, API keys, `cache/`, or scraped personal data. This repo has been public.
- Scraped data is about real people (some may be in the EU). Don't copy it elsewhere; keep a
  retention limit in mind for anything stored long-term.
- Commit small, with messages that explain **why**, and push — a separate planning chat reads the repo.
- When work lands, update the "Current code" and "Roadmap" sections of this file.
- Ask before changing the design decisions above.