"""
ab_thumbnail.py — A/B thumbnail testi.

İki farklı thumbnail varyantı oluşturur:
  Variant A: Orijinal tasarım (sarı başlık, kırmızı arka plan)
  Variant B: Alternatif tasarım (beyaz başlık, koyu mavi/gradient)

24 saat sonra YouTube Analytics ile CTR karşılaştırır,
kazananı aktif thumbnail olarak ayarlar.

Akış:
  1. ab_thumbnail.py generate  → iki PNG üret
  2. YouTube'a Variant A yükle (upload aşamasında)
  3. 24 saat bekle (ab_test.yml cron)
  4. ab_thumbnail.py compare   → CTR karşılaştır, kazananı ayarla
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

# Thumbnail boyutları
W, H = 1280, 720
FONT_DIR = Path("assets/fonts")
AB_STATE_PATH = "output/ab_state.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


# ─────────────────────── Kimlik doğrulama ───────────────────────

def _get_credentials() -> "Credentials":
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


# ─────────────────────── Font yardımcıları ───────────────────────

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        FONT_DIR / "Montserrat-Bold.ttf",
        FONT_DIR / "Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_centered_text(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    color: tuple,
    shadow_color: tuple = None,
    max_width: int = W - 80,
) -> int:
    """Metni yatayda ortalar, çok satırlıysa sarar. Son Y'yi döndürür."""
    lines = _wrap_text(text, font, max_width)
    for line in lines:
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        if shadow_color:
            draw.text((x + 3, y + 3), line, font=font, fill=shadow_color)
        draw.text((x, y), line, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + 12
    return y


# ─────────────────────── Varyant A — Orijinal ───────────────────────

def generate_variant_a(thumbnail_text: str, title: str, output_path: str) -> str:
    """
    Variant A: Kırmızı diagonal gradient, sarı büyük başlık, beyaz alt başlık.
    (Orijinal thumbnail.py tasarımına yakın)
    """
    img = Image.new("RGB", (W, H), (10, 10, 10))
    draw = ImageDraw.Draw(img)

    # Kırmızı gradient sol üst köşe
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(overlay)
    for i in range(400):
        alpha = int(200 * (1 - i / 400))
        grad_draw.ellipse(
            (-100 + i//2, -100 + i//2, 700 - i//2, 500 - i//2),
            fill=(196, 30, 30, alpha),
        )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # "WHAT IF?" etiketi
    tag_font = _load_font(36)
    draw.rectangle([40, 40, 200, 85], fill=(196, 30, 30))
    draw.text((55, 48), "WHAT IF?", font=tag_font, fill=(255, 255, 255))

    # Ana başlık (sarı)
    main_font = _load_font(96)
    _draw_centered_text(
        draw, thumbnail_text.upper(), main_font,
        y=180, color=(255, 220, 0), shadow_color=(0, 0, 0),
    )

    # Alt başlık (beyaz, küçük)
    sub_font = _load_font(38)
    _draw_centered_text(
        draw, title, sub_font,
        y=520, color=(220, 220, 220), shadow_color=(0, 0, 0),
        max_width=W - 120,
    )

    # Varyant etiketi (test sırasında görünmez, üretim'de kaldırılır)
    label_font = _load_font(24)
    draw.text((W - 60, H - 35), "A", font=label_font, fill=(100, 100, 100))

    img.save(output_path, "PNG")
    print(f"[ab] Variant A kaydedildi: {output_path}")
    return output_path


# ─────────────────────── Varyant B — Alternatif ───────────────────────

def generate_variant_b(thumbnail_text: str, title: str, output_path: str) -> str:
    """
    Variant B: Koyu mavi gradient, büyük beyaz başlık, parlak turuncu vurgu çizgisi.
    Daha modern / minimal görünüm.
    """
    # Koyu mavi arka plan
    img = Image.new("RGB", (W, H), (8, 15, 45))
    draw = ImageDraw.Draw(img)

    # Parlak mavi ışık efekti sağ üst
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(overlay)
    for i in range(350):
        alpha = int(160 * (1 - i / 350))
        r = 350 - i
        grad_draw.ellipse(
            (W - r - 50, -r + 50, W + r - 50, r + 50),
            fill=(30, 80, 200, alpha),
        )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Turuncu yatay çizgi
    draw.rectangle([0, H // 2 - 5, W, H // 2 + 5], fill=(255, 120, 0))

    # "WAR HISTORY" küçük üst etiket
    tag_font = _load_font(32)
    tag_text = "⚔ WAR HISTORY"
    bbox = tag_font.getbbox(tag_text)
    tx = (W - (bbox[2] - bbox[0])) // 2
    draw.text((tx + 2, 42), tag_text, font=tag_font, fill=(0, 0, 0))
    draw.text((tx, 40), tag_text, font=tag_font, fill=(255, 165, 0))

    # Ana başlık (beyaz, büyük)
    main_font = _load_font(100)
    _draw_centered_text(
        draw, thumbnail_text.upper(), main_font,
        y=160, color=(255, 255, 255), shadow_color=(0, 0, 60),
    )

    # Alt başlık (açık gri)
    sub_font = _load_font(36)
    _draw_centered_text(
        draw, title, sub_font,
        y=530, color=(200, 210, 255), shadow_color=(0, 0, 20),
        max_width=W - 120,
    )

    # Varyant etiketi
    label_font = _load_font(24)
    draw.text((W - 60, H - 35), "B", font=label_font, fill=(100, 100, 100))

    img.save(output_path, "PNG")
    print(f"[ab] Variant B kaydedildi: {output_path}")
    return output_path


# ─────────────────────── State yönetimi ───────────────────────

def save_ab_state(video_id: str, variant_a_path: str, variant_b_path: str) -> None:
    """A/B test durumunu kaydeder."""
    os.makedirs("output", exist_ok=True)
    state = {
        "video_id": video_id,
        "variant_a": variant_a_path,
        "variant_b": variant_b_path,
        "active_variant": "A",
        "start_time": __import__("datetime").datetime.utcnow().isoformat(),
        "completed": False,
    }
    with open(AB_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    print(f"[ab] A/B state kaydedildi: {AB_STATE_PATH}")


def load_ab_state() -> Optional[dict]:
    if os.path.exists(AB_STATE_PATH):
        with open(AB_STATE_PATH) as f:
            return json.load(f)
    return None


# ─────────────────────── CTR karşılaştırma ───────────────────────

def _get_video_ctr(video_id: str, start_date: str, end_date: str) -> float:
    """
    YouTube Analytics API ile video CTR'ını alır.
    Dönüş: float (ör. 5.2 → %5.2)
    """
    if not YOUTUBE_AVAILABLE:
        return 0.0
    try:
        creds = _get_credentials()
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="annotationClickThroughRate,impressionClickThroughRate",
            dimensions="video",
            filters=f"video=={video_id}",
        ).execute()

        rows = resp.get("rows", [])
        if rows:
            # impressionClickThroughRate genellikle ikinci sütun
            return float(rows[0][2]) * 100 if len(rows[0]) > 2 else 0.0
        return 0.0
    except Exception as e:
        print(f"[ab] CTR alınamadı: {e}")
        return 0.0


def _get_video_impressions(video_id: str, start_date: str, end_date: str) -> int:
    """YouTube Analytics ile izlenim sayısını alır."""
    if not YOUTUBE_AVAILABLE:
        return 0
    try:
        creds = _get_credentials()
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="impressions",
            dimensions="video",
            filters=f"video=={video_id}",
        ).execute()
        rows = resp.get("rows", [])
        return int(rows[0][1]) if rows and len(rows[0]) > 1 else 0
    except Exception as e:
        print(f"[ab] İzlenim alınamadı: {e}")
        return 0


def _upload_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """Belirtilen thumbnail'i YouTube videosuna yükler."""
    if not YOUTUBE_AVAILABLE:
        return False
    try:
        from googleapiclient.http import MediaFileUpload
        creds = _get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
        ).execute()
        print(f"[ab] Thumbnail yüklendi: {thumbnail_path} → {video_id}")
        return True
    except Exception as e:
        print(f"[ab] Thumbnail yüklenemedi: {e}")
        return False


# ─────────────────────── A/B test sonucu ───────────────────────

def compare_and_update() -> dict:
    """
    24 saat sonra çağrılır. CTR karşılaştırır, kazananı yükler.
    """
    state = load_ab_state()
    if not state:
        print("[ab] A/B state bulunamadı.")
        return {}

    if state.get("completed"):
        print("[ab] A/B test zaten tamamlanmış.")
        return state

    video_id = state["video_id"]
    from datetime import datetime, timedelta

    start_dt = datetime.fromisoformat(state["start_time"])
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = (datetime.utcnow()).strftime("%Y-%m-%d")

    print(f"[ab] CTR karşılaştırılıyor: {video_id} ({start_date} → {end_date})")

    # Mevcut durum: Variant A aktif (24 saat boyunca)
    ctr_a = _get_video_ctr(video_id, start_date, end_date)
    impressions_a = _get_video_impressions(video_id, start_date, end_date)

    # Şimdi Variant B'ye geç ve 0 ilave analiz
    # NOT: Gerçek A/B testi için videonun yarısında thumbnail değiştirilmeli.
    # Basitleştirilmiş yaklaşım: A'nın ilk 24 saati ile en iyi tahmini karşılaştır.
    # Variant B'yi yükle ve bir günlük data topla (ikinci run'da karşılaştırılır).

    if state.get("active_variant") == "A":
        # B'ye geç
        print(f"[ab] Variant A CTR: {ctr_a:.2f}% ({impressions_a:,} izlenim)")
        print("[ab] Variant B yükleniyor (24 saat test için)...")

        b_path = state.get("variant_b")
        if b_path and os.path.exists(b_path):
            _upload_thumbnail(video_id, b_path)
            state["active_variant"] = "B"
            state["ctr_a"] = ctr_a
            state["impressions_a"] = impressions_a
            state["switch_time"] = datetime.utcnow().isoformat()
        else:
            print(f"[ab] Variant B dosyası bulunamadı: {b_path}")

    elif state.get("active_variant") == "B":
        # B'nin sonucunu al ve kazananı seç
        ctr_b = _get_video_ctr(video_id, state.get("switch_time", start_date)[:10], end_date)
        ctr_a = state.get("ctr_a", 0)
        impressions_b = _get_video_impressions(video_id, state.get("switch_time", start_date)[:10], end_date)

        print(f"[ab] Variant A CTR: {ctr_a:.2f}% | Variant B CTR: {ctr_b:.2f}%")

        winner = "B" if ctr_b > ctr_a else "A"
        winner_path = state["variant_b"] if winner == "B" else state["variant_a"]

        print(f"[ab] KAZANAN: Variant {winner} (CTR: {'B: '+str(round(ctr_b,2)) if winner=='B' else 'A: '+str(round(ctr_a,2))}%)")

        # Kazananı yükle (B zaten aktifse sadece A kazanınca değiştir)
        if winner == "A":
            _upload_thumbnail(video_id, winner_path)

        state["winner"] = winner
        state["ctr_b"] = ctr_b
        state["impressions_b"] = impressions_b
        state["completed"] = True

        # Telegram + Discord bildir
        _notify_ab_result(state)

    with open(AB_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

    return state


def _notify_ab_result(state: dict) -> None:
    """A/B test sonucunu Telegram + Discord'a bildirir."""
    winner = state.get("winner", "?")
    ctr_a = state.get("ctr_a", 0)
    ctr_b = state.get("ctr_b", 0)

    msg = (
        f"🎨 *A/B Thumbnail Test Tamamlandı*\n\n"
        f"🏆 Kazanan: *Variant {winner}*\n"
        f"📊 Variant A CTR: `{ctr_a:.2f}%`\n"
        f"📊 Variant B CTR: `{ctr_b:.2f}%`\n"
        f"🎬 Video: `{state.get('video_id', '')}`"
    )

    try:
        from notifier import _send_message
        _send_message(msg)
    except Exception as e:
        print(f"[ab] Telegram bildirimi gönderilemedi: {e}")

    try:
        from discord_notify import _post
        _post({
            "embeds": [{
                "title": f"🎨 A/B Test Tamamlandı — Kazanan: Variant {winner}",
                "color": 0xF39C12,
                "fields": [
                    {"name": "Variant A CTR", "value": f"{ctr_a:.2f}%", "inline": True},
                    {"name": "Variant B CTR", "value": f"{ctr_b:.2f}%", "inline": True},
                    {"name": "Video ID", "value": state.get("video_id", "—"), "inline": False},
                ],
                "footer": {"text": "WAR SHORTS A/B Thumbnail Test"},
            }]
        })
    except Exception as e:
        print(f"[ab] Discord bildirimi gönderilemedi: {e}")


# ─────────────────────── Ana giriş noktası ───────────────────────

def generate_thumbnails(thumbnail_text: str, title: str, output_dir: str = "output") -> tuple[str, str]:
    """
    İki thumbnail varyantı üretir.
    Returns: (variant_a_path, variant_b_path)
    """
    os.makedirs(output_dir, exist_ok=True)
    a_path = os.path.join(output_dir, "thumbnail_a.png")
    b_path = os.path.join(output_dir, "thumbnail_b.png")
    generate_variant_a(thumbnail_text, title, a_path)
    generate_variant_b(thumbnail_text, title, b_path)
    return a_path, b_path


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"

    if mode == "generate":
        text = sys.argv[2] if len(sys.argv) > 2 else "ROME NEVER FELL?"
        title = sys.argv[3] if len(sys.argv) > 3 else "What if Rome Never Fell?"
        a, b = generate_thumbnails(text, title)
        print(f"Variant A: {a}")
        print(f"Variant B: {b}")

    elif mode == "compare":
        result = compare_and_update()
        print(json.dumps(result, indent=2, default=str))

    else:
        print(f"Bilinmeyen mod: {mode}")
        print("Kullanım: python ab_thumbnail.py [generate|compare] [text] [title]")
        sys.exit(1)
