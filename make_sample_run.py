"""Build a fictional sample run (no real people, no API calls) so the review GUI can be
demonstrated without credits or network. Writes runs/<timestamp>.json and placeholder
evidence frames. Usage: python3 make_sample_run.py"""
import json, random
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
random.seed(7)
CATS = {
    "partying": ("Party energy", "club or party scenes, dancing crowds, nightlife. A calm dinner does not count"),
    "drinking": ("Alcohol", "someone consuming alcohol or alcoholic drinks promoted. A bottle in the background does not count"),
    "violence": ("Violence", "fighting, weapons, aggressive behaviour. Sports and play-fighting do not count"),
    "loud_tone": ("Loud tone", "shouting, chaotic or frantic editing at odds with a calm, quiet-luxury look"),
}
CREATORS = {  # handle -> {category: [(level, observation, frame label)]}
    "sample.maya": {"partying": [(3, "Video frame 3 shows a packed club with a dancing crowd, strobe lighting and people jumping.", "Video frame 3"),
                                 (2, "Slide 2 shows a rooftop party with a DJ and a crowd.", "Slide 2")],
                    "drinking": [(2, "Video frame 5 shows the creator holding a champagne bottle while spraying it.", "Video frame 5")]},
    "sample.theo": {"violence": [(3, "Video frame 2 shows two men trading punches in a street fight.", "Video frame 2")],
                    "loud_tone": [(2, "Rapid cuts with shouting over loud music throughout the video.", "Video frame 4")]},
    "sample.ines": {"drinking": [(1, "Video frame 6 shows a glass of wine on a dinner table.", "Video frame 6")]},
    "sample.noor": {"partying": [(2, "Video frame 4 shows a crowded festival crowd dancing at night.", "Video frame 4")]},
    "sample.luca": {},
    "sample.zoe": {"loud_tone": [(1, "Slightly energetic voiceover, otherwise calm.", "Video frame 1")]},
    "sample.ravi": {},
    "sample.elena": {"drinking": [(3, "Video frame 3 shows several people taking shots at a bar, one visibly drunk.", "Video frame 3")],
                     "partying": [(3, "Video frame 5 shows a crowded bar party with loud music.", "Video frame 5")]},
}
ev = ROOT / "reports" / "demo-sample-evidence"
ev.mkdir(parents=True, exist_ok=True)
per_post, n = [], 0
for h, cats in CREATORS.items():
    flagged = {}
    for cat, items in cats.items():
        for lvl, obs, label in items:
            flagged.setdefault(len(flagged), {})[cat] = (lvl, obs, label)
    posts = list(flagged.values()) + [{}] * (6 - len(flagged))
    for pd_ in posts:
        n += 1
        code = f"DEMO{n:04d}"
        levels = {c: v[0] for c, v in pd_.items()}
        obs = {c: v[1] for c, v in pd_.items()}
        thumbs = []
        for c, (lvl, o, label) in list(pd_.items())[:2]:
            im = Image.new("RGB", (540, 720), (random.randint(40, 120),) * 3)
            dr = ImageDraw.Draw(im)
            for i in range(0, 720, 24):
                dr.rectangle([0, i, 540, i + 12], fill=tuple(random.randint(30, 150) for _ in range(3)))
            dr.text((20, 20), f"SAMPLE FRAME - fictional\n{label}\n{c}", fill="white")
            f = ev / f"{code}-{len(thumbs) + 1}.jpg"
            im.save(f)
            thumbs.append(str(f.relative_to(ROOT)))
        per_post.append({"url": f"https://example.com/sample/{code}", "error": None, "hits": [], "evidence": {},
                         "thumbs": thumbs, "levels": levels, "observations": obs, "kind": "video",
                         "images": 7, "input_tokens": 9000, "output_tokens": 120, "profile": h})
job = {"name": "demo-quiet-luxury", "brand": "Sample Brand", "campaign": "Quiet luxury launch", "notes": None,
       "months_lookback": 4, "videos_only": True, "vision_model": "claude-haiku-4-5", "default_min_level": "heavy",
       "categories": {k: {"label": l, "description": d, "text_only": False, "levels": None, "min_level": "heavy"}
                      for k, (l, d) in CATS.items()},
       "competitors": ["RivalCo"], "review_brands": []}
run = {"started": datetime.now().isoformat(timespec="seconds"), "profiles": list(CREATORS), "job": job,
       "settings": {"vision_model": "claude-haiku-4-5"}, "posts": len(per_post), "posts_failed": 0,
       "posts_flagged": sum(1 for p in per_post if p["levels"]), "vision_cost_usd": 0.0, "per_post": per_post}
out = ROOT / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
out.write_text(json.dumps(run, indent=1))
print("wrote", out)
