"""Scrape Instagram posts for a profile via the Apify Instagram Scraper actor.

Results are cached to disk per profile so re-runs don't re-scrape (or re-spend).
Each post is normalized to a small dict the rest of the pipeline understands.
"""
import json
from datetime import datetime, timedelta, timezone

from apify_client import ApifyClient

import config


def _cache_path(username: str):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / f"{username}.json"


def _normalize(item: dict) -> dict:
    """Map an Apify post item to the fields we care about.

    The actor's field names vary slightly by version; we read defensively.
    """
    ts = item.get("timestamp")
    caption = item.get("caption") or ""
    video_url = item.get("videoUrl") or item.get("video_url") or ""
    return {
        "id": item.get("id") or item.get("shortCode") or "",
        "url": item.get("url") or "",
        "timestamp": ts,
        "type": item.get("type") or item.get("productType") or "",
        "caption": caption,
        "hashtags": item.get("hashtags") or [],
        "mentions": item.get("mentions") or [],
        "tagged_users": [u.get("username") for u in item.get("taggedUsers", []) if isinstance(u, dict)],
        "is_sponsored": bool(item.get("isSponsored") or item.get("paidPartnership")),
        "video_url": video_url,
        # Photo, video cover, or carousel cover image.
        "display_url": item.get("displayUrl") or "",
        "alt": item.get("alt") or "",
        # Carousel slides (photos and/or videos), in order.
        "children": [{"type": c.get("type") or "",
                      "display_url": c.get("displayUrl") or "",
                      "video_url": c.get("videoUrl") or "",
                      "alt": c.get("alt") or ""}
                     for c in item.get("childPosts") or [] if isinstance(c, dict)],
        "likes": item.get("likesCount"),
        "comments": item.get("commentsCount"),
    }


def _within_lookback(ts: str, cutoff: datetime) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt >= cutoff


def scrape_profile(username: str, use_cache: bool = True) -> list[dict]:
    """Return normalized posts for `username` from the last MONTHS_LOOKBACK months."""
    cache = _cache_path(username)
    if use_cache and cache.exists():
        raw = json.loads(cache.read_text())
    else:
        client = ApifyClient(config.APIFY_TOKEN)
        run_input = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "posts",
            "resultsLimit": config.MAX_POSTS_PER_PROFILE,
            "addParentData": False,
        }
        run = client.actor(config.APIFY_ACTOR).call(run_input=run_input)
        run_id = run["id"] if isinstance(run, dict) else run.id
        raw = list(client.run(run_id).dataset().iterate_items())
        # A misspelled, private or deleted profile returns no posts (or only
        # error items). Fail instead of caching it, so it shows up as a scrape
        # error rather than as a profile with nothing to flag.
        posts_raw = [i for i in raw if not i.get("error")]
        if not posts_raw:
            errors = {f'{i.get("error")}: {i.get("errorDescription", "")}'.strip(": ")
                      for i in raw if i.get("error")}
            raise RuntimeError("no posts returned"
                               + (f" ({'; '.join(sorted(errors))})" if errors else ""))
        raw = posts_raw
        cache.write_text(json.dumps(raw, indent=2, default=str))

    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * config.MONTHS_LOOKBACK)
    posts = [_normalize(i) for i in raw]
    return [p for p in posts if _within_lookback(p["timestamp"], cutoff)]