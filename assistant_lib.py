"""Setup assistant: a chat that fills in a job (draft) through one tool, `update_job`.

Streamlit-free so it can be tested alone. The model never writes files - it only edits
the in-memory draft; the GUI saves it through the same validation as the Jobs page.
"""
from __future__ import annotations

import os
import re

LEVELS = ["incidental", "notable", "heavy"]
MODELS = ["claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-5-5"]
ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "claude-haiku-4-5")

TOP_KEYS = {"name", "brand", "campaign", "profiles", "months_lookback", "videos_only", "vision_model",
            "default_min_level", "competitors", "review_brands", "frames_per_video",
            "max_posts_per_profile", "max_vision_posts_per_profile", "include_video_cover"}
INT_RANGES = {"months_lookback": (1, 36), "frames_per_video": (1, 12),
              "max_posts_per_profile": (10, 500), "max_vision_posts_per_profile": (1, 1000)}
LIST_KEYS = {"profiles", "competitors", "review_brands"}

SYSTEM = """You are the setup assistant inside a brand-safety screening tool. A talent company \
screens Instagram creators for a brand: the tool scrapes recent posts, rejects creators who \
mention competitor brands, and has a vision model rate each post 0-3 (none / incidental / notable / \
heavy) per content category. A post is flagged at a category's level or above; a human reviews every \
flag. Your job is to help the user configure ONE screening job by talking to them, and to record \
every decision with the update_job tool.

Settings you can change:
- name (short slug), brand, campaign
- profiles: Instagram handles to screen
- months_lookback (1-36): how far back to look
- videos_only: reels/videos only - cheaper, skips photos and carousels
- vision_model: claude-haiku-4-5 (default, cheapest, ~$0.01/post), claude-sonnet-4-5 (~$0.03/post, \
more careful), claude-sonnet-5-5
- default_min_level: incidental | notable | heavy. Default heavy - brands usually only care about \
heavy cases (a glass of wine is not a party scene)
- categories: what to look for. Each has a key, label, description (what counts AND what doesn't), \
optional min_level override, optional text_only (judged from on-screen text/caption only). \
Optional levels: concrete examples for incidental/notable/heavy, which makes the rating more precise.
- competitors: brand names; a creator mentioning one is auto-rejected (the only auto-reject)
- review_brands: brands to flag for a person, never auto-reject
- Advanced: frames_per_video (1-12, default 6; more = better coverage, higher cost), \
max_posts_per_profile (cap on scraped posts, default 200), max_vision_posts_per_profile (cap on \
posts sent to the model, default none), include_video_cover (default true)

How to behave:
- Be brief and conversational; ask one or two things at a time, in a sensible order: brand and \
campaign, creators, what to watch for and how strict, competitors, then lookback/reels/model. Offer \
the advanced settings only when relevant (cost, speed) or when asked.
- When the user states something, call update_job right away with just what changed, then confirm in \
a sentence. Never claim a setting is saved unless you called the tool and it succeeded.
- Don't invent creators, brands or facts. If the user is vague, propose a concrete default and ask.
- Write category descriptions that say what counts and what does not.
- The current draft is given to you on every turn. If the tool returns an error, fix it or ask.
- You can't run the screening or save the job; the user does that with the buttons beside the chat."""

TOOL = {
    "name": "update_job",
    "description": "Change the draft job. Include only the fields that change. Lists replace the "
                   "whole list; categories are merged by key.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"}, "brand": {"type": "string"}, "campaign": {"type": "string"},
            "profiles": {"type": "array", "items": {"type": "string"}},
            "months_lookback": {"type": "integer"}, "videos_only": {"type": "boolean"},
            "vision_model": {"type": "string", "enum": MODELS},
            "default_min_level": {"type": "string", "enum": LEVELS},
            "competitors": {"type": "array", "items": {"type": "string"}},
            "review_brands": {"type": "array", "items": {"type": "string"}},
            "frames_per_video": {"type": "integer"},
            "max_posts_per_profile": {"type": "integer"},
            "max_vision_posts_per_profile": {"type": ["integer", "null"]},
            "include_video_cover": {"type": "boolean"},
            "categories": {
                "type": "object",
                "description": "key -> category; keys are lowercase_with_underscores",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"}, "description": {"type": "string"},
                        "min_level": {"type": "string", "enum": LEVELS},
                        "text_only": {"type": "boolean"},
                        "levels": {"type": "object", "properties": {l: {"type": "string"} for l in LEVELS}},
                    },
                },
            },
            "remove_categories": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def clean_handle(h: str) -> str:
    h = re.sub(r"^https?://(www\.)?instagram\.com/", "", str(h).strip())
    return re.sub(r"[/?#\s].*$", "", h).lstrip("@")


def apply_update(draft: dict, upd: dict) -> tuple[dict, list[str]]:
    """Return (new draft, problems). Nothing changes if there are problems."""
    new = {**draft, "categories": {k: dict(v) for k, v in (draft.get("categories") or {}).items()}}
    problems: list[str] = []
    for k, v in upd.items():
        if k in ("categories", "remove_categories"):
            continue
        if k not in TOP_KEYS:
            problems.append(f"unknown field '{k}'")
        elif k in LIST_KEYS:
            if not isinstance(v, list):
                problems.append(f"'{k}' must be a list")
                continue
            items = [clean_handle(x) if k == "profiles" else str(x).strip() for x in v]
            new[k] = list(dict.fromkeys(x for x in items if x))
        elif k in INT_RANGES:
            lo, hi = INT_RANGES[k]
            if v is None and k == "max_vision_posts_per_profile":
                new.pop(k, None)
            elif isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                problems.append(f"'{k}' must be a whole number from {lo} to {hi}")
            else:
                new[k] = v
        elif k == "vision_model" and v not in MODELS:
            problems.append(f"vision_model must be one of {MODELS}")
        elif k == "default_min_level" and v not in LEVELS:
            problems.append(f"default_min_level must be one of {LEVELS}")
        elif k in ("videos_only", "include_video_cover"):
            new[k] = bool(v)
        elif k == "name":
            slug = re.sub(r"[^a-z0-9_-]+", "-", str(v).lower()).strip("-")
            if slug:
                new[k] = slug
            else:
                problems.append("name needs letters or numbers")
        else:
            new[k] = v
    for key, c in (upd.get("categories") or {}).items():
        k = re.sub(r"[^a-z0-9_]+", "_", str(key).lower()).strip("_")
        if not k or not isinstance(c, dict):
            problems.append(f"bad category '{key}'")
            continue
        cur = new["categories"].get(k, {})
        merged = {**cur, **{a: b for a, b in c.items() if a in ("label", "description", "min_level", "text_only", "levels")}}
        if merged.get("min_level") and merged["min_level"] not in LEVELS:
            problems.append(f"category '{k}': min_level must be one of {LEVELS}")
            continue
        if not str(merged.get("description", "")).strip():
            problems.append(f"category '{k}' needs a description saying what counts and what doesn't")
            continue
        merged.setdefault("label", k.replace("_", " ").title())
        new["categories"][k] = merged
    for key in upd.get("remove_categories") or []:
        if new["categories"].pop(str(key), None) is None:
            problems.append(f"no category '{key}' to remove")
    return (draft, problems) if problems else (new, [])


def missing(draft: dict) -> list[str]:
    """What still has to be filled in before the job can be saved and run."""
    out = []
    if not draft.get("name"):
        out.append("job name")
    if not draft.get("profiles"):
        out.append("creators")
    if not draft.get("categories"):
        out.append("what to look for (at least one category)")
    return out


def summary(draft: dict) -> str:
    """The draft as the model sees it each turn."""
    import json
    return json.dumps({k: v for k, v in draft.items() if v not in (None, [], {})}, indent=1)


def friendly_error(e: Exception) -> str:
    s = str(e).lower()
    if "credit balance" in s:
        return "The assistant can't answer: the Anthropic account is out of credit. Add credit, or use the Jobs page."
    if "authentication" in s or "api key" in s or "permission" in s:
        return "The assistant can't answer: the Anthropic API key is missing or not accepted. Use the Jobs page meanwhile."
    if "timeout" in s or "connection" in s:
        return "The assistant couldn't reach the API (network). Try again, or use the Jobs page."
    return f"The assistant hit an error: {str(e)[:200]}"


def chat_turn(client, messages: list[dict], draft: dict, model: str = ASSISTANT_MODEL,
              max_rounds: int = 6) -> tuple[list[dict], dict, str]:
    """Run one user turn. `messages` ends with the user's message. Returns (messages, draft, reply).
    The model may call update_job several times; each result is checked before it is kept."""
    msgs = list(messages)
    for _ in range(max_rounds):
        resp = client.messages.create(
            model=model, max_tokens=1500, tools=[TOOL],
            system=SYSTEM + "\n\nCurrent draft job:\n" + summary(draft),
            messages=msgs)
        blocks = [{k: v for k, v in (b.model_dump() if hasattr(b, "model_dump") else dict(b)).items()
                   if v is not None} for b in resp.content]
        msgs.append({"role": "assistant", "content": blocks})
        calls = [b for b in blocks if b.get("type") == "tool_use"]
        if not calls:
            return msgs, draft, "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        results = []
        for c in calls:
            draft, problems = apply_update(draft, c.get("input") or {})
            results.append({"type": "tool_result", "tool_use_id": c["id"],
                            "content": ("Not applied: " + "; ".join(problems)) if problems else "Applied.",
                            "is_error": bool(problems)})
        msgs.append({"role": "user", "content": results})
    return msgs, draft, "(I got stuck updating the job - please tell me again what you'd like.)"
