"""
script_gen.py — Google Gemini API ile YouTube Shorts JSON script üretir.
Ücretsiz tier: 1500 istek/gün, kredi kartı gerekmez.
API key: https://aistudio.google.com/app/apikey

Dil desteği: "en" (İngilizce) veya "tr" (Türkçe)
"""

import os
import json
import re
import sys
import time
import requests


SYSTEM_PROMPTS = {
    "en": """You are an expert YouTube Shorts scriptwriter specializing in history, war, and geopolitics "what if" scenarios.
Your job is to write engaging, fast-paced scripts for 50-55 second vertical videos.
Topics can be historical alternate history OR current geopolitical/military scenarios.

Output ONLY a valid JSON object with this exact structure:
{
  "title": "What if [Scenario]?",
  "hook": "A punchy 1-sentence opening (max 15 words) that creates immediate curiosity",
  "narration": "The full narration script (150-180 words). Structure: 0-3s HOOK, 3-15s SETUP (historical context), 15-40s TWIST (3 alternate outcomes, fast pace), 40-50s PAYOFF (most shocking outcome), 50-55s CTA. Use short, punchy sentences. Present tense for drama.",
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
  "narration": "Tam anlatı metni (150-180 kelime). Yapı: 0-3sn HOOK, 3-15sn KURULUM, 15-40sn TWIST, 40-50sn PAYOFF, 50-55sn CTA. Kısa, çarpıcı cümleler kullan. Dramatik etki için geniş zaman.",
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

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """Gemini API'yi direkt HTTP ile çağırır, SDK kullanmaz."""
    url = GEMINI_API_URL.format(model=model) + f"?key={api_key}"

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
            "temperature": 0.9,
        },
    }

    resp = requests.post(url, json=payload, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()

    # Extract text from response
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response format: {json.dumps(data)[:300]}")

    return text


def _parse_json_response(raw: str) -> dict:
    """Gemini'nin döndürdüğü metinden JSON objesini çıkarır ve parse eder."""
    # Remove markdown code fences
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    # Extract the JSON object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    # Stage 1: direct parse
    try:
        return _normalize_script(json.loads(raw))
    except json.JSONDecodeError:
        pass

    # Stage 2: fix newlines/tabs inside strings
    fixed = _fix_json_strings(raw)
    try:
        return _normalize_script(json.loads(fixed))
    except json.JSONDecodeError:
        pass

    # Stage 3: fix trailing commas
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        return _normalize_script(json.loads(fixed))
    except json.JSONDecodeError:
        pass

    # Stage 4: regex extraction (nuclear)
    print("[script_gen] WARNING: Using regex fallback for JSON parsing", file=sys.stderr)
    return _extract_with_regex(raw)


def _fix_json_strings(raw: str) -> str:
    """JSON string'leri içindeki escape edilmemiş karakterleri düzeltir."""
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
    return fixed


def _normalize_script(data: dict) -> dict:
    """narration array ise string'e çevirir."""
    if isinstance(data.get("narration"), list):
        data["narration"] = " ".join(data["narration"])
    return data


def _extract_with_regex(raw: str) -> dict:
    """Son çare: regex ile alanları tek tek çıkarır."""
    def _extract(field):
        m = re.search(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if m:
            return m.group(1).replace('\n', ' ').strip()
        m = re.search(rf'"{field}"\s*:\s*"([^"]*)', raw, re.DOTALL)
        if m:
            return m.group(1).replace('\n', ' ').strip()
        return ""

    def _extract_list(field):
        m = re.search(rf'"{field}"\s*:\s*\[(.*?)\]', raw, re.DOTALL)
        if m:
            return [s.strip().strip('"') for s in m.group(1).split(',') if s.strip().strip('"')]
        return []

    return {
        "title": _extract("title"),
        "hook": _extract("hook"),
        "narration": _extract("narration"),
        "tags": _extract_list("tags"),
        "thumbnail_text": _extract("thumbnail_text"),
        "search_keywords": _extract_list("search_keywords"),
    }


def generate_script(topic: str, language: str = "en") -> dict:
    """
    Verilen konu için Gemini ile script üretir.
    language: "en" (varsayılan) veya "tr"
    """
    lang = language if language in SYSTEM_PROMPTS else "en"
    system_prompt = SYSTEM_PROMPTS[lang]
    api_key = os.environ["GEMINI_API_KEY"]

    user_prompt = {
        "en": f"Write a YouTube Shorts script for this topic: {topic}",
        "tr": f"Bu konu için YouTube Shorts senaryosu yaz: {topic}",
    }[lang]

    # Try models in order of preference
    models = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    last_error = None

    for model in models:
        for attempt in range(3):
            try:
                print(f"[script_gen] Model: {model}, Attempt: {attempt+1}", file=sys.stderr)
                raw = _call_gemini(api_key, model, system_prompt, user_prompt)
                print(f"[script_gen] Response ({len(raw)} chars): {raw[:200]}...", file=sys.stderr)

                script = _parse_json_response(raw)

                required = ["title", "hook", "narration", "tags", "thumbnail_text", "search_keywords"]
                for field in required:
                    if field not in script:
                        raise ValueError(f"Missing field: {field}")

                # narration boş ise hata
                if not script.get("narration"):
                    raise ValueError("Narration is empty")

                script["language"] = lang
                script["tts_voice"] = TTS_VOICES[lang]

                print(f"[script_gen] SUCCESS: {script['title']}", file=sys.stderr)
                return script

            except Exception as e:
                last_error = e
                print(f"[script_gen] Error: {type(e).__name__}: {e}", file=sys.stderr)
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                break  # Try next model

    raise RuntimeError(f"Script generation failed with all models: {last_error}")


def save_script(script: dict, path: str = "output/script.json") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print(f"[script_gen] Script kaydedildi: {path}")


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "What if Rome Never Fell?"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    print(f"[script_gen] Konu: {topic} | Dil: {lang}")
    script = generate_script(topic, lang)
    save_script(script)
    print(json.dumps(script, indent=2, ensure_ascii=False))
