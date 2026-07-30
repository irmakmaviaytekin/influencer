"""Analysis: brand-deal detection (captions) and content flags (video vision).

Content flags checked from sampled video frames:
    drinking (alcohol), smoking, partying, gambling, swearing.
NOTE: the model only sees still frames, so "swearing" can only be caught when
profanity is visible in on-screen text/captions - spoken swearing is not detected.
"""
import base64
import json
import re
import tempfile

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
# Video frame sampling
# ---------------------------------------------------------------------------
def _download_video(url: str) -> str | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
    except requests.RequestException:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    for chunk in r.iter_content(chunk_size=1 << 16):
        tmp.write(chunk)
    tmp.close()
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


def _empty_result(note: str = "") -> dict:
    return {cat: {"present": False, "evidence": note} for cat in CONTENT_CATEGORIES}


def detect_content(post: dict, client: anthropic.Anthropic) -> dict:
    """Download the post's video, sample frames, flag the content categories.

    Returns {category: {"present": bool, "evidence": str}} for every category.
    """
    video_url = post.get("video_url")
    if not video_url:
        return _empty_result("no video")

    path = _download_video(video_url)
    if not path:
        return _empty_result("video download failed")

    frames = _sample_frames(path, config.FRAMES_PER_VIDEO)
    if not frames:
        return _empty_result("no frames extracted")

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
        return _empty_result(f"vision error: {e}")

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
    return result