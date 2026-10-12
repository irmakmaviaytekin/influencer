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

- `main.py` — runs the pipeline: text pass for all profiles, then vision pass, writes reports.
  Profiles are processed **one at a time** (no concurrency yet).
- `scraper.py` — pulls posts via Apify `apify/instagram-scraper`, last 12 months, caches to `cache/`.
- `analyzer.py` — brand-deal detection (labels, hashtags, phrases, mentions), competitor match,
  video download, frame sampling (OpenCV), vision call to Anthropic.
- `export_report.py` — CSV/XLSX export alongside the HTML report.
- `config.py` — all settings; keys come from `.env`.
- Inputs: `profiles.txt`, `competitor_brands.txt`. Output: `influencer_report.*` (overwritten each run).

Current vision step: 6 evenly spaced frames per video, fixed categories
(drinking, smoking, partying, gambling, swearing). Per the note in `config.py`, video **download**
is the main bottleneck, not frame count.

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

**Interface:** a Streamlit app — upload a creator list, enter criteria, watch progress, review flags
with evidence, approve/override with a note (logged), export a report for legal.

## Roadmap

- **Phase 0 — Cleanup.** Rotate the old Apify and Anthropic keys (they're in git history).
  ~~Stop tracking `cache/`, `__pycache__/`, the vendor sample PDFs and generated reports.~~
  Done (now in `.gitignore`), but they are still in git history.
- **Phase 1 — Fast, complete engine.**
  - Process profiles and video downloads in parallel (biggest expected win).
  - Add audio transcription (spoken swearing is currently undetected; also catches spoken sponsors).
  - Cover image and carousel posts (currently ~30% of posts are skipped).
  - Use free data already in the scrape: alt text, comments, audio info.
  - Smarter frame sampling (scene changes instead of fixed spacing).
  - Store output as the reusable per-post descriptions above, not just yes/no flags.
  - Measure time and cost per profile before and after every change.
- **Phase 2 — Criteria-based judging.** Structured criteria, chat helper to draft them, per-run
  judging against cached descriptions, competitor list per run, evidence on every flag.
- **Phase 3 — Streamlit app** for the team.
- **Phase 4 — Monitoring after go-live.** Scheduled re-scans of active creators' new posts, alerts
  on new flags, decision log / audit trail.

## Testing

Use **ot.lorena** as the regression profile: 118 videos, 0 failures, 5 flagged in the last full run.
Any speed or sampling change must not lose those flags. Report time, cost and flag differences.

## Rules

- Never commit `.env`, API keys, `cache/`, or scraped personal data. This repo has been public.
- Scraped data is about real people (some may be in the EU). Don't copy it elsewhere; keep a
  retention limit in mind for anything stored long-term.
- Commit small, with messages that explain **why**, and push — a separate planning chat reads the repo.
- When work lands, update the "Current code" and "Roadmap" sections of this file.
- Ask before changing the design decisions above.