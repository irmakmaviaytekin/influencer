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
OUTPUT_CSV = ROOT / "influencer_report.csv"

# --- Scraping ---
# Apify actor that scrapes public Instagram profiles/posts.
APIFY_ACTOR = "apify/instagram-scraper"
MONTHS_LOOKBACK = 12                # only analyze posts from the last N months
MAX_POSTS_PER_PROFILE = 200         # safety cap per profile

# --- Alcohol vision detection ---
VISION_MODEL = "claude-sonnet-4-5"  # any Anthropic vision-capable model
FRAMES_PER_VIDEO = 6                # evenly-sampled frames sent to the model
FRAME_MAX_WIDTH = 768               # downscale frames before upload (px)

# --- Brand-deal detection ---
# Caption signals that indicate a paid partnership.
DEAL_HASHTAGS = ["#ad", "#sponsored", "#paidpartnership", "#partner",
                 "#collab", "#gifted", "#promotion", "#brandambassador"]
DEAL_PHRASES = ["paid partnership", "paid promotion", "sponsored by",
                "in partnership with", "thanks to", "use my code",
                "discount code", "link in bio", "brand ambassador"]
