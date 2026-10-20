"""Central configuration. Edit values here or override via .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Credentials ---
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Paths ---
ROOT = Path(__file__).parent
PROFILES_FILE = ROOT / "profiles.txt"
CACHE_DIR = ROOT / "cache"          # raw scraped JSON, cached per profile
VIDEO_DIR = ROOT / "cache" / "videos"
# Report file name without extension (.html/.csv/.xlsx are written next to
# each other). Set REPORT_NAME per job, e.g. REPORT_NAME=reports/acme-2026-10,
# so one job's reports never overwrite another's.
REPORT_NAME = os.getenv("REPORT_NAME", "influencer_report")
OUTPUT_HTML = ROOT / f"{REPORT_NAME}.html"

# --- Scraping ---
# Apify actor that scrapes public Instagram profiles/posts.
APIFY_ACTOR = "apify/instagram-scraper"
# Only analyze posts from the last N months (30-day months); set per job.
MONTHS_LOOKBACK = int(os.getenv("MONTHS_LOOKBACK", "12"))
MAX_POSTS_PER_PROFILE = 200         # safety cap per profile

# --- Content vision detection ---
# Vision model, set per job with VISION_MODEL=<id>. Each model needs an entry
# in VISION_MODELS: its price (USD per million tokens; images are billed as
# input) and the extra request options it accepts.
VISION_MODEL = os.getenv("VISION_MODEL", "claude-sonnet-4-5")
VISION_MODELS = {
    # temperature=0 so the same frames give the same flags on every run.
    "claude-sonnet-4-5": {"price_in": 3.00, "price_out": 15.00,
                          "max_tokens": 1000, "options": {"temperature": 0}},
    # Rejects temperature (results can vary slightly run to run) and thinks by
    # default. Tested 2026-10-12 against 4.5: medium effort found the same
    # ot.lorena reference flags and paid pizza posts as low, with fewer
    # borderline flags, at the same cost (~$0.018/video).
    # max_tokens covers thinking plus the JSON reply.
    # Cheaper tier (about 3x less per image than Sonnet 4.5). Prices are Anthropic's
    # list prices when added - confirm on the pricing page. Quality on our
    # categories is being tested against the ot.lorena reference flags.
    "claude-haiku-4-5": {"price_in": 1.00, "price_out": 5.00,
                         "max_tokens": 1000, "options": {"temperature": 0}},
    "claude-sonnet-5-5": {"price_in": 2.00, "price_out": 10.00,
                          "max_tokens": 4000, "options": {"output_config": {"effort": "medium"}}},
}
FRAMES_PER_VIDEO = 6                # evenly-sampled frames sent to the model
FRAME_MAX_WIDTH = 768               # downscale frames/photos before upload (px)
# Also send a video's cover image (the thumbnail the creator picked, often with
# title text) - one extra image per video.
INCLUDE_VIDEO_COVER = True
# Frames per video slide inside a carousel. Every slide of a carousel is
# checked (Instagram allows up to 20), photos as-is, videos as this many frames.
FRAMES_PER_CAROUSEL_VIDEO = 3
# Cap on videos analyzed per profile - None means analyze every video. Set to
# a small number under time pressure to get thin-but-complete coverage across
# every profile instead of full coverage of only a few (download bandwidth is
# the bottleneck, not frame count, so this is the only lever that actually
# reduces total time). Videos are taken in scrape order (most recent first).
MAX_VISION_POSTS_PER_PROFILE = None
# Per job, VIDEOS_ONLY=1 sends only videos/reels to the vision pass (no photos
# or carousels): far fewer posts to analyze, and the brand-deal text pass is
# unaffected. Default is off - photos and carousels are checked too.
VIDEOS_ONLY = os.getenv("VIDEOS_ONLY", "").lower() in ("1", "true", "yes")

# --- Content categories (vision pass) ---
# What the model checks each video for, as named sets; pick one per job with
# CATEGORY_SET=<name>. "description" is sent to the model as the definition,
# so say what counts and what doesn't. "text_only" categories can only be
# judged from on-screen text and the caption (there is no audio yet); the
# report says so.
CATEGORY_SETS = {
    "standard": {
        "drinking": {"label": "Drinking", "color": "#c0392b", "text_only": False,
                     "description": "someone consuming alcohol, or alcoholic drinks (beer, "
                                    "wine, cocktails, spirits, champagne) clearly visible"},
        "smoking": {"label": "Smoking", "color": "#8e44ad", "text_only": False,
                    "description": "cigarettes, cigars, vaping, or smoking-related products"},
        "partying": {"label": "Partying", "color": "#d35400", "text_only": False,
                     "description": "club/party scene, crowds dancing, nightlife, heavy "
                                    "celebration"},
        "gambling": {"label": "Gambling", "color": "#16704a", "text_only": False,
                     "description": "casino, cards for money, slot machines, betting, poker chips"},
        "swearing": {"label": "Swearing", "color": "#2c3e50", "text_only": True,
                     "description": "profanity in on-screen text or in the caption"},
    },
    "pizza": {
        "violence": {"label": "Violence", "color": "#c0392b", "text_only": False,
                     "description": "fighting, assault, weapons used or brandished "
                                    "threateningly, blood or injury, graphic or threatening "
                                    "violence. Cartoon slapstick or toy weapons in play do "
                                    "not count"},
        "nudity": {"label": "Nudity", "color": "#8e44ad", "text_only": False,
                   "description": "nudity or near-nudity (exposed genitals, buttocks or "
                                  "nipples), or sexual or sexually suggestive content. "
                                  "Ordinary swimwear at a beach or pool does not count by "
                                  "itself"},
        "partying": {"label": "Partying", "color": "#d35400", "text_only": False,
                     "description": "club/party scene, crowds dancing, nightlife, heavy "
                                    "celebration"},
        "swearing": {"label": "Swearing", "color": "#2c3e50", "text_only": True,
                     "description": "profanity in on-screen text or in the caption"},
        "racism": {"label": "Racism", "color": "#7b241c", "text_only": True,
                   "description": "racist slurs, jokes, stereotypes or hostility toward a race "
                                  "or ethnicity, in on-screen text or in the caption"},
        "sexism": {"label": "Sexism", "color": "#6c3483", "text_only": True,
                   "description": "sexist slurs, jokes, stereotypes or demeaning statements "
                                  "about a sex or gender, in on-screen text or in the caption"},
        "pizza_sponsorship": {
            "label": "Pizza sponsorship", "color": "#b9770e", "text_only": False,
            "description": "paid, gifted or promoted pizza content: a pizza brand, pizzeria or "
                           "pizza product being advertised or promoted (e.g. #ad/#sponsored/"
                           "#gifted/partner/discount code/link to order in the caption, a "
                           "brand's logo or packaging shown as a promotion, or the video is "
                           "plainly an ad). Just eating, cooking or reviewing pizza with no "
                           "sign of payment, gifting or promotion does NOT count"},
    },
    # Calm, quiet-luxury brand direction: flag party energy, alcohol and
    # violence (brand-safety history), and a loud visual tone that clashes.
    "quiet_luxury": {
        "partying": {"label": "Party energy", "color": "#d35400", "text_only": False,
                     "description": "high-energy party content: club/party scenes, crowds "
                                    "dancing, nightlife, heavy celebration, festival or "
                                    "rave-style atmosphere. A quiet dinner or a small calm "
                                    "gathering does not count"},
        "drinking": {"label": "Alcohol", "color": "#c0392b", "text_only": False,
                     "description": "someone consuming alcohol, or alcoholic drinks (beer, "
                                    "wine, cocktails, spirits, champagne) clearly visible or "
                                    "promoted. A bar shelf blurred in the background does not "
                                    "count by itself"},
        "violence": {"label": "Violence", "color": "#7b241c", "text_only": False,
                     "description": "fighting, assault, weapons used or brandished "
                                    "threateningly, blood or injury, graphic or threatening "
                                    "violence. Cartoon slapstick or toy weapons in play do "
                                    "not count"},
        "loud_tone": {"label": "Loud visual tone", "color": "#6c3483", "text_only": False,
                      "description": "a visual style that clashes with a calm, quiet-luxury "
                                     "look: frantic or chaotic energy, neon or strongly "
                                     "saturated club-style lighting, cluttered or garish "
                                     "settings, shouting or clickbait-style presentation, "
                                     "loud hype aesthetics. Calm, minimal, softly lit, "
                                     "neutral or warm-toned content does not count; an "
                                     "ordinary busy food market or travel scene is not loud "
                                     "by itself"},
    },
}
CATEGORY_SET = os.getenv("CATEGORY_SET", "standard")

# --- Sensitivity (per brand/job) ---
# The model rates each category 0-3 for every post (0 none, 1 incidental,
# 2 notable, 3 heavy) and says why. A post is FLAGGED for a category only when
# its level reaches that category's minimum for this job. Every observation is
# saved either way, so a brand's sensitivity can be changed later with
# rethreshold.py without re-analyzing anything.
LEVELS = {"incidental": 1, "notable": 2, "heavy": 3}
LEVEL_NAMES = {v: k for k, v in LEVELS.items()}
# Unless a job says otherwise, only heavy cases count as a flag.
DEFAULT_MIN_LEVEL = "heavy"


def _parse_min_levels(spec: str) -> dict:
    """MIN_LEVELS="drinking=notable,swearing=incidental" -> {"drinking": 2, ...}"""
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        cat, _, lvl = part.partition("=")
        if lvl.strip() not in LEVELS:
            raise SystemExit(f"MIN_LEVELS: '{part}' - level must be one of {list(LEVELS)}")
        out[cat.strip()] = LEVELS[lvl.strip()]
    return out


# Per-job overrides, e.g. MIN_LEVELS="drinking=notable,violence=notable".
MIN_LEVELS = _parse_min_levels(os.getenv("MIN_LEVELS", ""))

# What each level means for a category, so the model rates consistently.
LEVEL_NOTES = {
    "drinking": {"incidental": "a glass of wine or a drink at a meal, a bottle on a shelf or in the background",
                 "notable": "drinking is clearly the focus of part of the post (cocktails at a bar, a toast, several drinks)",
                 "heavy": "heavy drinking: visibly drunk, drinking games, many drinks, alcohol is the point of the post"},
    "partying": {"incidental": "a small celebration, a birthday dinner, a few friends at a bar",
                 "notable": "a lively party or night out with music and a group, but not a club or crowd scene",
                 "heavy": "a club, rave or festival crowd, heavy nightlife, dancing crowds, wild celebration"},
    "violence": {"incidental": "mild roughhousing, a sports tackle, violence in a movie clip or game",
                 "notable": "a real or staged fight, a weapon displayed, visible injury",
                 "heavy": "graphic or sustained violence, assault, blood, threatening use of a weapon"},
    "swearing": {"incidental": "a mild word such as damn or hell",
                 "notable": "clear profanity",
                 "heavy": "strong or repeated profanity, slurs, aggressive language"},
    "smoking": {"incidental": "a cigarette or vape visible briefly in the background",
                "notable": "someone smoking or vaping on camera",
                "heavy": "smoking is a feature of the post or promoted"},
    "gambling": {"incidental": "a lottery ticket or a casino seen in passing",
                 "notable": "someone gambling on camera",
                 "heavy": "gambling is promoted or the focus of the post"},
    "loud_tone": {"incidental": "one busy or colourful moment in an otherwise calm post",
                  "notable": "a clearly loud, high-energy or cluttered style through much of the post",
                  "heavy": "the whole post is frantic, garish or hype-driven, the opposite of calm luxury"},
    "nudity": {"incidental": "swimwear at a beach or pool",
               "notable": "revealing or suggestive clothing or poses",
               "heavy": "nudity or explicit sexual content"},
}
for _set in CATEGORY_SETS.values():
    for _key, _cat in _set.items():
        _cat.setdefault("levels", LEVEL_NOTES.get(_key))


def min_level(cat: str) -> int:
    """The level (1-3) at which `cat` counts as a flag for this job."""
    return MIN_LEVELS.get(cat, LEVELS[DEFAULT_MIN_LEVEL])


CONTENT_CATEGORIES = CATEGORY_SETS[CATEGORY_SET]

# --- Parallelism ---
# Profiles scraped at once in the text pass (each is a separate Apify run).
SCRAPE_WORKERS = 4
# Videos processed at once in the vision pass, shared across all profiles.
# Each worker downloads, samples frames and makes one vision call. Too high
# and downloads split the bandwidth and hit MAX_DOWNLOAD_SECONDS, or vision
# calls hit the API rate limit.
VISION_WORKERS = 8
# SDK retries (with backoff) for rate-limited or failed vision calls.
API_MAX_RETRIES = 5

# --- Brand-deal detection ---
# Caption signals that indicate a paid partnership.
DEAL_HASHTAGS = ["#ad", "#sponsored", "#paidpartnership", "#partner",
                 "#collab", "#gifted", "#promotion", "#brandambassador"]
DEAL_PHRASES = ["paid partnership", "paid promotion", "sponsored by",
                "in partnership with", "thanks to", "use my code",
                "discount code", "link in bio", "brand ambassador"]

# --- Text pass (fast pre-screen, runs before any vision/LLM call) ---
# One competitor brand/handle per line; profiles that mention one get
# auto-rejected before the vision pass. This is the only text-based reject -
# content categories (drinking, smoking, etc.) are decided by the vision
# pass only, since caption keyword matching for those is too unreliable
# (e.g. "vodka" matching inside "spicy vodka pizza").
COMPETITOR_BRANDS_FILE = ROOT / "competitor_brands.txt"
# Brands whose deals are flagged for human review in the text pass - never
# auto-rejected. One brand or term per line; a deal post is flagged when a
# term appears in a mentioned/tagged handle or as a whole word in its caption.
# Set per job, e.g. REVIEW_BRANDS_FILE=pizza_brands.txt (create it for the job;
# not kept in the repo). Missing file = none.
REVIEW_BRANDS_FILE = ROOT / os.getenv("REVIEW_BRANDS_FILE", "review_brands.txt")

# --- Run metrics ---
# Every run writes runs/<timestamp>.json: phase times, per-video timings,
# token usage, cost and per-video results, so runs can be compared.
RUNS_DIR = ROOT / "runs"
PRICE_INPUT_PER_MTOK = VISION_MODELS[VISION_MODEL]["price_in"]
PRICE_OUTPUT_PER_MTOK = VISION_MODELS[VISION_MODEL]["price_out"]

# --- Timing estimate ---
# Rough seconds per video (download + frame sample + vision call), used to
# estimate vision-pass duration after the text pass completes.
EST_SECONDS_PER_POST = 12