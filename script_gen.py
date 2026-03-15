"""
script_gen.py — Google Gemini 1.5 Flash ile YouTube Shorts JSON script üretir.
Ücretsiz tier: 1500 istek/gün, kredi kartı gerekmez.
API key: https://aistudio.google.com/app/apikey
"""

import os
import json
import time
import google.generativeai as genai

SYSTEM_PROMPT = """You are an expert YouTube Shorts scriptwriter specializing in history and war "what if" scenarios.
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
- Output ONLY the JSON, no other text"""


def generate_script(topic: str) -> dict:
    """
    Verilen konu için Gemini 1.5 Flash ile script üretir.
    3 deneme hakkı var, başarısız olursa hata fırlatır.
    """
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=1024,
            temperature=0.9,
        ),
        system_instruction=SYSTEM_PROMPT,
    )

    for attempt in range(3):
        try:
            response = model.generate_content(
                f"Write a YouTube Shorts script for this topic: {topic}"
            )
            raw = response.text.strip()

            # JSON bloğu varsa çıkar
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            script = json.loads(raw)

            # Temel alanları doğrula
            required = ["title", "hook", "narration", "tags", "thumbnail_text", "search_keywords"]
            for field in required:
                if field not in script:
                    raise ValueError(f"Missing field: {field}")

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
    print(f"[script_gen] Konu: {topic}")
    script = generate_script(topic)
    save_script(script)
    print(json.dumps(script, indent=2, ensure_ascii=False))
