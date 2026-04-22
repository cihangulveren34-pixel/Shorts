"""
binaural_script_gen.py — Binaural beats + math geometry Shorts için Gemini metadata üretici.

freq_script_gen.py'deki _call_gemini, _extract_json, generate_localizations reuse edilir.
Sadece PROMPT_TEMPLATE ve generate_binaural_script() yeni.
"""

import os
import json
import random

from freq_script_gen import (
    _call_gemini,
    _extract_json,
    generate_localizations,
)


PROMPT_TEMPLATE = """You are a YouTube Shorts expert specializing in sacred geometry, mathematics, and binaural beats meditation content.

Generate viral metadata for a YouTube Short that combines mesmerizing math animations with binaural beats:

Math Animation: {math_type_display}
Binaural Beat: {beat_hz} Hz ({beat_band} wave)
Carrier Frequency: {carrier_hz} Hz
Key Benefit: {benefit}
Short Benefit Label: {short_benefit}
Mood: {mood}

HOOK INSPIRATION (pick or remix the best one):
{hooks_str}

RULES:
- title: ≤60 chars. Format: "{math_type_display} + {beat_hz} Hz {beat_band_cap} | {short_benefit}" or similar viral format.
  Example: "Fibonacci Spiral + 2 Hz Delta | Deep Sleep"
- hook_line: The SINGLE most compelling line shown on screen. ≤12 words. Must reference the math pattern AND the brain benefit. Dramatic, scroll-stopping.
- hook_subtext: Small subtext under hook_line. ≤8 words. Creates urgency or curiosity. Can be empty string.
- thumbnail_text: 2-4 WORD CAPS for thumbnail. Examples: "SPIRAL SLEEP", "FRACTAL FOCUS", "SACRED GEOMETRY"
- cta_line: 1 sentence for end screen. Example: "Follow for daily sacred geometry meditations."
- description: 80-120 word SEO-optimized YouTube description. Mention the math pattern, Hz frequency, brainwave type, and benefits. End with relevant hashtags on new lines.
- tags: 10-15 relevant YouTube tags. Include math type, Hz, brainwave band, "binaural beats", "sacred geometry", "meditation", specific benefit keywords.

Output ONLY valid JSON:
{{
  "title": "...",
  "hook_line": "...",
  "hook_subtext": "...",
  "thumbnail_text": "...",
  "cta_line": "...",
  "description": "...",
  "tags": ["...", "..."]
}}
"""

MATH_TYPE_DISPLAY = {
    "fibonacci_spiral": "Fibonacci Spiral",
    "mandelbrot_zoom": "Mandelbrot Fractal Zoom",
    "sacred_flower": "Flower of Life",
    "golden_ratio": "Golden Ratio",
    "julia_set": "Julia Set",
    "metatron_cube": "Metatron's Cube",
    "sierpinski": "Sierpinski Triangle",
    "koch_snowflake": "Koch Snowflake",
    "penrose_tiling": "Penrose Tiling",
    "lissajous": "Lissajous Curve",
}


def generate_binaural_script(topic: dict) -> dict:
    """
    Binaural beats + math geometry konusu icin Gemini metadata uretir.

    Args:
        topic: binaural_topic_pool.json'dan bir kayit

    Returns:
        Uretilen metadata dict
    """
    math_type = topic["math_type"]
    math_display = MATH_TYPE_DISPLAY.get(math_type, math_type.replace("_", " ").title())
    beat_band = topic["beat_band"]
    hooks_str = "\n".join(f"- {h}" for h in topic.get("hooks", []))

    prompt = PROMPT_TEMPLATE.format(
        math_type_display=math_display,
        beat_hz=topic["beat_hz"],
        beat_band=beat_band,
        beat_band_cap=beat_band.capitalize(),
        carrier_hz=topic["carrier_hz"],
        benefit=topic["benefit"],
        short_benefit=topic["short_benefit"],
        mood=topic["mood"],
        hooks_str=hooks_str,
    )

    print(f"[binaural_script] {math_display} + {topic['beat_hz']} Hz {beat_band} icin Gemini cagriliyor...")
    raw = _call_gemini(prompt)
    script = _extract_json(raw)

    # Eksik alan varsa topic pool'dan default al
    script.setdefault("title", topic["title_name"])
    script.setdefault("hook_line", random.choice(topic["hooks"]))
    script.setdefault("hook_subtext", "")
    script.setdefault("thumbnail_text", topic["short_benefit"].upper())
    script.setdefault("cta_line", "Follow for daily sacred geometry meditations.")
    script.setdefault("tags", topic["tags"])
    script.setdefault("description", topic["description"])

    # Topic meta bilgilerini ekle
    script["math_type"] = math_type
    script["beat_hz"] = topic["beat_hz"]
    script["beat_band"] = beat_band
    script["carrier_hz"] = topic["carrier_hz"]
    script["short_benefit"] = topic["short_benefit"]
    script["mood"] = topic["mood"]

    print(f"[binaural_script] Baslik: {script['title']}")
    print(f"[binaural_script] Hook: {script['hook_line']}")
    return script


def save_binaural_script(script: dict, path: str = "output/binaural_script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[binaural_script] Script kaydedildi: {path}")
