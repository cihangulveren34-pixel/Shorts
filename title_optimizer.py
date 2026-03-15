"""
title_optimizer.py — Yüklendikten 24 saat sonra YouTube Analytics'i kontrol eder.
Görüntülenme eşiğin altındaysa Gemini ile 3 yeni başlık varyantı üretir
ve en iyi olanı YouTube API ile günceller.

Çalıştırma:
  python title_optimizer.py              # last_video.json'daki video için
  python title_optimizer.py VIDEO_ID     # belirli video için
"""

import json
import os
import sys
import time

import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from notifier import _send


VIEWS_THRESHOLD = 500       # 24 saatte bu kadar görüntülenme yoksa başlık değiştir
LAST_VIDEO_PATH = "output/last_video.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _get_credentials() -> Credentials:
    import tempfile
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_json:
        data = json.loads(token_json)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        creds = Credentials.from_authorized_user_file(tmp.name, SCOPES)
        os.unlink(tmp.name)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        raise FileNotFoundError("YouTube token bulunamadı.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def get_video_views_24h(video_id: str) -> int:
    """Videonun son 24 saatteki görüntülenme sayısını döndürür."""
    from datetime import datetime, timedelta, timezone

    creds = _get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=1)

    try:
        report = yta.reports().query(
            ids="channel==MINE",
            startDate=str(start_date),
            endDate=str(end_date),
            metrics="views",
            dimensions="video",
            filters=f"video=={video_id}",
        ).execute()

        rows = report.get("rows", [])
        if rows:
            return int(rows[0][1])
    except Exception as e:
        print(f"[title_optimizer] Analytics sorgu hatası: {e}")

    return 0


def generate_title_variants(original_title: str, hook: str) -> list[str]:
    """Gemini ile 3 farklı başlık varyantı üretir."""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=512,
            temperature=1.0,
        ),
    )

    prompt = f"""You are a YouTube title optimization expert.
The video title "{original_title}" got low views in the first 24 hours.
Hook: "{hook}"

Generate 3 alternative titles with higher click-through potential.
Rules:
- Max 60 characters each
- Use power words, numbers, or emotional triggers
- Keep "What if" format if applicable
- Different approach for each variant

Output ONLY a JSON array of 3 strings:
["Title 1", "Title 2", "Title 3"]"""

    for attempt in range(3):
        try:
            resp = model.generate_content(prompt)
            variants = json.loads(resp.text.strip())
            if isinstance(variants, list) and len(variants) >= 3:
                return variants[:3]
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return []


def score_title(title: str) -> float:
    """
    Basit skor: uzunluk + power kelime sayısı + soru işareti bonusu.
    Yüksek skor = daha iyi CTR potansiyeli.
    """
    power_words = {
        "never", "always", "secret", "revealed", "shocking", "truth",
        "actually", "finally", "incredible", "insane", "brutal", "epic",
        "destroyed", "conquered", "survived", "ultimate", "real", "dark",
    }
    score = 0.0
    words = title.lower().split()
    score += sum(1.5 for w in words if w in power_words)
    score += 1.0 if "?" in title else 0
    score += 0.5 if any(c.isdigit() for c in title) else 0
    # İdeal uzunluk: 40-60 karakter
    if 40 <= len(title) <= 60:
        score += 1.0
    elif len(title) < 30:
        score -= 0.5
    return score


def update_video_title(video_id: str, new_title: str) -> bool:
    """YouTube API ile video başlığını günceller."""
    creds = _get_credentials()
    yt = build("youtube", "v3", credentials=creds)

    # Mevcut snippet'i al
    resp = yt.videos().list(part="snippet", id=video_id).execute()
    if not resp.get("items"):
        print(f"[title_optimizer] Video bulunamadı: {video_id}")
        return False

    snippet = resp["items"][0]["snippet"]
    snippet["title"] = new_title

    yt.videos().update(
        part="snippet",
        body={"id": video_id, "snippet": snippet},
    ).execute()

    print(f"[title_optimizer] Başlık güncellendi: {new_title}")
    return True


def optimize(video_id: str = None) -> None:
    # Video ID'yi bul
    if not video_id:
        if os.path.exists(LAST_VIDEO_PATH):
            with open(LAST_VIDEO_PATH) as f:
                data = json.load(f)
            video_id = data.get("video_id")
            original_title = data.get("title", "")
            hook = data.get("hook", "")
        else:
            print("[title_optimizer] last_video.json bulunamadı, çıkılıyor.")
            return
    else:
        original_title = ""
        hook = ""

    if not video_id:
        print("[title_optimizer] Video ID yok, çıkılıyor.")
        return

    # 24 saatlik görüntülenme
    views = get_video_views_24h(video_id)
    print(f"[title_optimizer] Video: {video_id} | 24s görüntülenme: {views}")

    if views >= VIEWS_THRESHOLD:
        print(f"[title_optimizer] Görüntülenme iyi ({views} >= {VIEWS_THRESHOLD}), başlık değiştirilmiyor.")
        _send(
            f"✅ *Başlık Optimizasyonu*\n"
            f"📹 `{video_id}`\n"
            f"👁  24s görüntülenme: *{views}* (hedef: {VIEWS_THRESHOLD})\n"
            f"🟢 Başlık değiştirilmedi — performans iyi!"
        )
        return

    # Yeni başlık varyantları üret
    print(f"[title_optimizer] Düşük performans ({views} < {VIEWS_THRESHOLD}), yeni başlıklar üretiliyor...")
    variants = generate_title_variants(original_title, hook)

    if not variants:
        print("[title_optimizer] Başlık varyantı üretilemedi.")
        return

    # En iyi başlığı seç
    best = max(variants, key=score_title)
    scores = {v: round(score_title(v), 2) for v in variants}
    print(f"[title_optimizer] Varyantlar: {scores}")
    print(f"[title_optimizer] Seçilen: {best}")

    # Güncelle
    success = update_video_title(video_id, best)

    # Telegram bildirimi
    variants_text = "\n".join(f"  {i+1}. {v}" for i, v in enumerate(variants))
    _send(
        f"🔄 *Başlık Optimizasyonu*\n"
        f"📹 `{video_id}`\n"
        f"👁  24s görüntülenme: *{views}* (hedef: {VIEWS_THRESHOLD})\n\n"
        f"📝 Eski: _{original_title}_\n"
        f"✅ Yeni: *{best}*\n\n"
        f"Diğer varyantlar:\n{variants_text}"
    )


if __name__ == "__main__":
    vid = sys.argv[1] if len(sys.argv) > 1 else None
    optimize(vid)
