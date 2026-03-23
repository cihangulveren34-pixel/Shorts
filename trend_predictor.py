"""
trend_predictor.py — Viral potansiyel tahmin motoru.

Çoklu sinyal kaynağından konu virallik skorunu hesaplar:
  1. Google Trends momentum (yükseliş hızı)
  2. RSS frekansı (aynı konu birden fazla kaynakta mı?)
  3. Tarihsel performans (benzer konular nasıl performans gösterdi?)
  4. Zamanlama skoru (konu ne kadar taze?)
  5. Rekabet analizi (rakipler bu konuyu kapsadı mı?)

Sonuç: 0-100 viral potansiyel skoru + açıklama.

Rakip avantajı: Diğer kanallar rastgele konu seçerken, biz veri odaklı
konu seçimiyle sürekli viral içerik üretiyoruz.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"
RSS_STATE_PATH = "rss_state.json"
PERFORMANCE_HISTORY_PATH = "output/performance_history.json"


@dataclass
class ViralScore:
    """Bir konunun viral potansiyel skoru."""
    topic: str
    trend_score: float = 0.0       # 0-30: Google Trends momentum
    freshness_score: float = 0.0   # 0-20: Konu tazeliği
    rss_frequency: float = 0.0     # 0-20: Çoklu kaynak skoru
    historical_score: float = 0.0  # 0-15: Benzer konuların geçmiş performansı
    competition_score: float = 0.0 # 0-15: Rakip boşluk skoru
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            self.trend_score + self.freshness_score + self.rss_frequency +
            self.historical_score + self.competition_score, 1
        )

    @property
    def tier(self) -> str:
        if self.total >= 75:
            return "VIRAL_POTENTIAL"
        if self.total >= 55:
            return "HIGH"
        if self.total >= 35:
            return "MEDIUM"
        return "LOW"

    def summary(self) -> str:
        lines = [
            f"Viral Skor: {self.total}/100 — {self.tier}",
            f"  Trend:     {self.trend_score}/30",
            f"  Tazelik:   {self.freshness_score}/20",
            f"  RSS Freq:  {self.rss_frequency}/20",
            f"  Tarihsel:  {self.historical_score}/15",
            f"  Rekabet:   {self.competition_score}/15",
        ]
        if self.reasons:
            lines.append("  Nedenler:")
            lines.extend(f"    • {r}" for r in self.reasons)
        return "\n".join(lines)


# ─── Trend Momentum ──────────────────────────────────────────────────────────

def _extract_keywords(topic: str) -> list[str]:
    """Konudan arama anahtar kelimelerini çıkarır."""
    clean = re.sub(r"\[NEWS\]\s*", "", topic)
    clean = re.sub(r"[^\w\s]", " ", clean)
    stop_words = {"what", "if", "the", "a", "an", "is", "was", "how", "why",
                  "who", "and", "or", "but", "in", "on", "at", "to", "for",
                  "of", "never", "ever", "just", "did", "does", "here", "that"}
    words = [w for w in clean.split() if len(w) > 2 and w.lower() not in stop_words]
    return words[:3]


def _score_trend_momentum(topic: str) -> tuple[float, list[str]]:
    """
    Google Trends'ten momentum hesaplar.
    Son 7 günün ortalaması vs son 1 günün değeri → yükseliş tespit.
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))

        keywords = _extract_keywords(topic)
        if not keywords:
            return 0.0, ["Keyword çıkarılamadı"]

        kw = keywords[0]
        pytrends.build_payload([kw], timeframe="now 7-d", geo="")
        df = pytrends.interest_over_time()

        if df.empty or kw not in df.columns:
            return 5.0, [f"'{kw}' Trends verisi yok — temel puan"]

        values = df[kw].tolist()
        if len(values) < 2:
            return 5.0, ["Yetersiz veri noktası"]

        avg_7d = sum(values) / len(values)
        recent = sum(values[-24:]) / max(1, len(values[-24:]))  # Son 24 saat

        if avg_7d == 0:
            return 5.0, ["Trend değeri 0"]

        momentum = (recent - avg_7d) / max(1, avg_7d) * 100

        reasons = []
        if momentum > 50:
            score = 30.0
            reasons.append(f"🔥 '{kw}' patladı! Momentum: +{momentum:.0f}%")
        elif momentum > 20:
            score = 22.0
            reasons.append(f"📈 '{kw}' hızla yükseliyor: +{momentum:.0f}%")
        elif momentum > 0:
            score = 15.0
            reasons.append(f"↗️ '{kw}' yükselişte: +{momentum:.0f}%")
        elif momentum > -20:
            score = 10.0
            reasons.append(f"→ '{kw}' stabil: {momentum:+.0f}%")
        else:
            score = 5.0
            reasons.append(f"↘️ '{kw}' düşüşte: {momentum:+.0f}%")

        # Absolute interest bonus
        if recent > 70:
            score = min(30, score + 5)
            reasons.append(f"Yüksek mutlak ilgi: {recent:.0f}/100")

        return score, reasons

    except ImportError:
        return 10.0, ["pytrends kurulu değil — varsayılan puan"]
    except Exception as e:
        return 8.0, [f"Trends hatası: {str(e)[:60]}"]


# ─── Tazelik Skoru ────────────────────────────────────────────────────────────

def _score_freshness(topic: str) -> tuple[float, list[str]]:
    """
    Konu ne kadar taze? [NEWS] prefix'i varsa veya RSS'ten geldiyse yüksek puan.
    """
    reasons = []

    if topic.startswith("[NEWS]"):
        return 20.0, ["Son dakika haberi — maksimum tazelik"]

    # RSS state'inden kontrol et
    try:
        if os.path.exists(RSS_STATE_PATH):
            with open(RSS_STATE_PATH, encoding="utf-8") as f:
                rss_state = json.load(f)
            seen_titles = rss_state.get("seen_titles", [])
            topic_lower = topic.lower()
            # RSS'ten türetilmiş mi?
            for title in seen_titles[-50:]:
                if any(w in title.lower() for w in _extract_keywords(topic)):
                    return 16.0, ["RSS haberlerinden türetilmiş — taze konu"]
    except Exception:
        pass

    # Anahtar kelimelerle güncellik tahmini
    current_year = str(datetime.now().year)
    if current_year in topic or "today" in topic.lower() or "latest" in topic.lower():
        return 14.0, ["Güncel referans içeriyor"]

    return 8.0, ["Standart konu — orta tazelik"]


# ─── RSS Frekans Skoru ────────────────────────────────────────────────────────

def _score_rss_frequency(topic: str) -> tuple[float, list[str]]:
    """
    Aynı konu birden fazla haber kaynağında mı? Çoklu kaynak = viral potansiyel.
    """
    try:
        if not os.path.exists(RSS_STATE_PATH):
            return 5.0, ["RSS state dosyası yok"]

        with open(RSS_STATE_PATH, encoding="utf-8") as f:
            rss_state = json.load(f)

        seen_titles = rss_state.get("seen_titles", [])
        if not seen_titles:
            return 5.0, ["RSS geçmişi boş"]

        keywords = _extract_keywords(topic)
        if not keywords:
            return 5.0, ["Keyword yok"]

        # Kaç farklı başlıkta bu keywordler geçiyor?
        match_count = 0
        for title in seen_titles[-100:]:
            title_lower = title.lower()
            if any(kw.lower() in title_lower for kw in keywords):
                match_count += 1

        reasons = []
        if match_count >= 10:
            score = 20.0
            reasons.append(f"🔥 {match_count} farklı haber kaynağında — çok gündem")
        elif match_count >= 5:
            score = 15.0
            reasons.append(f"📰 {match_count} farklı haberde geçiyor — gündemde")
        elif match_count >= 2:
            score = 10.0
            reasons.append(f"📋 {match_count} haberde geçiyor")
        else:
            score = 5.0
            reasons.append("Az haber kapsamı")

        return score, reasons

    except Exception as e:
        return 5.0, [f"RSS frekans hatası: {str(e)[:40]}"]


# ─── Tarihsel Performans ─────────────────────────────────────────────────────

def _score_historical(topic: str) -> tuple[float, list[str]]:
    """
    Benzer konuların geçmiş performansını kontrol eder.
    retention_insights.json ve analytics verilerini kullanır.
    """
    try:
        insights_path = "output/retention_insights.json"
        if not os.path.exists(insights_path):
            return 7.5, ["Tarihsel veri yok — varsayılan puan"]

        with open(insights_path, encoding="utf-8") as f:
            insights = json.load(f)

        videos = insights.get("videos", [])
        if not videos:
            return 7.5, ["Analiz edilmiş video yok"]

        keywords = _extract_keywords(topic)
        if not keywords:
            return 7.5, ["Keyword yok"]

        # Benzer konulardaki videoların retention ortalaması
        similar_retentions = []
        for v in videos:
            title_lower = v.get("title", "").lower()
            analysis = v.get("analysis", {})
            avg_ret = analysis.get("avg_retention", 0)

            if any(kw.lower() in title_lower for kw in keywords) and avg_ret > 0:
                similar_retentions.append(avg_ret)

        if not similar_retentions:
            return 7.5, ["Benzer konu bulunamadı — varsayılan puan"]

        avg = sum(similar_retentions) / len(similar_retentions)
        reasons = []

        if avg > 60:
            score = 15.0
            reasons.append(f"Benzer konular mükemmel retention: %{avg:.0f}")
        elif avg > 45:
            score = 11.0
            reasons.append(f"Benzer konular iyi retention: %{avg:.0f}")
        elif avg > 30:
            score = 7.0
            reasons.append(f"Benzer konular orta retention: %{avg:.0f}")
        else:
            score = 3.0
            reasons.append(f"Benzer konular düşük retention: %{avg:.0f} — dikkat!")

        return score, reasons

    except Exception as e:
        return 7.5, [f"Tarihsel analiz hatası: {str(e)[:40]}"]


# ─── Rekabet Boşluk Skoru ────────────────────────────────────────────────────

def _score_competition_gap(topic: str) -> tuple[float, list[str]]:
    """
    Rakipler bu konuyu kapsadı mı? Kapsamadıysa fırsat var.
    competitor_tracker verilerini kullanır.
    """
    try:
        comp_path = "output/competitor_state.json"
        if not os.path.exists(comp_path):
            return 10.0, ["Rakip verisi yok — nötr puan"]

        with open(comp_path, encoding="utf-8") as f:
            comp_data = json.load(f)

        keywords = _extract_keywords(topic)
        if not keywords:
            return 10.0, ["Keyword yok"]

        # Rakip videolarının başlıklarında bu konuyu ara
        competitor_titles = []
        for channel in comp_data.get("channels", []):
            for video in channel.get("recent_videos", []):
                competitor_titles.append(video.get("title", "").lower())

        if not competitor_titles:
            return 10.0, ["Rakip video verisi yok"]

        # Kaç rakip bu konuyu kapsamış?
        covered_count = 0
        for title in competitor_titles:
            if any(kw.lower() in title for kw in keywords):
                covered_count += 1

        reasons = []
        if covered_count == 0:
            score = 15.0
            reasons.append("🎯 Hiçbir rakip kapsamadı — büyük fırsat!")
        elif covered_count <= 2:
            score = 10.0
            reasons.append(f"Az rekabet: sadece {covered_count} rakip kapsamış")
        elif covered_count <= 5:
            score = 6.0
            reasons.append(f"Orta rekabet: {covered_count} rakip kapsamış")
        else:
            score = 3.0
            reasons.append(f"Yüksek rekabet: {covered_count} rakip kapsamış — diferansiyasyon şart")

        return score, reasons

    except Exception as e:
        return 10.0, [f"Rekabet analizi hatası: {str(e)[:40]}"]


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def predict_viral_score(topic: str) -> ViralScore:
    """
    Bir konu için viral potansiyel skoru hesaplar.

    Returns:
        ViralScore objesi
    """
    vs = ViralScore(topic=topic)

    # Her sinyal kaynağını puanla
    vs.trend_score, reasons = _score_trend_momentum(topic)
    vs.reasons.extend(reasons)

    vs.freshness_score, reasons = _score_freshness(topic)
    vs.reasons.extend(reasons)

    vs.rss_frequency, reasons = _score_rss_frequency(topic)
    vs.reasons.extend(reasons)

    vs.historical_score, reasons = _score_historical(topic)
    vs.reasons.extend(reasons)

    vs.competition_score, reasons = _score_competition_gap(topic)
    vs.reasons.extend(reasons)

    return vs


def rank_topics(topics: list[str], top_n: int = 5) -> list[ViralScore]:
    """
    Birden fazla konuyu viral potansiyeline göre sıralar.

    Returns:
        En yüksek skorlu top_n konu listesi
    """
    print(f"[trend_predictor] {len(topics)} konu analiz ediliyor...")

    scores = []
    for i, topic in enumerate(topics):
        print(f"  [{i+1}/{len(topics)}] {topic[:50]}...")
        vs = predict_viral_score(topic)
        scores.append(vs)
        print(f"    → {vs.total}/100 ({vs.tier})")
        time.sleep(0.5)  # Rate limit koruması

    scores.sort(key=lambda s: s.total, reverse=True)
    return scores[:top_n]


def pick_best_topic(topics: list[str]) -> tuple[str, ViralScore]:
    """
    Verilen konulardan en viral potansiyelli olanı seçer.

    Returns:
        (en iyi konu, ViralScore)
    """
    if not topics:
        raise ValueError("Boş konu listesi")

    if len(topics) == 1:
        vs = predict_viral_score(topics[0])
        return topics[0], vs

    ranked = rank_topics(topics, top_n=1)
    best = ranked[0]

    print(f"\n[trend_predictor] En iyi konu: '{best.topic}'")
    print(best.summary())

    return best.topic, best


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
        vs = predict_viral_score(topic)
        print(vs.summary())
    else:
        # Pool'dan ilk 10 konuyu analiz et
        try:
            with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
                pool = json.load(f)
            ranked = rank_topics(pool[:10], top_n=5)
            print(f"\n{'='*60}")
            print("Top 5 Viral Potansiyel:")
            for i, vs in enumerate(ranked, 1):
                print(f"\n{i}. [{vs.total}] {vs.topic}")
                for r in vs.reasons:
                    print(f"     {r}")
        except Exception as e:
            print(f"Hata: {e}")
