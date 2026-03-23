"""
smart_regenerator.py — Düşük puanlı scriptleri otomatik yeniden üretir.

Script kalite skoru SCORE_PASS altındaysa, farklı bir yaklaşımla yeniden
üretir. Her denemede önceki hataları Gemini'ye ileterek daha iyi sonuç alır.

Strateji:
  1. İlk script üretilir ve puanlanır
  2. Puan düşükse, puanlama notları Gemini'ye feedback olarak verilir
  3. Maksimum 3 deneme — en yüksek puanlı script seçilir
  4. Hiçbiri SCORE_PASS'ı geçemezse en iyisi kullanılır

Rakip avantajı: Sürekli yüksek kaliteli içerik → daha iyi retention → daha fazla izlenme.
"""

import json
import os
import sys

from script_gen import generate_script, save_script
from script_scorer import score_script, ScoreBreakdown, SCORE_PASS, SCORE_WARN


MAX_RETRIES = 3
FEEDBACK_TEMPLATE_EN = """IMPORTANT FEEDBACK from quality scoring (improve these areas):
{notes}

Previous title was: "{prev_title}"
Previous score: {prev_score}/100

Generate a BETTER script that addresses the above issues. Make the hook more powerful,
the narrative more engaging, and ensure proper CTA and SEO tags."""

FEEDBACK_TEMPLATE_TR = """ÖNEMLİ GERİBİLDİRİM — kalite puanlamasından (bu alanları iyileştir):
{notes}

Önceki başlık: "{prev_title}"
Önceki puan: {prev_score}/100

Yukarıdaki sorunları gideren DAHA İYİ bir senaryo üret. Hook'u daha güçlü,
anlatıyı daha çekici yap ve CTA + SEO etiketlerini doğru kullan."""


def regenerate_until_quality(
    topic: str,
    language: str = "en",
    min_score: int = SCORE_PASS,
    max_attempts: int = MAX_RETRIES,
) -> tuple[dict, ScoreBreakdown]:
    """
    Script üretir, puanlar, düşükse yeniden üretir.

    Returns:
        (en iyi script, en iyi puan breakdown)
    """
    best_script = None
    best_breakdown = None
    best_score = -1
    all_attempts = []

    for attempt in range(1, max_attempts + 1):
        print(f"\n[regenerator] Deneme {attempt}/{max_attempts}...")

        # İlk denemeden sonra topic'e feedback ekle
        effective_topic = topic
        if attempt > 1 and best_breakdown:
            feedback_notes = "\n".join(f"  • {n}" for n in best_breakdown.notes)
            template = FEEDBACK_TEMPLATE_TR if language == "tr" else FEEDBACK_TEMPLATE_EN
            feedback = template.format(
                notes=feedback_notes,
                prev_title=best_script.get("title", ""),
                prev_score=best_breakdown.total,
            )
            effective_topic = f"{topic}\n\n{feedback}"

        try:
            script = generate_script(effective_topic, language)
            breakdown = score_script(script)

            all_attempts.append({
                "attempt": attempt,
                "title": script.get("title", ""),
                "score": breakdown.total,
                "grade": breakdown.grade,
            })

            print(f"[regenerator] Deneme {attempt}: {breakdown.total}/100 ({breakdown.grade})")
            print(f"[regenerator]   Başlık: {script.get('title', '')}")

            if breakdown.total > best_score:
                best_script = script
                best_breakdown = breakdown
                best_score = breakdown.total

            # Yeterince iyi — hemen dön
            if breakdown.total >= min_score:
                print(f"[regenerator] ✅ Kalite hedefine ulaşıldı: {breakdown.total}/100")
                break

        except Exception as e:
            print(f"[regenerator] Deneme {attempt} başarısız: {e}", file=sys.stderr)
            continue

    if not best_script:
        raise RuntimeError("Tüm script üretim denemeleri başarısız oldu.")

    # Sonuç özeti
    if best_score < min_score:
        print(f"\n[regenerator] ⚠️ {max_attempts} denemede hedef ({min_score}) aşılamadı.")
        print(f"[regenerator]   En iyi puan: {best_score}/100")
    else:
        print(f"\n[regenerator] ✅ En iyi puan: {best_score}/100")

    # Tüm denemeleri logla
    print(f"[regenerator] Deneme özeti:")
    for a in all_attempts:
        marker = " ← seçildi" if a["score"] == best_score else ""
        print(f"  #{a['attempt']}: {a['score']}/100 — {a['title'][:50]}{marker}")

    return best_script, best_breakdown


def smart_generate(
    topic: str,
    language: str = "en",
) -> tuple[dict, ScoreBreakdown]:
    """
    main.py entegrasyonu için basit arayüz.
    Düşük puanlı scriptleri otomatik yeniden üretir.
    """
    return regenerate_until_quality(topic, language)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "What if Turkey Left NATO?"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"

    script, breakdown = smart_generate(topic, lang)
    save_script(script)

    print(f"\n{'='*50}")
    print(breakdown.summary())
    print(f"{'='*50}")
    print(json.dumps(script, indent=2, ensure_ascii=False))
