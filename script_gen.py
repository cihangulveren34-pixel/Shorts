"""
script_gen.py — Google Gemini 2.5 Flash ile YouTube Shorts JSON script üretir.
Ücretsiz tier: 1500 istek/gün, kredi kartı gerekmez.
API key: https://aistudio.google.com/app/apikey

Dil desteği: "en" (İngilizce) veya "tr" (Türkçe)
"""

import os
import json
import re
import time
from google import genai
from google.genai import types


SYSTEM_PROMPTS = {
    "en": """You are an expert YouTube Shorts scriptwriter specializing in history and war "what if" scenarios.
Your job is to write engaging, fast-paced scripts for 50-55 second vertical videos.

Output ONLY a valid JSON object with this exact structure:
{
  "title": "What if [Scenario]?",
  "hook": "A punchy 1-sentence opening (max 15 words) that creates immediate curiosity",
  "narration": "The full narration script (150-180 words). Structure: 0-3s HOOK, 3-15s SETUP (historical context), 15-40s TWIST (3 alternate outcomes, fast pace), 40-50s PAYOFF (most shocking outcome), 50-55s CTA ('Follow for more what-ifs!'). Use short, punchy sentences. Present tense for drama.",
  "tags": ["history", "whatif", "war", "shorts"],
  "thumbnail_text": "SHORT DRAMATIC TEXT IN CAPS (max 4 words)",
  "search_keywords": ["keyword1", "keyword2", "keyword3"]
}

Rules:
- narration must be 150-180 words
- hook must be under 15 words
- thumbnail_text must be ALL CAPS and max 4 words
- search_keywords should relate to the historical footage needed
- tags must always include "history", "whatif", "war", "shorts"
- Output ONLY the JSON, no other text""",

    "tr": """Sen savaş ve tarih "ya olmasaydı" senaryolarında uzmanlaşmış bir YouTube Shorts senaryo yazarısın.
50-55 saniyelik dikey videolar için çarpıcı, hızlı tempolu senaryolar yazıyorsun.

SADECE şu yapıda geçerli bir JSON nesnesi çıkar:
{
  "title": "Ya [Senaryo] Olmasaydı?",
  "hook": "İlk 3 saniyede dikkat çeken çarpıcı 1 cümle (max 15 kelime)",
  "narration": "Tam anlatı metni (150-180 kelime). Yapı: 0-3sn HOOK, 3-15sn KURULUM (tarihsel arka plan), 15-40sn TWIST (3 alternatif sonuç, hızlı tempo), 40-50sn PAYOFF (en beklenmedik sonuç), 50-55sn CTA ('Daha fazlası için takip et!'). Kısa, çarpıcı cümleler kullan. Dramatik etki için geniş zaman.",
  "tags": ["tarih", "yasaolmasaydi", "savas", "shorts"],
  "thumbnail_text": "BÜYÜK HARF KISA METİN (max 4 kelime)",
  "search_keywords": ["keyword1", "keyword2", "keyword3"]
}

Kurallar:
- narration 150-180 kelime olmalı
- hook max 15 kelime
- thumbnail_text TAMAMI BÜYÜK HARF, max 4 kelime
- search_keywords İngilizce olmalı (Pexels arama için)
- SADECE JSON çıkar, başka metin ekleme""",
}

# TTS için dil-ses eşleştirmesi
TTS_VOICES = {
    "en": "en-US-GuyNeural",
    "tr": "tr-TR-AhmetNeural",
}


def _parse_json_response(raw: str) -> dict:
    """Gemini'nin döndürdüğü metinden JSON objesini çıkarır ve parse eder."""
    # Remove markdown code fences
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    # Extract the JSON object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", raw, 0)
    raw = match.group(0)

    # First try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fix common issues: unescaped newlines/tabs/quotes inside strings
    fixed = ""
    in_string = False
    escape = False
    for ch in raw:
        if escape:
            fixed += ch
            escape = False
            continue
        if ch == '\\':
            fixed += ch
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
        if in_string and ch in ('\n', '\r', '\t'):
            fixed += ' '
        else:
            fixed += ch

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: fix single quotes, trailing commas
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    return json.loads(fixed)


def generate_script(topic: str, language: str = "en") -> dict:
    """
    Verilen konu için Gemini 2.5 Flash ile script üretir.
    language: "en" (varsayılan) veya "tr"
    """
    lang = language if language in SYSTEM_PROMPTS else "en"
    system_prompt = SYSTEM_PROMPTS[lang]

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    user_prompt = {
        "en": f"Write a YouTube Shorts script for this topic: {topic}",
        "tr": f"Bu konu için YouTube Shorts senaryosu yaz: {topic}",
    }[lang]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=2048,
                    temperature=0.9,
                ),
            )
            raw = response.text.strip()
            print(f"[script_gen] Attempt {attempt+1} raw ({len(raw)} chars): {raw[:300]}...")

            script = _parse_json_response(raw)
            required = ["title", "hook", "narration", "tags", "thumbnail_text", "search_keywords"]
            for field in required:
                if field not in script:
                    raise ValueError(f"Missing field: {field}")

            # Dil bilgisini script'e ekle (tts.py için)
            script["language"] = lang
            script["tts_voice"] = TTS_VOICES[lang]

            return script

        except (json.JSONDecodeError, ValueError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Script generation failed after 3 attempts: {e}")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def save_script(script: dict, path: str = "output/script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[script_gen] Script kaydedildi: {path}")


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "What if Rome Never Fell?"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    print(f"[script_gen] Konu: {topic} | Dil: {lang}")
    script = generate_script(topic, lang)
    save_script(script)
    print(json.dumps(script, indent=2, ensure_ascii=False))
