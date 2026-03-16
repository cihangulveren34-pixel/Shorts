"""
weekly_compilation.py — Haftanın Shorts'larını tek uzun video'ya derler.

Her Pazar batch üretiminden sonra veya manuel çalıştırıldığında:
  1. Son 7 günün üretilmiş videolarını toplar
  2. Aralarına başlık kartı ekler (MoviePy TextClip)
  3. Tek MP4'e birleştirir (crossfade ile)
  4. "This Week in WAR SHORTS" başlığıyla YouTube'a yükler
  5. Playlist'e ekler

Bu derleme videosu kanal izlenme süresini önemli ölçüde artırır
(YouTube'un long-form içeriği Shorts'a kıyasla farklı dağıtım algoritmasına sahip).

Gereksinimler:
  - MoviePy + FFmpeg (zaten kurulu)
  - YOUTUBE_TOKEN_JSON
"""

import json
import os
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

try:
    from moviepy.editor import (
        VideoFileClip, TextClip, CompositeVideoClip,
        concatenate_videoclips, ColorClip, AudioFileClip,
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


OUTPUT_DIR = "output"
COMPILATION_PATH = os.path.join(OUTPUT_DIR, "weekly_compilation.mp4")
COMPILATION_THUMB_PATH = os.path.join(OUTPUT_DIR, "compilation_thumb.png")

# Derleme video boyutu — landscape (YouTube long-form için daha iyi)
COMP_W, COMP_H = 1920, 1080
CARD_DURATION = 3.0      # Her video başlık kartı süresi (saniye)
CROSSFADE = 0.5          # Geçiş süresi


def _find_week_videos(days: int = 7) -> list[dict]:
    """
    Son N günün üretilmiş videolarını batch veya output dizininden bulur.
    scheduled_queue.json'dan yayınlanmış videoları da kontrol eder.
    """
    cutoff = date.today() - timedelta(days=days)
    videos = []

    # 1) scheduled_queue.json'dan
    queue_path = "scheduled_queue.json"
    if os.path.exists(queue_path):
        with open(queue_path, encoding="utf-8") as f:
            queue = json.load(f)
        for item in queue:
            if item.get("published") and item.get("video_path"):
                try:
                    item_date = date.fromisoformat(item["scheduled_date"])
                    if item_date >= cutoff and os.path.exists(item["video_path"]):
                        videos.append({
                            "path": item["video_path"],
                            "title": item.get("title", "WAR SHORTS"),
                            "date": item["scheduled_date"],
                        })
                except (ValueError, KeyError):
                    continue

    # 2) batch_output dizininden
    batch_root = Path("batch_output")
    if batch_root.exists():
        for day_dir in sorted(batch_root.iterdir()):
            try:
                dir_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if dir_date < cutoff:
                continue
            for mp4 in day_dir.glob("*.mp4"):
                if str(mp4) not in [v["path"] for v in videos]:
                    title_file = mp4.with_suffix(".json")
                    title = mp4.stem
                    if title_file.exists():
                        try:
                            with open(title_file) as f:
                                data = json.load(f)
                            title = data.get("title", title)
                        except Exception:
                            pass
                    videos.append({
                        "path": str(mp4),
                        "title": title,
                        "date": day_dir.name,
                    })

    # Tarihe göre sırala
    videos.sort(key=lambda v: v["date"])
    return videos


def _make_title_card(title: str, video_number: int, total: int) -> "ColorClip":
    """
    Video başlığını gösteren 3 saniyelik başlık kartı üretir.
    """
    card = ColorClip(size=(COMP_W, COMP_H), color=(10, 10, 10), duration=CARD_DURATION)

    try:
        number_txt = TextClip(
            f"#{video_number}/{total}",
            fontsize=60, color="red", font="Liberation-Sans-Bold",
            size=(COMP_W, None), method="caption",
        ).set_duration(CARD_DURATION).set_position(("center", 350))

        title_txt = TextClip(
            title,
            fontsize=72, color="white", font="Liberation-Sans-Bold",
            size=(COMP_W - 100, None), method="caption",
        ).set_duration(CARD_DURATION).set_position(("center", 440))

        return CompositeVideoClip([card, number_txt, title_txt])
    except Exception:
        # TextClip başarısız → sadece renk kartı
        return card


def _resize_to_landscape(clip: "VideoFileClip") -> "VideoFileClip":
    """
    Dikey 1080×1920 video'yu 1920×1080'e döndürür (pillarbox ile).
    """
    # Dikey video → 1920×1080'e sığdır (letterbox/pillarbox)
    scale = COMP_H / clip.h
    new_w = int(clip.w * scale)
    resized = clip.resize(height=COMP_H)

    if new_w < COMP_W:
        # Pillarbox (siyah yan bantlar)
        bg = ColorClip(size=(COMP_W, COMP_H), color=(0, 0, 0), duration=clip.duration)
        x_offset = (COMP_W - new_w) // 2
        return CompositeVideoClip([bg, resized.set_position((x_offset, 0))])

    return resized.crop(x_center=new_w // 2, width=COMP_W)


def _generate_compilation_thumbnail(titles: list[str], video_count: int) -> str:
    """Derleme için özel thumbnail üretir."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1280, 720), (5, 5, 20))
        draw = ImageDraw.Draw(img)

        # Kırmızı gradient
        for i in range(300):
            alpha = int(150 * (1 - i / 300))
            draw.rectangle([0, 0, 300 - i, 400 - i], fill=(180, 20, 20))

        # Ana başlık
        try:
            font_big = ImageFont.truetype(
                "assets/fonts/Montserrat-Bold.ttf", 80
            )
            font_mid = ImageFont.truetype(
                "assets/fonts/Montserrat-Bold.ttf", 40
            )
            font_small = ImageFont.truetype(
                "assets/fonts/Montserrat-Bold.ttf", 28
            )
        except Exception:
            font_big = font_mid = font_small = ImageFont.load_default()

        draw.text((50, 50), "⚔️ THIS WEEK", font=font_big, fill=(255, 220, 0))
        draw.text((50, 150), "IN WAR SHORTS", font=font_big, fill=(255, 255, 255))
        draw.text((50, 280), f"{video_count} VIDEOS", font=font_mid, fill=(200, 200, 200))

        for i, t in enumerate(titles[:4]):
            draw.text((50, 360 + i * 80), f"• {t[:45]}", font=font_small, fill=(180, 180, 180))

        img.save(COMPILATION_THUMB_PATH, "PNG")
        return COMPILATION_THUMB_PATH
    except Exception as e:
        print(f"[compilation] Thumbnail üretilemedi: {e}")
        return ""


def build_compilation(days: int = 7) -> str | None:
    """
    Son 7 günün videolarını derler.

    Returns:
        Derleme MP4 dosya yolu, veya başarısız olursa None
    """
    if not MOVIEPY_AVAILABLE:
        print("[compilation] MoviePy kurulu değil.")
        return None

    videos = _find_week_videos(days)
    if not videos:
        print(f"[compilation] Son {days} gündeki video bulunamadı.")
        return None

    print(f"[compilation] {len(videos)} video derleniyor...")

    clips = []
    for i, v in enumerate(videos, 1):
        print(f"[compilation]  {i}/{len(videos)}: {v['title'][:50]}")
        try:
            # Başlık kartı
            card = _make_title_card(v["title"], i, len(videos))
            clips.append(card)

            # Video
            clip = VideoFileClip(v["path"])
            landscape = _resize_to_landscape(clip)
            # Crossfade
            if clips:
                landscape = landscape.crossfadein(CROSSFADE)
            clips.append(landscape)
        except Exception as e:
            print(f"[compilation] Video işlenemedi {v['path']}: {e}")
            continue

    if not clips:
        print("[compilation] Hiçbir video işlenemedi.")
        return None

    # Birleştir
    print("[compilation] Birleştiriliyor...")
    try:
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        final.write_videofile(
            COMPILATION_PATH,
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="fast",
            threads=2,
            logger=None,
        )
        final.close()
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        print(f"[compilation] Derleme tamamlandı: {COMPILATION_PATH}")
        return COMPILATION_PATH
    except Exception as e:
        print(f"[compilation] Birleştirme hatası: {e}")
        return None


def upload_compilation(compilation_path: str, videos: list[dict]) -> str | None:
    """
    Derleme videosunu YouTube'a yükler.

    Returns:
        YouTube video ID
    """
    try:
        from uploader import upload_video, build_description
        from playlist_manager import add_to_playlist

        week_start = (date.today() - timedelta(days=7)).strftime("%b %d")
        week_end = date.today().strftime("%b %d, %Y")

        title = f"WAR SHORTS Weekly Compilation — {week_start}–{week_end}"
        titles_list = "\n".join(f"• {v['title']}" for v in videos)

        description = (
            f"This week's collection of alternate history 'What If' shorts!\n\n"
            f"📺 Videos this week:\n{titles_list}\n\n"
            f"🔔 Subscribe for daily history shorts!\n\n"
            f"#WarHistory #WhatIf #AlternateHistory #HistoryShorts #WeeklyCompilation"
        )

        tags = ["WarHistory", "WhatIf", "AlternateHistory", "Shorts", "WeeklyCompilation",
                "History", "Compilation", "HistoryFacts"]

        thumb_path = _generate_compilation_thumbnail(
            [v["title"] for v in videos], len(videos)
        )

        video_id = upload_video(
            video_path=compilation_path,
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=thumb_path or None,
        )

        if video_id:
            print(f"[compilation] YouTube'a yüklendi: {video_id}")
            comp_script = {"title": title, "tags": tags}
            add_to_playlist(video_id, comp_script)

        return video_id
    except Exception as e:
        print(f"[compilation] Upload hatası: {e}")
        return None


def run_weekly_compilation() -> dict:
    """
    Tam derleme akışı: build → upload.
    weekly_report.yml veya batch.yml'den çağrılır.
    """
    videos = _find_week_videos(days=7)
    print(f"[compilation] {len(videos)} video bulundu.")

    if len(videos) < 2:
        print("[compilation] En az 2 video gerekli, atlandı.")
        return {"skipped": True, "reason": "insufficient_videos"}

    path = build_compilation()
    if not path:
        return {"error": "build_failed"}

    video_id = upload_compilation(path, videos)

    result = {
        "video_count": len(videos),
        "compilation_path": path,
        "youtube_video_id": video_id,
        "uploaded": bool(video_id),
    }
    print(f"[compilation] Tamamlandı: {result}")
    return result


if __name__ == "__main__":
    result = run_weekly_compilation()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
