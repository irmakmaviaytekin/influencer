"""Look and feel for the review GUI: stylesheet, sidebar logo, page banners and illustrations.
All artwork is inline SVG drawn here - no external images, nothing to download."""
from __future__ import annotations

import streamlit as st

INK, DEEP, TEAL, MINT, SAND, AMBER = "#0F1C1A", "#14302B", "#00806A", "#7FD1BC", "#F6F5F0", "#C9772B"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {{font-family: 'DM Sans', system-ui, sans-serif;}}
.stApp {{background: {SAND};}}
.block-container {{padding-top: 1.6rem; max-width: 1320px;}}
header[data-testid="stHeader"] {{background: transparent;}}

/* sidebar */
section[data-testid="stSidebar"] {{background: linear-gradient(180deg, #0E2622 0%, {DEEP} 100%);}}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label p, section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p, section[data-testid="stSidebar"] summary p,
section[data-testid="stSidebar"] summary span {{color: #CFE3DE !important;}}
section[data-testid="stSidebar"] hr {{border-color: rgba(255,255,255,.12);}}
section[data-testid="stSidebar"] div[role="radiogroup"] {{gap: 4px;}}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{padding: 9px 12px; border-radius: 10px; width: 100%;}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{background: rgba(255,255,255,.07);}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{background: rgba(127,209,188,.18);}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{color: #FFFFFF !important; font-weight: 600;}}
section[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{display: none;}}
section[data-testid="stSidebar"] [data-testid="stExpander"] {{border: 1px solid rgba(255,255,255,.14); border-radius: 10px;}}
.logo {{display:flex; align-items:center; gap:12px; margin: .3rem 0 .2rem 0;}}
.logo b {{font-size: 1.25rem; color:#fff; letter-spacing:-.01em;}}
.logosub {{font-size:.7rem; color:{MINT}; text-transform:uppercase; letter-spacing:.14em; margin: 0 0 1.2rem 52px;}}

.whoami {{display:flex; align-items:center; gap:10px; background:rgba(255,255,255,.07); border-radius:12px; padding:10px 12px; margin-bottom:10px;}}
.whoami span {{width:34px; height:34px; border-radius:50%; background:{TEAL}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700;}}
.whoami div {{line-height:1.25;}} .whoami b {{color:#FFFFFF !important; font-size:1rem;}} .whoami small {{color:{MINT} !important; font-size:.8rem;}}
/* page banner */
.hero {{position:relative; overflow:hidden; border-radius:18px; padding:30px 290px 30px 36px; margin: 0 0 1.4rem 0;
  background: radial-gradient(120% 140% at 100% 0%, #1F5A4E 0%, {DEEP} 55%, #0E2622 100%); color:#fff;
  box-shadow: 0 10px 30px rgba(15,44,38,.18);}}
.hero .kicker {{font-size:.74rem; letter-spacing:.16em; text-transform:uppercase; color:{MINT}; font-weight:600;}}
.hero h1 {{margin:.25rem 0 .35rem 0 !important; padding:0 !important; font-size:2.2rem !important; font-weight:700 !important;
  letter-spacing:-.02em; color:#fff !important;}}
.hero p {{margin:0; color:#BFD8D5; font-size:1.02rem;}}

.hero > .kicker, .hero > h1, .hero > p, .hero > .chips {{position:relative; z-index:1;}}
@media (max-width: 1100px) {{.hero .art {{display:none;}} .hero {{padding-right:36px;}}}}
.hero .art {{position:absolute; right:26px; top:50%; transform:translateY(-50%); opacity:.95;}}
.hero .chips {{margin-top:14px; display:flex; gap:8px; flex-wrap:wrap;}}
.chip {{display:inline-block; padding:4px 11px; border-radius:999px; font-size:.78rem; font-weight:600;
  background:rgba(127,209,188,.16); color:{MINT}; border:1px solid rgba(127,209,188,.3);}}

/* inputs: clear borders on white so fields are visible */
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div, [data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stSelectbox"] div:has(> input), [data-testid="stMultiSelect"] div:has(> input) {{background:#FFFFFF !important; border:1.5px solid #AEBFBA !important; border-radius:10px !important;}}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within {{border-color:{TEAL} !important; box-shadow:0 0 0 3px rgba(0,128,106,.18);}}
section[data-testid="stSidebar"] div[data-baseweb="input"] input {{color:{INK} !important;}}
[data-testid="stFileUploaderDropzone"] {{background:#FFFFFF !important; border:1.5px dashed #7FA89D !important; border-radius:12px;}}
[data-testid="stWidgetLabel"] p, label p {{color:{INK}; font-weight:500;}}
section[data-testid="stSidebar"] .stButton > button {{background:rgba(255,255,255,.12); color:#FFFFFF; border:1px solid rgba(255,255,255,.35);}}
section[data-testid="stSidebar"] .stButton > button:hover {{background:rgba(255,255,255,.22);}}
section[data-testid="stSidebar"] .stButton > button p {{color:#FFFFFF !important;}}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{color:#A9C7C0 !important;}}
/* cards */
[data-testid="stMetric"] {{background:#fff; border:1px solid #E1E6E3; border-radius:14px; padding:16px 20px;
  box-shadow: 0 1px 2px rgba(15,28,26,.04); border-top:3px solid {TEAL};}}
[data-testid="stMetricLabel"] p {{color:#5A6B68; font-size:.82rem; text-transform:uppercase; letter-spacing:.06em;}}
[data-testid="stMetricValue"] {{font-weight:700; color:{DEEP};}}
[data-testid="stVerticalBlockBorderWrapper"] {{border-radius:14px; background:#fff;}}
div[data-testid="stDataFrame"] {{border:1px solid #E1E6E3; border-radius:14px; overflow:hidden; background:#fff;}}
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{border-radius:10px; font-weight:600;}}
.stButton > button[kind="primary"] {{background:{TEAL}; border:none;}}
.stButton > button[kind="primary"]:hover {{background:#006956;}}
[data-testid="stAlert"] {{border-radius:12px;}}
h2, h3 {{letter-spacing:-.01em; color:{DEEP};}}
.subtitle {{color:#5A6B68; margin:-.4rem 0 1rem 0; font-size:1.02rem;}}
.section {{font-size:.78rem; letter-spacing:.12em; text-transform:uppercase; color:{TEAL}; font-weight:700; margin:1.4rem 0 .5rem 0;}}

/* highlight strip */
.hl {{background:#fff; border:1px solid #E1E6E3; border-radius:14px; overflow:hidden; box-shadow:0 1px 2px rgba(15,28,26,.04);}}
.hl .cap {{padding:10px 14px 12px 14px;}}
.hl .who {{font-weight:700; color:{DEEP}; font-size:.95rem;}}
.pill {{display:inline-block; padding:2px 9px; border-radius:999px; font-size:.74rem; font-weight:700; margin-right:4px;}}
.pill.l1 {{background:#ECEFEE; color:#4B5B58;}} .pill.l2 {{background:#FCE8CF; color:#8A4B0B;}} .pill.l3 {{background:#F9D7D3; color:#9A2418;}}

/* empty state */
.empty {{text-align:center; padding:36px 10px; color:#5A6B68;}}
.empty b {{display:block; color:{DEEP}; font-size:1.15rem; margin:10px 0 4px 0;}}
</style>
"""

LOGO = f"""<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-label="logo">
<defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2FB596"/><stop offset="1" stop-color="{TEAL}"/></linearGradient></defs>
<rect width="40" height="40" rx="11" fill="url(#lg)"/>
<path d="M20 8 L31 12 V20 C31 26 26.5 30.5 20 33 C13.5 30.5 9 26 9 20 V12 Z" fill="none" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M14.5 20.5 L18.5 24.5 L26 16" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

_ART = {
    # a shield with a check, over faint frames
    "review": f"""<svg width="210" height="130" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="shield with check">
<rect x="6" y="22" width="64" height="86" rx="10" fill="#fff" opacity=".07"/><rect x="140" y="14" width="64" height="86" rx="10" fill="#fff" opacity=".07"/>
<rect x="14" y="30" width="48" height="34" rx="6" fill="#7FD1BC" opacity=".25"/><rect x="148" y="22" width="48" height="34" rx="6" fill="#C9772B" opacity=".35"/>
<path d="M105 8 L146 24 V58 C146 84 128 104 105 114 C82 104 64 84 64 58 V24 Z" fill="#00806A" stroke="#7FD1BC" stroke-width="3"/>
<path d="M86 60 L100 74 L126 44" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>""",
    # frames being scanned
    "run": f"""<svg width="210" height="130" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="video frames being scanned">
<g fill="#fff" opacity=".1"><rect x="8" y="30" width="50" height="70" rx="8"/><rect x="66" y="30" width="50" height="70" rx="8"/><rect x="124" y="30" width="50" height="70" rx="8"/></g>
<g fill="#7FD1BC" opacity=".35"><rect x="14" y="38" width="38" height="30" rx="5"/><rect x="72" y="38" width="38" height="30" rx="5"/><rect x="130" y="38" width="38" height="30" rx="5"/></g>
<rect x="55" y="14" width="6" height="102" rx="3" fill="#C9772B"/><path d="M58 14 L120 14" stroke="#C9772B" stroke-width="0"/>
<circle cx="170" cy="62" r="30" fill="none" stroke="#7FD1BC" stroke-width="7"/><path d="M192 84 L206 100" stroke="#7FD1BC" stroke-width="9" stroke-linecap="round"/></svg>""",
    # sliders / checklist
    "jobs": f"""<svg width="210" height="130" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="settings sliders">
<rect x="20" y="14" width="170" height="102" rx="14" fill="#fff" opacity=".08"/>
<g stroke="#7FD1BC" stroke-width="5" stroke-linecap="round" opacity=".7"><path d="M40 40 H170"/><path d="M40 66 H170"/><path d="M40 92 H170"/></g>
<circle cx="78" cy="40" r="10" fill="#C9772B"/><circle cx="132" cy="66" r="10" fill="#00806A" stroke="#7FD1BC" stroke-width="3"/><circle cx="96" cy="92" r="10" fill="#C9772B"/></svg>""",
    # chat bubbles
    "assistant": f"""<svg width="210" height="130" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="chat bubbles">
<path d="M20 18 H120 a12 12 0 0 1 12 12 V58 a12 12 0 0 1 -12 12 H56 L36 88 V70 H20 a12 12 0 0 1 -12 -12 V30 a12 12 0 0 1 12 -12 Z" fill="#fff" opacity=".14"/>
<path d="M90 56 H190 a12 12 0 0 1 12 12 V96 a12 12 0 0 1 -12 12 H174 V124 L154 108 H90 a12 12 0 0 1 -12 -12 V68 a12 12 0 0 1 12 -12 Z" fill="#00806A" stroke="#7FD1BC" stroke-width="2.5"/>
<g stroke="#7FD1BC" stroke-width="5" stroke-linecap="round"><path d="M24 36 H100" opacity=".7"/><path d="M24 50 H70" opacity=".7"/></g>
<g stroke="#fff" stroke-width="5" stroke-linecap="round"><path d="M96 74 H182"/><path d="M96 90 H150"/></g></svg>""",
    # ledger
    "log": f"""<svg width="210" height="130" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="decision ledger">
<rect x="46" y="10" width="118" height="112" rx="12" fill="#fff" opacity=".1"/>
<g stroke="#7FD1BC" stroke-width="5" stroke-linecap="round" opacity=".7"><path d="M66 38 H144"/><path d="M66 60 H144"/><path d="M66 82 H120"/></g>
<circle cx="150" cy="92" r="22" fill="#00806A" stroke="#7FD1BC" stroke-width="3"/><path d="M140 92 L148 100 L162 84" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>""",
    "empty": f"""<svg width="160" height="100" viewBox="0 0 210 130" xmlns="http://www.w3.org/2000/svg" aria-label="nothing here yet">
<rect x="30" y="20" width="150" height="96" rx="14" fill="#E7EFEC"/><path d="M52 50 H158 M52 72 H130 M52 94 H100" stroke="#B7CFC8" stroke-width="7" stroke-linecap="round"/>
<circle cx="160" cy="96" r="22" fill="#00806A"/><path d="M150 96 H170 M160 86 V106" stroke="#fff" stroke-width="5" stroke-linecap="round"/></svg>""",
}


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_logo() -> None:
    st.markdown(f"<div class='logo'>{LOGO}<b>Creator screening</b></div>"
                f"<div class='logosub'>Brand-safety review</div>", unsafe_allow_html=True)


def hero(kicker: str, title: str, sub: str, art: str, chips: list[str] | None = None) -> None:
    chip_html = "".join(f"<span class='chip'>{c}</span>" for c in chips or [] if c)
    st.markdown(f"<div class='hero'><div class='art'>{_ART[art]}</div><div class='kicker'>{kicker}</div>"
                f"<h1>{title}</h1><p>{sub}</p>"
                f"{'<div class=chips>' + chip_html + '</div>' if chip_html else ''}</div>", unsafe_allow_html=True)


def section(text: str) -> None:
    st.markdown(f"<div class='section'>{text}</div>", unsafe_allow_html=True)


def empty(title: str, text: str) -> None:
    st.markdown(f"<div class='empty'>{_ART['empty']}<b>{title}</b>{text}</div>", unsafe_allow_html=True)


def pill(label: str, level: int | None) -> str:
    return f"<span class='pill l{level or 1}'>{label}</span>"
