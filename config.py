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
MONTHS_LOOKBACK = 12                # only analyze posts from the last N months
MAX_POSTS_PER_PROFILE = 200         # safety cap per profile

# --- Content vision detection ---
VISION_MODEL = "claude-sonnet-4-5"  # any Anthropic vision-capable model
FRAMES_PER_VIDEO = 6                # evenly-sampled frames sent to the model
FRAME_MAX_WIDTH = 768               # downscale frames before upload (px)
# Cap on videos analyzed per profile - None means analyze every video. Set to
# a small number under time pressure to get thin-but-complete coverage across
# every profile instead of full coverage of only a few (download bandwidth is
# the bottleneck, not frame count, so this is the only lever that actually
# reduces total time). Videos are taken in scrape order (most recent first).
MAX_VIDEOS_PER_PROFILE = None

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
}
CATEGORY_SET = os.getenv("CATEGORY_SET", "standard")
CONTENT_CATEGORIES = CATEGORY_SETS[CATEGORY_SET]

# --- Parallelism ---
# Profiles scraped at once in the text pass (each is a separate Apify run).
SCRAPE_WORKERS = 4
# Videos processed at once in the vision pass, shared across all profiles.
# Each worker downloads, samples frames and makes one vision call. Too high
# and downloads split the bandwidth and hit MAX_DOWNLOAD_SECONDS, or vision
# calls hit the API rate limit.
VIDEO_WORKERS = 8
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
# Set per job, e.g. REVIEW_BRANDS_FILE=pizza_brands.txt. Missing file = none.
REVIEW_BRANDS_FILE = ROOT / os.getenv("REVIEW_BRANDS_FILE", "review_brands.txt")

# --- Run metrics ---
# Every run writes runs/<timestamp>.json: phase times, per-video timings,
# token usage, cost and per-video results, so runs can be compared.
RUNS_DIR = ROOT / "runs"
# USD per million tokens for VISION_MODEL (images are billed as input tokens).
# Update these if VISION_MODEL changes.
PRICE_INPUT_PER_MTOK = 3.00
PRICE_OUTPUT_PER_MTOK = 15.00

# --- Timing estimate ---
# Rough seconds per video (download + frame sample + vision call), used to
# estimate vision-pass duration after the text pass completes.
EST_SECONDS_PER_VIDEO = 12