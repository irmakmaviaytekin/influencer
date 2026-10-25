"""Review GUI for the creator brand-safety screening tool.

    streamlit run app.py

Pages: Review (flags with evidence, sensitivity, decisions, export), Run a job,
Jobs (create/edit criteria), Decision log. Runs the engine (main.py) as a separate
process, so the tool works the same from the command line and from here.

This is a LOCAL tool: it shows real people's content. Don't expose it publicly.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import config
import review_lib as rl

ROOT = Path(__file__).parent
JOBS_DIR = ROOT / "jobs"
RUNS_DIR = ROOT / "runs"
ACTIVE = RUNS_DIR / "gui-active.json"
LEVEL_OPTIONS = list(rl.LEVELS)
LEVEL_COLOR = {1: "gray", 2: "orange", 3: "red"}

st.set_page_config(page_title="Creator screening", layout="wide")
st.markdown("""<style>
.block-container {padding-top: 2.4rem; max-width: 1280px;}
h1 {font-weight: 650 !important; letter-spacing: -.01em;}
section[data-testid="stSidebar"] {background: #F1F5F3;}
[data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #DDE3E1; border-radius: 10px; padding: 14px 18px;}
[data-testid="stMetricLabel"] {color: #5A6B68;}
.brand {font-size: 1.3rem; font-weight: 700; letter-spacing: -.01em; margin-top: .2rem;}
.brandsub {font-size: .72rem; color: #5A6B68; text-transform: uppercase; letter-spacing: .1em; margin-bottom: 1.2rem;}
.subtitle {color: #5A6B68; margin: -.7rem 0 1.1rem 0; font-size: 1.02rem;}
</style>""", unsafe_allow_html=True)


def shown(name: str, names: list[str]) -> str:
    """Demo mode can hide real handles on screen (the data and decision log keep the real ones)."""
    if not st.session_state.get("mask_names") or name not in names:
        return name
    i = names.index(name)
    return f"Creator {chr(65 + i)}" if i < 26 else f"Creator {i + 1}"


@st.cache_data(show_spinner=False)
def _img(path: str, blur: bool):
    from PIL import Image, ImageFilter
    im = Image.open(path)
    im.load()
    return im.filter(ImageFilter.GaussianBlur(max(im.size) / 20)) if blur else im


# ------------------------------------------------------------------------ helpers
def job_files() -> list[Path]:
    return sorted(JOBS_DIR.glob("*.json")) if JOBS_DIR.exists() else []


def read_job(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_job(path: Path) -> str | None:
    """Use the engine's own job validation, so the GUI can never save a job the engine rejects."""
    r = subprocess.run([sys.executable, "-c", "import config"], cwd=ROOT, capture_output=True,
                       text=True, env={**os.environ, "JOB": str(path)})
    if r.returncode == 0:
        return None
    return (r.stderr.strip().splitlines() or ["The job file is not valid."])[-1]


def est_cost(posts: int, model: str) -> float:
    """Rough: about 9,000 input and 120 output tokens per post (measured on real runs)."""
    m = config.VISION_MODELS[model]
    return posts * (9000 * m["price_in"] + 120 * m["price_out"]) / 1_000_000


@st.cache_resource
def _procs() -> dict:
    return {}


def active_run() -> dict | None:
    if not ACTIVE.exists():
        return None
    info = json.loads(ACTIVE.read_text())
    proc = _procs().get(info["pid"])
    if proc is not None:
        alive = proc.poll() is None
    else:
        try:
            os.kill(info["pid"], 0)
            alive = True
        except OSError:
            alive = False
    info["alive"] = alive
    return info


def start_run(job: str, text_only: bool) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    log = RUNS_DIR / f"gui-{job}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    cmd = [sys.executable, "-u", "main.py", "--job", job] + (["--text-only"] if text_only else [])
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log.open("w"), stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})
    _procs()[proc.pid] = proc
    ACTIVE.write_text(json.dumps({"pid": proc.pid, "log": str(log), "job": job,
                                  "text_only": text_only, "started": time.time()}))


def clean_log(path: str) -> list[str]:
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return []
    skip = ("apify.instagram-scraper", "Traceback", "  File ", "raise ", "^")
    return [l for l in lines if l.strip() and not any(s in l for s in skip) and not l.startswith("    ")
            or re.match(r"\s+\d+/\d+ posts analyzed", l)]


@st.cache_data(show_spinner=False)
def _load_run(run_id: str, mtime: float) -> dict:
    return rl.load_run(run_id)


# -------------------------------------------------------------------------- Review
def page_review() -> None:
    st.title("Review")
    runs = [r for r in rl.list_runs() if r["reviewable"]]
    if not runs:
        st.info("No finished runs to review yet. Start one on the **Run a job** page.")
        return

    def label(rid: str) -> str:
        r = next(x for x in runs if x["id"] == rid)
        when = r["started"][:16].replace("T", " ")
        return f"{when} · {r['job'] or 'run'} · {r['profiles']} creators · {r['posts']} posts · {r['model']}"

    rid = st.selectbox("Run", [r["id"] for r in runs], format_func=label)
    run = _load_run(rid, (RUNS_DIR / f"{rid}.json").stat().st_mtime)
    cats = rl.categories_of(run)
    has_levels = any("levels" in p for p in run["per_post"])
    job = run.get("job") or {}
    if job.get("brand") or job.get("campaign"):
        st.markdown(f"<div class='subtitle'>{job.get('brand') or ''}"
                    f"{' · ' if job.get('brand') and job.get('campaign') else ''}"
                    f"{job.get('campaign') or ''} · {run.get('settings', {}).get('vision_model', '')}"
                    f"</div>", unsafe_allow_html=True)

    # Sensitivity: re-applied from the saved levels, free of charge.
    base = rl.default_mins(run)
    st.markdown("**Sensitivity** — a post is flagged at or above this level")
    if not has_levels:
        st.caption("This run predates saved levels, so its recorded flags are shown as they were.")
        mins = base
    else:
        cols = st.columns(len(cats))
        mins = {}
        for col, (k, c) in zip(cols, cats.items()):
            mins[k] = col.selectbox(c.get("label", k), LEVEL_OPTIONS, key=f"min|{rid}|{k}",
                                    index=LEVEL_OPTIONS.index(base.get(k, "heavy")),
                                    help=c.get("description") or None)
        if mins != base:
            st.caption("Sensitivity differs from the one this run used. Counts below follow what you "
                       "chose here, and the export records it.")

    flags = rl.flags_for(run, mins)
    table = rl.profile_table(run, flags)
    decisions = rl.latest_by_creator(rid)
    table.sort(key=lambda r: (-r["flagged_posts"], r["creator"]))

    names = sorted(r["creator"] for r in table)
    flagged_creators = sum(1 for r in table if r["flagged_posts"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Creators", len(table))
    m2.metric("With flags", flagged_creators)
    m3.metric("Flagged posts", len({f["url"] for f in flags}))
    m4.metric("Reviewed", sum(1 for r in table if r["creator"] in decisions))

    lv = rl.profile_levels(run)
    word = {0: "—", 1: "incidental", 2: "notable", 3: "heavy"}
    # (faint = seen but below the sensitivity, strong = flagged), by highest level seen
    tile = {1: ("rgba(150,150,150,.14)", "rgba(150,150,150,.32)"),
            2: ("rgba(240,160,40,.16)", "rgba(240,160,40,.50)"),
            3: ("rgba(220,60,60,.18)", "rgba(220,60,60,.55)")}
    rows, css = [], []
    for r in table:
        d = decisions.get(r["creator"], {})
        dec = d.get("decision", "—") + (f" → {d['escalated_to']}" if d.get("escalated_to") else "")
        row = {"Creator": shown(r["creator"], names), "Decision": dec, "Flagged posts": r["flagged_posts"]}
        shade = {"Creator": "", "Decision": "", "Flagged posts": ""}
        for k, c in cats.items():
            lab, n = c.get("label", k), r["by_category"].get(k, 0)
            if has_levels:
                mx = lv.get(r["creator"], {}).get(k, 0)
                row[lab] = "—" if not mx else (f"{word[mx]} · {n}" if n else word[mx])
                shade[lab] = f"background-color: {tile[mx][1 if n else 0]}" if mx else ""
            else:  # older run: only yes/no flags were saved
                row[lab] = str(n) if n else "—"
                shade[lab] = f"background-color: {tile[3][1]}" if n else ""
        row["Not analyzed"] = ("⚠ " if r["incomplete"] else "") + str(r["not_analyzed"] or "")
        shade["Not analyzed"] = ""
        rows.append(row)
        css.append(shade)
    df = pd.DataFrame(rows)
    styled = df.style.apply(lambda _: pd.DataFrame(css, index=df.index, columns=df.columns), axis=None)
    st.caption("Each tile shows the highest level seen. Strong colour = flagged at the sensitivity above "
               "(the number is flagged posts); faint = seen, but below it. Select a creator to see the evidence.")
    ev = st.dataframe(styled, width="stretch", hide_index=True, on_select="rerun",
                      selection_mode="single-row", key=f"tbl|{rid}")
    sel = ev.selection.rows
    st.session_state.setdefault("export", {})
    c_exp1, c_exp2 = st.columns([2, 5])
    if c_exp1.button("Prepare legal export"):
        st.session_state["export"][rid] = rl.export_xlsx(run, mins)
    if rid in st.session_state["export"]:
        c_exp2.download_button("⬇ Download report for legal (.xlsx)", st.session_state["export"][rid],
                               file_name=f"{job.get('name') or 'report'}-{rid}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if not sel:
        return

    row = table[sel[0]]
    creator = row["creator"]
    st.divider()
    st.subheader(shown(creator, names))
    if row["not_analyzed"]:
        st.warning(f"{row['not_analyzed']} of {row['analyzed'] + row['not_analyzed']} posts could not be "
                   f"analyzed. A clean result is not proven for this creator — consider rerunning.")

    mine = [f for f in flags if f["profile"] == creator]
    by_post: dict[str, list[dict]] = {}
    for f in mine:
        by_post.setdefault(f["url"], []).append(f)
    prev = decisions.get(creator, {})
    prev_dismissed = set(prev.get("dismissed", []))
    if not by_post:
        st.success("Nothing flagged at this sensitivity.")
    for url, fl in sorted(by_post.items(), key=lambda kv: -max((f["level"] or 0) for f in kv[1])):
        with st.container(border=True):
            left, right = st.columns([1, 3])
            shown_frames = [ROOT / t for t in fl[0]["thumbs"] if (ROOT / t).exists()]
            with left:
                if shown_frames:
                    for t in shown_frames:
                        st.image(_img(str(t), bool(st.session_state.get("blur_imgs"))), width=230)
                else:
                    st.caption("No frame saved for this run.")
            with right:
                for f in fl:
                    lvl = rl.LEVEL_NAMES.get(f["level"], "flagged")
                    st.badge(f"{cats.get(f['category'], {}).get('label', f['category'])} · {lvl}",
                             color=LEVEL_COLOR.get(f["level"], "gray"))
                    st.write(f["reason"] or "—")
                b1, b2 = st.columns([1, 2])
                if not st.session_state.get("mask_names"):
                    b1.link_button("Open post", url)
                b2.checkbox("Not a problem (dismiss)", key=f"dis|{rid}|{creator}|{url}",
                            value=url in prev_dismissed)

    st.markdown("**Decision**")
    with st.form(f"decide|{rid}|{creator}"):
        options = rl.DECISIONS
        choice = st.radio("Decision", options, horizontal=True,
                          index=options.index(prev["decision"]) if prev.get("decision") in options
                          else options.index("Needs more review"))
        escalate_to = st.text_input("If escalating — to whom? (e.g. legal, brand lead)",
                                    value=prev.get("escalated_to", ""))
        note = st.text_area("Note (why — this goes in the report)", value=prev.get("note", ""))
        if st.form_submit_button("Save decision", type="primary"):
            who = st.session_state.get("reviewer", "").strip()
            if not who:
                st.error("Enter your name in the sidebar first, so the decision is traceable.")
            elif choice == "Escalate" and not escalate_to.strip():
                st.error("Say who this is escalated to.")
            else:
                dismissed = [u for u in by_post if st.session_state.get(f"dis|{rid}|{creator}|{u}")]
                rl.log_decision({
                    "run": rid, "job": job.get("name"), "brand": job.get("brand"),
                    "campaign": job.get("campaign"), "creator": creator, "decision": choice,
                    "escalated_to": escalate_to.strip() if choice == "Escalate" else "",
                    "note": note, "reviewer": who, "dismissed": dismissed,
                    "flags_shown": len(by_post), "sensitivity": mins})
                st.session_state["export"].pop(rid, None)
                st.success(f"Saved: {choice}.")
                st.rerun()
    history = [d for d in rl.load_decisions(rid) if d["creator"] == creator]
    if history:
        with st.expander(f"History for {shown(creator, names)} ({len(history)})"):
            for d in reversed(history):
                st.write(f"**{d['decision']}** — {d['reviewer']}, {d['ts'].replace('T', ' ')}"
                         + (f" — {d['note']}" if d.get("note") else ""))


# ----------------------------------------------------------------------- Run a job
def page_run() -> None:
    st.title("Run a job")
    jobs = job_files()
    if not jobs:
        st.info("No jobs yet. Create one on the **Jobs** page.")
        return
    act = active_run()
    if act and act["alive"]:
        st.warning(f"A run is in progress: **{act['job']}**"
                   f"{' (size check)' if act['text_only'] else ''}. Only one run at a time.")
        _live(act)
        return
    if act and not act["alive"]:
        _finished(act)

    names = [p.stem for p in jobs]
    name = st.selectbox("Job", names)
    job = read_job(JOBS_DIR / f"{name}.json")
    model = job.get("vision_model", config.VISION_MODEL)
    a, b, c, d = st.columns(4)
    a.metric("Creators", len(job.get("profiles") or []))
    b.metric("Months back", job.get("months_lookback", 12))
    c.metric("Reels only", "yes" if job.get("videos_only") else "no")
    d.metric("Model", model)
    st.caption("Categories: " + ", ".join(
        v.get("label", k) for k, v in (job.get("categories") or {}).items()) or "(standard set)")

    st.info("**Check size and cost first.** This scrapes any creators not already stored (Instagram "
            "scraping costs credits, roughly $0.50–2 per new creator) and counts the posts, but does "
            "not run the vision model.")
    c1, c2 = st.columns(2)
    if c1.button("1 · Check size and cost"):
        start_run(name, text_only=True)
        st.rerun()
    est = st.session_state.get("last_check", {})
    if est.get("job") == name:
        c1.success(f"{est['posts']} posts to analyze ≈ **${est_cost(est['posts'], model):.2f}** "
                   f"with {model} (rough).")
    if c2.button("2 · Start full run", type="primary"):
        start_run(name, text_only=False)
        st.rerun()


def _finished(act: dict) -> None:
    lines = clean_log(act["log"])
    text = "\n".join(lines)
    m = re.search(r"\((\d+) posts across", text)
    if act["text_only"] and m:
        st.session_state["last_check"] = {"job": act["job"], "posts": int(m.group(1))}
    if "STOPPING" in text or "Run stopped" in text:
        st.error("The run stopped early — see the log. Finished creators are saved.")
    elif "Run metrics" in text:
        st.success("Run finished. Open the **Review** page.")
    elif act["text_only"] and "Text pass done" in text:
        st.success("Size check done.")
    with st.expander("Log of the last run"):
        st.code("\n".join(lines[-60:]) or "(empty)")
    ACTIVE.unlink(missing_ok=True)


def _live(act: dict) -> None:
    @st.fragment(run_every=2)
    def view() -> None:
        lines = clean_log(act["log"])
        text = "\n".join(lines)
        prog = re.findall(r"(\d+)/(\d+) posts analyzed", text)
        tp = re.findall(r"\[(\d+)/(\d+)\]", text)
        if prog:
            d, t = map(int, prog[-1])
            st.progress(d / t, text=f"Analyzing posts: {d}/{t}")
        elif tp:
            d, t = map(int, tp[-1])
            st.progress(d / t, text=f"Scraping creators: {d}/{t}")
        st.code("\n".join(lines[-25:]) or "Starting…")
        a = active_run()
        if a and not a["alive"]:
            st.rerun()
    view()
    if st.button("Stop run"):
        p = _procs().get(act["pid"])
        try:
            (p.terminate() if p else os.kill(act["pid"], 15))
        except OSError:
            pass
        time.sleep(1)
        st.rerun()


# ----------------------------------------------------------------------------- Jobs
def page_jobs() -> None:
    st.title("Jobs")
    st.caption("A job is one brand or campaign's whole setup: creators, criteria and how sensitive to be.")
    existing = {p.stem: p for p in job_files()}
    pick = st.selectbox("Job", ["➕ New job"] + list(existing))
    data = read_job(existing[pick]) if pick in existing else {}
    key = f"{pick}"

    name = st.text_input("Job name (file name)", data.get("name", ""), key=f"n|{key}",
                         help="Letters, numbers, dashes. e.g. quiet-luxury-2026-10")
    c1, c2 = st.columns(2)
    brand = c1.text_input("Brand", data.get("brand") or "", key=f"b|{key}")
    campaign = c2.text_input("Campaign", data.get("campaign") or "", key=f"c|{key}")

    st.markdown("**Creators**")
    up = st.file_uploader("Upload a list (.txt or .csv, one Instagram handle per line)", type=["txt", "csv"],
                          key=f"u|{key}")
    start = "\n".join(data.get("profiles") or [])
    if up is not None:
        extra = [re.sub(r"[,;\s].*$", "", l.strip()).lstrip("@") for l in up.read().decode("utf-8", "replace").splitlines()]
        start = "\n".join(dict.fromkeys([x for x in extra if x and not x.startswith("#")]))
    profiles = st.text_area("One handle per line", start, height=160, key=f"p|{key}|{hash(start) % 10**6}")

    c1, c2, c3 = st.columns(3)
    months = c1.number_input("Look back (months)", 1, 36, int(data.get("months_lookback", 12)), key=f"m|{key}")
    videos_only = c2.checkbox("Reels/videos only (skip photos and carousels)", bool(data.get("videos_only", False)),
                              key=f"v|{key}")
    models = list(config.VISION_MODELS)
    model = c3.selectbox("Model", models, index=models.index(data.get("vision_model", config.VISION_MODEL))
                         if data.get("vision_model", config.VISION_MODEL) in models else 0, key=f"mo|{key}",
                         help="Cheaper models cost less per post; check a sample before trusting a switch.")
    c1, c2 = st.columns(2)
    competitors = c1.text_area("Competitor brands (a mention rejects the creator; one per line)",
                               "\n".join(data.get("competitors") or []), height=110, key=f"co|{key}")
    review = c2.text_area("Brands to flag for a person (never auto-reject; one per line)",
                          "\n".join(data.get("review_brands") or []), height=110, key=f"rb|{key}")
    default_min = st.select_slider("Default sensitivity — flag at this level or above", LEVEL_OPTIONS,
                                   value=data.get("default_min_level", "heavy"), key=f"dm|{key}")

    st.markdown("**What to look for**")
    st.caption("Describe what counts and what doesn't. The model rates each post 0–3 per category; "
               "a post is flagged at the category's level or above (blank = the default above).")
    old = data.get("categories") or {}
    rows = [{"key": k, "label": v.get("label", k), "description": v.get("description", ""),
             "min_level": v.get("min_level") or "", "text_only": bool(v.get("text_only", False))}
            for k, v in old.items()] or [{"key": "partying", "label": "Party energy",
                                          "description": "club or party scenes, dancing crowds, nightlife",
                                          "min_level": "", "text_only": False}]
    edited = st.data_editor(
        pd.DataFrame(rows), num_rows="dynamic", width="stretch", key=f"ed|{key}",
        column_config={
            "key": st.column_config.TextColumn("Key", help="short id, e.g. drinking"),
            "label": st.column_config.TextColumn("Label"),
            "description": st.column_config.TextColumn("What counts (and what doesn't)", width="large"),
            "min_level": st.column_config.SelectboxColumn("Flag at", options=[""] + LEVEL_OPTIONS),
            "text_only": st.column_config.CheckboxColumn("Text only", help="judged from on-screen text and caption only"),
        })

    if st.button("Save job", type="primary"):
        slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-")
        if not slug:
            st.error("Give the job a name.")
            return
        cats = {}
        for _, r in edited.iterrows():
            k = re.sub(r"[^a-z0-9_]+", "_", str(r["key"] or "").strip().lower()).strip("_")
            if not k:
                continue
            c = {k2: v for k2, v in (old.get(k) or {}).items() if k2 in ("levels", "color")}  # keep advanced fields
            c.update({"label": str(r["label"] or k), "description": str(r["description"] or "").strip(),
                      "text_only": bool(r["text_only"])})
            if r["min_level"]:
                c["min_level"] = r["min_level"]
            cats[k] = c
        lst = lambda s: [l.strip().lstrip("@") for l in s.splitlines() if l.strip() and not l.strip().startswith("#")]
        job = {**{k: v for k, v in data.items() if k in ("notes",)},
               "name": slug, "brand": brand, "campaign": campaign, "profiles": lst(profiles),
               "months_lookback": int(months), "videos_only": bool(videos_only), "vision_model": model,
               "default_min_level": default_min, "competitors": lst(competitors),
               "review_brands": lst(review), "categories": cats}
        JOBS_DIR.mkdir(exist_ok=True)
        path = JOBS_DIR / f"{slug}.json"
        backup = path.read_text() if path.exists() else None
        path.write_text(json.dumps(job, indent=2))
        problem = validate_job(path)
        if problem:
            path.write_text(backup) if backup is not None else path.unlink()
            st.error(problem)
        else:
            st.success(f"Saved jobs/{slug}.json — {len(job['profiles'])} creators, {len(cats)} categories.")


# ------------------------------------------------------------------------ Decision log
def page_log() -> None:
    st.title("Decision log")
    st.caption("Every decision ever saved. Append-only: a changed decision adds a new line, nothing is overwritten.")
    d = rl.load_decisions()
    if not d:
        st.info("No decisions yet.")
        return
    df = pd.DataFrame(d).sort_values("ts", ascending=False)
    cols = [c for c in ("ts", "creator", "decision", "escalated_to", "reviewer", "note", "brand", "campaign", "job", "run") if c in df]
    st.dataframe(df[cols], width="stretch", hide_index=True)
    st.download_button("⬇ Download log (.csv)", df[cols].to_csv(index=False), file_name="decision-log.csv",
                       mime="text/csv")


# ---------------------------------------------------------------------------- shell
with st.sidebar:
    st.markdown("<div class='brand'>Creator screening</div><div class='brandsub'>Brand-safety review</div>",
                unsafe_allow_html=True)
    st.text_input("Your name", key="reviewer", help="Recorded with every decision")
    page = st.radio("Page", ["Review", "Run a job", "Jobs", "Decision log"], label_visibility="collapsed")
    st.divider()
    with st.expander("Demo mode"):
        st.toggle("Mask creator names", key="mask_names", help="Shows Creator A, B, C on screen instead of handles")
        st.toggle("Blur evidence images", key="blur_imgs", help="Blurs faces and scenes on screen")
        st.caption("Screen only - saved decisions and exports keep the real names.")
    st.caption("Local tool - it shows real people's content. Don't expose it on the internet.")

{"Review": page_review, "Run a job": page_run, "Jobs": page_jobs, "Decision log": page_log}[page]()
