"""Analysis: brand-deal detection (captions) and alcohol detection (video vision)."""
import base64
import re
import tempfile

import cv2
import requests
import anthropic

import config


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

    # Brand candidates: @mentions and tagged accounts.
    brands = set(post.get("mentions") or [])
    brands.update(post.get("tagged_users") or [])
    # @mentions embedded in caption text.
    brands.update(re.findall(r"@([A-Za-z0-9_.]+)", caption))

    return {
        "is_deal": bool(signals),
        "signals": signals,
        "brands": sorted(b for b in brands if b),
    }


# ---------------------------------------------------------------------------
# Alcohol detection via video frames
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


_ALCOHOL_PROMPT = (
    "You are reviewing sampled frames from a single social-media video. "
    "Determine whether anyone is consuming alcohol OR whether alcoholic "
    "drinks (beer, wine, cocktails, spirits, champagne) are clearly visible. "
    "Respond with a strict JSON object, no prose:\n"
    '{"alcohol": true|false, "confidence": 0.0-1.0, "evidence": "short reason"}'
)


def detect_alcohol(post: dict, client: anthropic.Anthropic) -> dict:
    """Download the post's video, sample frames, ask the vision model about alcohol."""
    result = {"alcohol": None, "confidence": None, "evidence": ""}
    video_url = post.get("video_url")
    if not video_url:
        result["evidence"] = "no video"
        return result

    path = _download_video(video_url)
    if not path:
        result["evidence"] = "video download failed"
        return result

    frames = _sample_frames(path, config.FRAMES_PER_VIDEO)
    if not frames:
        result["evidence"] = "no frames extracted"
        return result

    content = [{"type": "text", "text": _ALCOHOL_PROMPT}]
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
            max_tokens=200,
            messages=[{"role": "user", "content": content}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        import json
        parsed = json.loads(text)
        result.update({
            "alcohol": bool(parsed.get("alcohol")),
            "confidence": parsed.get("confidence"),
            "evidence": parsed.get("evidence", ""),
        })
    except Exception as e:  # noqa: BLE001 - surface model/parse errors in output
        result["evidence"] = f"vision error: {e}"
    return result
