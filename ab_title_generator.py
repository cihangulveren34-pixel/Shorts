"""
ab_title_generator.py — Her video için birden fazla başlık varyantı üretir.

Gemini ile 3 farklı başlık varyantı üretir ve 24 saat sonra en iyi
performans gösteren başlığı seçer. Title_optimizer.py'den farklı olarak:
  - Yayınlamadan ÖNCE birden fazla seçenek üretir
  - Her birini CTR ve hook gücüne göre puanlar
  - En iyisini otomatik seçer
  - 24 saat sonra gerçek veriye göre optimize eder

Başlık Formülleri (test edilmiş):
  1. Soru formatı: "Why Did [Country] Just Do THIS?"
  2. Şok formatı: "[Country] Just Changed EVERYTHING"
  3. Sayısal format: "3 Reasons [Event] Should Terrify [Country]"
  4. Acil format: "BREAKING: [Event] — What It Means"
  5. Gizem formatı: "The Truth About [Topic] Nobody Talks About"

Rakip avantajı: Her video için en güçlü başlığı veri odaklı seçeriz.
Rakipler tek başlıkla yüklemenin lottery etkisindeyken, biz A/B test ederiz.
"""

import json
import os
import re
import requests
from datetime import datetime, timezone

from script_scorer import TITLE_CTR_WORDS


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
AB_TITLES_PATH = "output/ab_titles.json"

# Başlık formül şablonları (Gemini'ye yol gösterici)
TITLE_FORMULAS = {
    "question": "Turn the topic into a compelling question that viewers MUST click to answer",
    "shock": "Start with a shocking statement that creates urgency",
    "numeric": "Use a number to create a listicle-style hook (3 Reasons, 5 Ways, etc.)",
    "breaking": "Frame it as breaking news with urgency markers",
    "mystery": "Create curiosity gap — hint at hidden truth",
}


def _call_gemini(prompt: str, system: str = "") -> str:
    """Gemini API çağrısı."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    model = "gemini-2.5-flash-lite"
    url = f"{GEMINI_API_URL.format(model=model)}?key={api_key}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 300,
            "temperature": 0.9,
        },
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[ab_title] Gemini hatası: {e}")
    return ""


def _score_title_variant(title: str) -> int:
    """Başlık varyantını CTR potansiyeline göre puanlar (0-100)."""
    score = 30  # Temel puan
    lower = title.lower()

    # CTR güç kelimeleri
    ctr_hits = sum(1 for w in TITLE_CTR_WORDS if w in lower)
    score += min(25, ctr_hits * 6)

    # Uzunluk optimizasyonu (40-60 karakter ideal)
    length = len(title)
    if 35 <= length <= 60:
        score += 15
    elif 25 <= length <= 70:
        score += 8

    # Soru işareti — merak uyandırır
    if "?" in title:
        score += 10

    # Büyük harfli kelime — dikkat çekici (ama fazlası spam)
    caps_words = len(re.findall(r"\b[A-Z]{2,}\b", title))
    if 1 <= caps_words <= 3:
        score += 8
    elif caps_words > 3:
        score -= 5

    # Emoji (YouTube'da iyi performans gösterir — ama max 1)
    emoji_count = len(re.findall(r"[\U0001f300-\U0001f9ff]", title))
    if emoji_count == 1:
        score += 5
    elif emoji_count > 2:
        score -= 5

    # Sayısal değer (clickbait etkisi)
    if re.search(r"\d+", title):
        score += 7

    # Tarih içerme (güncellik sinyali)
    current_year = str(datetime.now().year)
    months = ["january", "february", "march", "april", "may", "june",
              "july", "august", "september", "october", "november", "december"]
    if current_year in title or any(m in lower for m in months):
        score += 5

    return min(100, max(0, score))


def generate_title_variants(script: dict, count: int = 5) -> list[dict]:
    """
    Script için birden fazla başlık varyantı üretir.

    Returns:
        [{"title": str, "formula": str, "score": int}]
    """
    title = script.get("title", "")
    narration = script.get("narration", "")[:200]
    tags = script.get("tags", [])

    system = """You are a YouTube title optimization expert.
Generate title variants that maximize Click-Through Rate (CTR).

Rules:
- Each title MUST be under 60 characters
- Use different psychological hooks for each
- Include urgency, curiosity, or controversy
- Never use clickbait that doesn't match content
- At least one title should include a date/time reference

Reply in JSON:
{"titles": [
  {"title": "variant 1", "formula": "question|shock|numeric|breaking|mystery"},
  {"title": "variant 2", "formula": "..."},
  ...
]}"""

    prompt = (
        f"Original title: \"{title}\"\n"
        f"Content: {narration}\n"
        f"Tags: {', '.join(tags[:5])}\n\n"
        f"Generate {count} different title variants using these formulas: "
        f"{', '.join(TITLE_FORMULAS.keys())}"
    )

    raw = _call_gemini(prompt, system)
    variants = []

    # Orijinal başlığı da ekle
    variants.append({
        "title": title,
        "formula": "original",
        "score": _score_title_variant(title),
    })

    if raw:
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for v in data.get("titles", []):
                    t = v.get("title", "")
                    if t and t != title:
                        variants.append({
                            "title": t[:60],
                            "formula": v.get("formula", "unknown"),
                            "score": _score_title_variant(t),
                        })
        except (json.JSONDecodeError, KeyError):
            pass

    # Skorlara göre sırala
    variants.sort(key=lambda v: v["score"], reverse=True)

    # Özet
    print(f"[ab_title] {len(variants)} başlık varyantı üretildi:")
    for i, v in enumerate(variants):
        marker = " ← BEST" if i == 0 else ""
        print(f"  [{v['score']}] ({v['formula']}) {v['title']}{marker}")

    return variants


def pick_best_title(script: dict) -> str:
    """
    En yüksek skorlu başlığı seçer ve script'e uygular.

    Returns:
        Seçilen başlık
    """
    variants = generate_title_variants(script)

    if not variants:
        return script.get("title", "")

    best = variants[0]

    # State kaydet (24 saat sonra A/B test için)
    _save_ab_titles(script, variants)

    if best["title"] != script.get("title", ""):
        print(f"[ab_title] ✅ Başlık değiştirildi:")
        print(f"  Eski: {script.get('title', '')}")
        print(f"  Yeni: {best['title']} (skor: {best['score']})")
        script["title"] = best["title"]
    else:
        print(f"[ab_title] Orijinal başlık en iyi (skor: {best['score']})")

    return best["title"]


def _save_ab_titles(script: dict, variants: list[dict]) -> None:
    """A/B test state'ini kaydeder."""
    os.makedirs("output", exist_ok=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_title": script.get("title", ""),
        "variants": variants,
        "selected": variants[0]["title"] if variants else "",
    }
    with open(AB_TITLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    test_script = {
        "title": "Turkey's KAAN Fighter Changes Everything",
        "narration": "Turkey just unveiled the KAAN fifth-generation stealth fighter jet...",
        "tags": ["turkey", "kaan", "fighter", "stealth", "military"],
    }
    variants = generate_title_variants(test_script)
    print(f"\nEn iyi: {variants[0]['title']} ({variants[0]['score']}/100)")
