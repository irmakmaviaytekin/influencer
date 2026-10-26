# Demo runbook

## Before (5 min)
1. `streamlit run app.py` (or it is already on port 8599). Sidebar -> Demo mode: turn on **Mask creator names** and **Blur evidence images** if the room should not see real people.
2. Pick the run to show on Review. Fictional fallback: `python3 make_sample_run.py` (8 made-up creators, no API). Credits are empty, so real data cannot be generated until Anthropic credit is added.
3. Set "Your name" in the sidebar.

## Flow (about 8 min)
1. **Review** - tiles per creator; point out colour = category, analyzed / not analyzed counts.
2. **Sensitivity** - drop Alcohol / Party from heavy to notable: flags go from 4 to 8 instantly, no cost. Back to heavy.
3. **Open a flagged creator** (sample.elena) - evidence frame, model's reasoning, post link.
4. **Decide** - Escalate to a named person, add a note. Then **Decision log** page.
5. **Export** - download the .xlsx; show Decisions / Flags / Criteria used.
6. **Jobs** - criteria table, Advanced settings. **Setup assistant** - needs credit to talk; without it show the empty draft and the Jobs page instead.
7. **Run a job** - "Check size and cost" works from cache, free. Do not start a real run live.

## Do not
- Start a live scrape/analysis (needs credit, minutes long). Pre-run beforehand if credit exists.
- Show unmasked real creator names to people outside the team.

## Main story: upload names -> choose what to look for -> get a report
Uses the real run `frozen-pizza-2026-10` (20 creators, 5 categories, 4 months, reels only). Turn on Demo mode (mask names, blur images).
1. **Jobs** -> "New job". Upload `jobs/demo-creators.txt` (one handle per line; local only, not in git) with the file uploader and show the list fill in.
2. Choose what to look for: the categories table (violence, alcohol, hate speech, religion, partying), the default sensitivity, competitor brands. Don't save over the existing job; name it `demo-live`.
3. **Run a job** -> pick `frozen-pizza-2026-10` -> "Check size and cost" (free). Say this is the run done earlier: about 15 minutes, $2.72 of analysis. Don't press Start.
4. **Review** -> that run: tiles, drop sensitivity to notable (two creators light up on alcohol), open evidence, decide, export.
5. **Setup assistant** is the alternative to step 2: describe the brand and it fills the draft.
Two handles in the list don't exist on Instagram, which is a good way to show failures being reported rather than hidden.
