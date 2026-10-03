"""Analysis: brand-deal detection (captions) and content flags (video vision).

Content flags checked from sampled video frames:
    drinking (alcohol), smoking, partying, gambling, swearing.
NOTE: the model only sees still frames, so "swearing" can only be caught when
profanity is visible in on-screen text/captions - spoken swearing is not detected.
"""
import base64
import json
import os
import re
import tempfile
import time

import cv2
import requests
import anthropic

import config

CONTENT_CATEGORIES = ["drinking", "smoking", "partying", "gambling", "swearing"]


# ---------------------------------------------------------------------------
# Brand deals
# ---------------------------------------------------------------------------
def detect_brand_deals(post: dict) -> dict:
    """Return {is_deal, signals, brands} inferred from a post's caption/metadata."""
    caption = (post.get("caption") or "").lower()
    signals = []

    if post.get("is_sponsored"):
        signals.append("IG paid-partnership label")

    for tag in config.DEAL_HASHTAGS:
        if tag in caption:
            signals.append(tag)

    for phrase in config.DEAL_PHRASES:
        if phrase in caption:
            signals.append(f'"{phrase}"')

    brands = set(post.get("mentions") or [])
    brands.update(post.get("tagged_users") or [])
    brands.update(re.findall(r"@([A-Za-z0-9_.]+)", caption))

    return {
        "is_deal": bool(signals),
        "signals": signals,
        "brands": sorted(b for b in brands if b),
    }


# ---------------------------------------------------------------------------
# Text pass: competitor screening (no LLM call)
# ---------------------------------------------------------------------------
def _word_match(text: str, phrase: str) -> bool:
    """Whole-word match for single words, plain substring for multi-word
    phrases (spaces already anchor those). Prevents things like "rave"
    matching inside "traveled"."""
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def detect_competitor(caption: str, brands: set[str], competitors: set[str]) -> str | None:
    """Return the matched competitor name if `caption`/`brands` reference one
    of `competitors` (case-insensitive), else None."""
    cap_lower = (caption or "").lower()
    for comp in competitors:
        if comp in brands or _word_match(cap_lower, comp):
            return comp
    return None


# ---------------------------------------------------------------------------
# Video frame sampling
# ---------------------------------------------------------------------------
MAX_DOWNLOAD_SECONDS = 45  # hard wall-clock cap, independent of per-read timeouts


def _download_video(url: str) -> str | None:
    if not url:
        return None
    start = time.monotonic()
    try:
        r = requests.get(url, timeout=15, stream=True)
        r.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        for chunk in r.iter_content(chunk_size=1 << 16):
            # A connection that trickles data slowly (e.g. throttled by the
            # CDN) never hits requests' per-read timeout, so cap total time
            # explicitly instead of trusting timeout= alone.
            if time.monotonic() - start > MAX_DOWNLOAD_SECONDS:
                tmp.close()
                os.unlink(tmp.name)
                return None
            tmp.write(chunk)
        tmp.close()
    except requests.RequestException:
        return None
    return tmp.name


def _sample_frames(video_path: str, n: int) -> list[bytes]:
    """Return up to n evenly-spaced JPEG frames (downscaled) from the video."""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frames: list[bytes] = []
    if total <= 0:
        cap.release()
        return frames
    idxs = [int(total * i / (n + 1)) for i in range(1, n + 1)]
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if w > config.FRAME_MAX_WIDTH:
            scale = config.FRAME_MAX_WIDTH / w
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            frames.append(buf.tobytes())
    cap.release()
    return frames


# ---------------------------------------------------------------------------
# Content-flag detection
# ---------------------------------------------------------------------------
_CONTENT_PROMPT = (
    "You are reviewing sampled frames from a single social-media video. "
    "For each category below, decide if it is clearly present in the frames:\n"
    "- drinking: someone consuming alcohol, or alcoholic drinks (beer, wine, "
    "cocktails, spirits, champagne) clearly visible\n"
    "- smoking: cigarettes, cigars, vaping, or smoking-related products\n"
    "- partying: club/party scene, crowds dancing, nightlife, heavy celebration\n"
    "- gambling: casino, cards for money, slot machines, betting, poker chips\n"
    "- swearing: profanity visible in ON-SCREEN TEXT or captions "
    "(you cannot hear audio; judge text only)\n\n"
    "Respond with ONLY a strict JSON object, no prose:\n"
    '{"drinking":{"present":bool,"evidence":"short reason or empty"},'
    '"smoking":{"present":bool,"evidence":""},'
    '"partying":{"present":bool,"evidence":""},'
    '"gambling":{"present":bool,"evidence":""},'
    '"swearing":{"present":bool,"evidence":""}}'
)


def _empty_result() -> dict:
    return {cat: {"present": False, "evidence": ""} for cat in CONTENT_CATEGORIES}


def detect_content(post: dict, client: anthropic.Anthropic) -> dict:
    """Download the post's video, sample frames, flag the content categories.

    Returns {"error": str|None, "categories": {category: {"present": bool,
    "evidence": str}}}. `error` is set (and categories are all-empty/unreliable)
    when the video couldn't be downloaded or analyzed - this is distinct from a
    successful analysis that found nothing, and callers must not treat the two
    the same way (a download failure is not evidence of a clean profile).
    """
    video_url = post.get("video_url")
    if not video_url:
        return {"error": None, "categories": _empty_result()}

    path = _download_video(video_url)
    if not path:
        return {"error": "video download failed (link may have expired - try a fresh scrape)",
                "categories": _empty_result()}

    frames = _sample_frames(path, config.FRAMES_PER_VIDEO)
    if not frames:
        return {"error": "no frames extracted", "categories": _empty_result()}

    content = [{"type": "text", "text": _CONTENT_PROMPT}]
    for f in frames:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(f).decode(),
            },
        })

    try:
        msg = client.messages.create(
            model=config.VISION_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": content}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
    except Exception as e:  # noqa: BLE001 - surface errors in the report
        return {"error": f"vision error: {e}", "categories": _empty_result()}

    result = _empty_result()
    for cat in CONTENT_CATEGORIES:
        entry = parsed.get(cat) or {}
        if isinstance(entry, dict):
            result[cat] = {
                "present": bool(entry.get("present")),
                "evidence": str(entry.get("evidence", "")),
            }
        else:
            result[cat] = {"present": bool(entry), "evidence": ""}
    return {"error": None, "categories": result}