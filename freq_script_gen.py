"""
freq_script_gen.py — Solfeggio frekans videoları için Gemini ile metadata üretir.

Üretilen alanlar:
  - title: YouTube başlığı (≤60 karakter)
  - hook_line: Ekranda gösterilecek kısa hook metni (≤12 kelime, 1 satır)
  - hook_subtext: Hook altı küçük metin (opsiyonel, ≤8 kelime)
  - description: YouTube açıklaması (SEO optimized)
  - tags: YouTube etiketleri
  - thumbnail_text: Thumbnail'daki büyük metin (2-4 kelime caps)
  - cta_line: Video sonu CTA metni
"""

import os
import json
import random
import re
import time
import requests


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.0-flash"]


def _call_gemini(prompt: str) -> str:
    """Gemini API'yi çağırır, model bulunamazsa fallback dener."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY ortam değişkeni eksik.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 1024},
    }
    last_err = None
    for model in GEMINI_MODELS:
        url = GEMINI_API_BASE.format(model=model) + f"?key={api_key}"
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 404:
                    break  # Bu model yok, sonrakini dene
                resp.raise_for_status()
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 ** attempt)
    raise RuntimeError(f"Tüm Gemini modelleri başarısız: {last_err}")


def _extract_json(text: str) -> dict:
    """Metin içinden JSON bloğunu ayıklar."""
    # ```json ... ``` bloğu
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Direkt JSON
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"JSON bulunamadı:\n{text[:400]}")


PROMPT_TEMPLATE = """You are a YouTube Shorts optimization expert specializing in healing frequency and meditation content.

Generate viral metadata for a YouTube Short about this healing frequency:

Frequency: {hz} Hz
Name: {name}
Key Benefit: {benefit}
Mood: {mood}
Description: {description}

HOOK INSPIRATION (pick or remix the best one):
{hooks_str}

RULES:
- title: ≤60 chars. Format: "[Hz] Hz | [Benefit Keyword] | [Action Word]"
  Example: "528 Hz | DNA Repair | Listen Until The End"
- hook_line: The SINGLE most compelling line shown on screen. ≤12 words. Must start with "If you listen to this" or "This [Hz] Hz sound will" or similar.
  This is shown as large text overlay on the video.
- hook_subtext: Small subtext under hook_line. ≤8 words. Creates urgency or curiosity. Can be empty string.
- thumbnail_text: 2-4 WORD CAPS for thumbnail. Examples: "DNA REPAIR", "MIRACLE FREQUENCY", "FEEL THE SHIFT"
- cta_line: 1 sentence for end screen. Example: "Follow for daily healing frequencies."
- description: 80-120 word SEO-optimized YouTube description. Mention the Hz, benefits, timestamps if applicable. End with relevant hashtags on new lines.
- tags: 10-15 relevant YouTube tags (strings). Include the exact Hz number, "solfeggio", "healing frequency", "meditation", specific benefit keywords.

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


def generate_freq_script(topic: dict) -> dict:
    """
    Frekans konusu için Gemini metadata üretir.

    Args:
        topic: freq_topic_pool.json'dan bir kayıt

    Returns:
        Üretilen metadata dict
    """
    hz = topic["hz"]
    hooks_str = "\n".join(f"- {h}" for h in topic.get("hooks", []))

    prompt = PROMPT_TEMPLATE.format(
        hz=hz,
        name=topic["name"],
        benefit=topic["benefit"],
        mood=topic["mood"],
        description=topic["description"],
        hooks_str=hooks_str,
    )

    print(f"[freq_script_gen] {topic['name']} için Gemini çağrılıyor...")
    raw = _call_gemini(prompt)
    script = _extract_json(raw)

    # Eksik alan varsa topic pool'dan default al
    script.setdefault("title", topic["title_name"])
    script.setdefault("hook_line", random.choice(topic["hooks"]))
    script.setdefault("hook_subtext", "")
    script.setdefault("thumbnail_text", topic["short_benefit"].upper())
    script.setdefault("cta_line", "Follow for daily healing frequencies.")
    script.setdefault("tags", topic["tags"])
    script.setdefault("description", topic["description"])

    # Topic meta bilgilerini ekle
    script["hz"] = hz
    script["freq_name"] = topic["name"]
    script["short_benefit"] = topic["short_benefit"]
    script["mood"] = topic["mood"]
    script["pexels_keywords"] = topic.get("pexels_keywords", [])

    print(f"[freq_script_gen] Başlık: {script['title']}")
    print(f"[freq_script_gen] Hook: {script['hook_line']}")
    return script


def save_freq_script(script: dict, path: str = "output/freq_script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[freq_script_gen] Script kaydedildi: {path}")
