"""
script_scorer.py — Script üretildikten sonra kalite skoru verir.

Gemini'nin ürettiği script'i çeşitli kriterlere göre puanlar:
  - Hook gücü: İlk cümle dikkat çekici mi? (0-25 puan)
  - Anlatı akışı: Başlangıç → gelişme → sonuç var mı? (0-25 puan)
  - CTA varlığı: Abone/takip çağrısı var mı? (0-10 puan)
  - Uzunluk uyumu: 45-60 saniyelik anlatı için ideal kelime sayısı (0-20 puan)
  - SEO tag kalitesi: Tag'ler arama odaklı mı? (0-10 puan)
  - Başlık gücü: CTR'a katkı yapacak başlık mı? (0-10 puan)

Toplam: 100 puan
  80+ → Yayınla
  60-79 → Uyarıyla devam et
  <60 → Yeniden üret

Gereksinim: GEMINI_API_KEY (opsiyonel — yoksa kural bazlı puanlama)
"""

import json
import os
import re
from dataclasses import dataclass, field

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# Puan eşikleri
SCORE_PASS = 80
SCORE_WARN = 60

# Hook güç kelimeleri
HOOK_POWER_WORDS = [
    "imagine", "what if", "never", "secret", "truth", "shocking", "actually",
    "nobody", "nobody knows", "hidden", "real reason", "dark", "untold",
    "changed everything", "almost", "could have", "would have",
]

# Zayıf hook göstergeleri
WEAK_HOOK_PATTERNS = [
    r"^(in|the|a|an|today|this|let me|let's|i will|we will)\b",
    r"^(hello|hi|hey|welcome)\b",
]

# İdeal anlatı kelime sayısı (TTS ~150 kelime/dakika, 50-60 saniye hedef)
IDEAL_WORD_MIN = 100
IDEAL_WORD_MAX = 160

# Arama odaklı tag kelimeleri
SEO_TAG_KEYWORDS = [
    "history", "shorts", "whatif", "war", "ancient", "medieval", "ww2",
    "what if", "alternate", "empire", "battle", "world", "facts",
]

# Başlık CTR kelimeleri
TITLE_CTR_WORDS = [
    "what if", "never", "secret", "truth", "real", "hidden", "actually",
    "dark", "untold", "?", "almost", "biggest",
]


@dataclass
class ScoreBreakdown:
    hook_score: int = 0         # 0-25
    narrative_score: int = 0    # 0-25
    cta_score: int = 0          # 0-10
    length_score: int = 0       # 0-20
    seo_score: int = 0          # 0-10
    title_score: int = 0        # 0-10
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (self.hook_score + self.narrative_score + self.cta_score +
                self.length_score + self.seo_score + self.title_score)

    @property
    def grade(self) -> str:
        if self.total >= SCORE_PASS:
            return "PASS ✅"
        if self.total >= SCORE_WARN:
            return "WARN ⚠️"
        return "FAIL ❌"

    def summary(self) -> str:
        lines = [
            f"Script Skoru: {self.total}/100 — {self.grade}",
            f"  Hook:     {self.hook_score}/25",
            f"  Anlatı:   {self.narrative_score}/25",
            f"  Uzunluk:  {self.length_score}/20",
            f"  CTA:      {self.cta_score}/10",
            f"  SEO Tags: {self.seo_score}/10",
            f"  Başlık:   {self.title_score}/10",
        ]
        if self.notes:
            lines.append("  Notlar:")
            lines.extend(f"    • {n}" for n in self.notes)
        return "\n".join(lines)


# ─────────── Kural tabanlı puanlama ───────────

def _score_hook(hook: str, narration: str) -> tuple[int, list[str]]:
    notes = []
    score = 10  # Temel puan

    first_sentence = hook.split(".")[0].lower() if hook else ""

    # Güç kelimeleri
    power_hits = sum(1 for w in HOOK_POWER_WORDS if w in first_sentence)
    score += min(10, power_hits * 4)

    # Soru içeriyor mu?
    if "?" in hook:
        score += 5
        notes.append("Hook soru içeriyor (+5)")

    # Zayıf başlangıç
    for pat in WEAK_HOOK_PATTERNS:
        if re.match(pat, first_sentence, re.IGNORECASE):
            score -= 8
            notes.append("Hook zayıf başlangıç kelimesiyle açılıyor (-8)")
            break

    # Hook uzunluğu (çok kısa veya çok uzun)
    word_count = len(hook.split())
    if word_count < 8:
        score -= 5
        notes.append(f"Hook çok kısa ({word_count} kelime, min 8)")
    elif word_count > 25:
        score -= 3
        notes.append(f"Hook çok uzun ({word_count} kelime, max 25)")

    return max(0, min(25, score)), notes


def _score_narrative(narration: str) -> tuple[int, list[str]]:
    notes = []
    score = 10

    lower = narration.lower()

    # Yapısal belirteçler: zaman geçişi, kontrast, sonuç
    has_contrast = any(w in lower for w in ["but", "however", "instead", "yet", "although"])
    has_progression = any(w in lower for w in ["then", "next", "eventually", "finally", "ultimately", "as a result"])
    has_hook_payoff = any(w in lower for w in ["this means", "which means", "the result", "today", "now imagine"])

    if has_contrast:
        score += 5
        notes.append("Karşıtlık ifadesi mevcut (+5)")
    if has_progression:
        score += 5
        notes.append("Zaman/sıra geçişi mevcut (+5)")
    if has_hook_payoff:
        score += 5
        notes.append("Hook bağlantısı mevcut (+5)")

    # Çok tekrarlı kelimeler (kötü anlatı işareti)
    words = re.findall(r"\b\w{4,}\b", lower)
    from collections import Counter
    freq = Counter(words)
    repetitive = [w for w, c in freq.most_common(5) if c > 4 and w not in
                  {"would", "could", "their", "have", "been", "that", "with", "this", "they", "were"}]
    if repetitive:
        score -= len(repetitive) * 2
        notes.append(f"Tekrarlı kelimeler: {repetitive[:3]} (-{len(repetitive)*2})")

    return max(0, min(25, score)), notes


def _score_cta(narration: str, hook: str) -> tuple[int, list[str]]:
    combined = (narration + " " + hook).lower()
    cta_patterns = ["subscribe", "follow", "tap follow", "hit the bell", "like", "comment", "what do you think"]
    hits = sum(1 for p in cta_patterns if p in combined)
    if hits >= 2:
        return 10, ["Güçlü CTA (birden fazla)"]
    if hits == 1:
        return 7, ["CTA mevcut"]
    return 0, ["CTA eksik — abone/takip çağrısı ekle (-10)"]


def _score_length(narration: str) -> tuple[int, list[str]]:
    words = len(narration.split())
    notes = []
    if IDEAL_WORD_MIN <= words <= IDEAL_WORD_MAX:
        return 20, [f"İdeal uzunluk: {words} kelime ✓"]
    if words < IDEAL_WORD_MIN:
        diff = IDEAL_WORD_MIN - words
        score = max(0, 20 - diff // 3)
        notes.append(f"Çok kısa: {words} kelime (ideal {IDEAL_WORD_MIN}-{IDEAL_WORD_MAX})")
        return score, notes
    diff = words - IDEAL_WORD_MAX
    score = max(0, 20 - diff // 5)
    notes.append(f"Çok uzun: {words} kelime (ideal {IDEAL_WORD_MIN}-{IDEAL_WORD_MAX})")
    return score, notes


def _score_seo_tags(tags: list[str]) -> tuple[int, list[str]]:
    if not tags:
        return 0, ["Tag listesi boş"]
    lower_tags = " ".join(t.lower() for t in tags)
    hits = sum(1 for k in SEO_TAG_KEYWORDS if k in lower_tags)
    score = min(10, hits * 2)
    notes = []
    if len(tags) < 5:
        score -= 3
        notes.append(f"Az tag: {len(tags)} (minimum 5 önerilen)")
    if score < 6:
        notes.append("Tag'ler SEO odaklı değil — 'history', 'war', 'whatif' gibi ekle")
    return max(0, score), notes


def _score_title(title: str) -> tuple[int, list[str]]:
    notes = []
    score = 5
    lower = title.lower()

    hits = sum(1 for w in TITLE_CTR_WORDS if w in lower)
    score += min(5, hits * 2)

    if len(title) < 20:
        score -= 3
        notes.append(f"Başlık çok kısa ({len(title)} karakter)")
    elif len(title) > 70:
        score -= 2
        notes.append(f"Başlık çok uzun ({len(title)} karakter, YouTube 70 gösterir)")

    if not re.search(r"[?!]", title):
        notes.append("Başlıkta soru/ünlem yok — CTR düşük olabilir")

    return max(0, min(10, score)), notes


# ─────────── Gemini tabanlı ek puanlama ───────────

def _gemini_quality_bonus(script: dict) -> int:
    """
    Gemini'ye script'i okutarak 0-10 arası ek kalite bonusu alır.
    Bu puan toplam skora eklenmez, sadece notlara yansır.
    """
    if not GEMINI_AVAILABLE:
        return 0
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return 0
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            f"Rate this YouTube Shorts script on a scale of 1-10 for viral potential.\n"
            f"Title: {script.get('title', '')}\n"
            f"Hook: {script.get('hook', '')}\n"
            f"Narration (first 200 chars): {script.get('narration', '')[:200]}\n\n"
            f"Reply with ONLY a single integer (1-10), nothing else."
        )
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=5, temperature=0.1),
        )
        return min(10, max(1, int(resp.text.strip())))
    except Exception:
        return 0


# ─────────── Ana fonksiyon ───────────

def score_script(script: dict) -> ScoreBreakdown:
    """
    Script'i puanlar.

    Args:
        script: generate_script() çıktısı

    Returns:
        ScoreBreakdown — .total < SCORE_PASS ise yeniden üretmeyi düşün
    """
    breakdown = ScoreBreakdown()

    hook = script.get("hook", "")
    narration = script.get("narration", "")
    tags = script.get("tags", [])
    title = script.get("title", "")

    s, n = _score_hook(hook, narration)
    breakdown.hook_score = s
    breakdown.notes.extend(n)

    s, n = _score_narrative(narration)
    breakdown.narrative_score = s
    breakdown.notes.extend(n)

    s, n = _score_cta(narration, hook)
    breakdown.cta_score = s
    breakdown.notes.extend(n)

    s, n = _score_length(narration)
    breakdown.length_score = s
    breakdown.notes.extend(n)

    s, n = _score_seo_tags(tags)
    breakdown.seo_score = s
    breakdown.notes.extend(n)

    s, n = _score_title(title)
    breakdown.title_score = s
    breakdown.notes.extend(n)

    # Opsiyonel Gemini kalite bonusu (notlara yansır)
    gemini_score = _gemini_quality_bonus(script)
    if gemini_score:
        breakdown.notes.append(f"Gemini viral tahmini: {gemini_score}/10")

    return breakdown


def score_or_warn(script: dict, min_score: int = SCORE_WARN) -> ScoreBreakdown:
    """
    Puanlar; düşükse uyarı yazdırır ama pipeline'ı durdurmaz.
    SCORE_PASS altındaysa caller'a bırakılır karar.
    """
    bd = score_script(script)
    print(f"\n[scorer] {bd.summary()}\n")

    if bd.total < min_score:
        print(f"[scorer] ⚠️  Puan düşük ({bd.total} < {min_score}). Script yeniden üretilmesi önerilen.")
    return bd


if __name__ == "__main__":
    test_script = {
        "title": "What if Rome Never Fell?",
        "hook": "Imagine waking up in 2025 — and the Roman Empire never collapsed. What would the world look like TODAY?",
        "narration": (
            "In 476 AD, the last Roman emperor fell. But what if he didn't? "
            "Instead of dark ages, Roman roads and law would have united Europe for 1500 more years. "
            "Latin would be the global language. Christianity would have evolved differently. "
            "But here's the dark twist — with no competition between nations, "
            "innovation might have stagnated. No Renaissance. No Industrial Revolution. "
            "The world might actually be LESS advanced today. "
            "Which alternate outcome do you think is most likely? Subscribe for more what-ifs!"
        ),
        "tags": ["rome", "history", "whatif", "war", "shorts", "alternate"],
        "thumbnail_text": "ROME NEVER FELL?",
    }
    bd = score_or_warn(test_script)
