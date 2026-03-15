"""
script_gen.py — Google Gemini 1.5 Flash ile YouTube Shorts JSON script üretir.
Ücretsiz tier: 1500 istek/gün, kredi kartı gerekmez.
API key: https://aistudio.google.com/app/apikey

Dil desteği: "en" (İngilizce) veya "tr" (Türkçe)
"""

import os
import json
import time
import google.generativeai as genai


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


def generate_script(topic: str, language: str = "en") -> dict:
    """
    Verilen konu için Gemini 1.5 Flash ile script üretir.
    language: "en" (varsayılan) veya "tr"
    """
    lang = language if language in SYSTEM_PROMPTS else "en"
    system_prompt = SYSTEM_PROMPTS[lang]

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=1024,
            temperature=0.9,
        ),
        system_instruction=system_prompt,
    )

    user_prompt = {
        "en": f"Write a YouTube Shorts script for this topic: {topic}",
        "tr": f"Bu konu için YouTube Shorts senaryosu yaz: {topic}",
    }[lang]

    for attempt in range(3):
        try:
            response = model.generate_content(user_prompt)
            raw = response.text.strip()

            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            script = json.loads(raw)
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
