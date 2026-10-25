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
