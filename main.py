"""
main.py — WAR SHORTS pipeline orkestratörü.

Kullanım:
  python main.py                    # Normal çalıştırma
  python main.py --dry-run          # Upload olmadan test
  python main.py --topic "..."      # Belirli konu ile çalıştır
"""

import argparse
import json
import os
import sys
import traceback
from datetime import date  # noqa: F401 (used by topic_selector)

from script_gen import generate_script, save_script
from tts import generate_audio
from video_builder import build_video
from thumbnail import generate_thumbnail
from uploader import upload_video, build_description, post_pinned_comment
from notifier import send_notification, send_error_notification
from topic_selector import pick_trending_topic


OUTPUT_DIR = "output"
USED_TOPICS_PATH = "used_topics.json"

# Adım adları — hata bildirimlerinde kullanılır
STEP_NAMES = {
    "script":    "Script üretimi (Gemini)",
    "tts":       "Ses üretimi (Edge TTS)",
    "video":     "Video montajı (MoviePy)",
    "thumbnail": "Thumbnail (Pillow)",
    "upload":    "YouTube upload",
    "notify":    "Telegram bildirimi",
}


def save_used(used_data: dict) -> None:
    with open(USED_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(used_data, f, indent=2, ensure_ascii=False)


def cleanup_outputs() -> None:
    for fname in ["script.json", "narration.mp3", "narration.vtt", "short.mp4", "thumbnail.png"]:
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path):
            os.remove(path)


def _step(name: str, fn, topic: str = ""):
    """
    Bir pipeline adımını çalıştırır.
    Hata olursa Telegram'a bildirir ve hatayı yeniden fırlatır.
    """
    try:
        return fn()
    except Exception as e:
        label = STEP_NAMES.get(name, name)
        print(f"\n[main] ❌ HATA — {label}: {e}", file=sys.stderr)
        traceback.print_exc()
        send_error_notification(label, e, topic)
        raise


def run(dry_run: bool = False, topic_override: str = None) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_outputs()

    print("=" * 52)
    print("⚔️   WAR SHORTS — Pipeline Başlatıldı")
    print("=" * 52)

    # 1) Trending konu seç (Google Trends + fallback)
    topic, used_data = pick_trending_topic(topic_override)
    save_used(used_data)
    print(f"\n[main] Konu: {topic}")

    # 2) Script
    print("\n[main] Script üretiliyor...")
    script = _step("script", lambda: generate_script(topic), topic)
    save_script(script)
    print(f"[main] Başlık: {script['title']}")

    # 3) TTS + VTT
    print("\n[main] Ses üretiliyor...")
    audio_path, vtt_path = _step("tts", lambda: generate_audio(script["narration"]), topic)

    from moviepy.editor import AudioFileClip
    clip = AudioFileClip(audio_path)
    duration_sec = clip.duration
    clip.close()

    # 4) Video
    print("\n[main] Video üretiliyor (3 klip + CTA + crossfade)...")
    video_path = _step("video", lambda: build_video(script, audio_path, vtt_path), topic)

    # 5) Thumbnail
    print("\n[main] Thumbnail üretiliyor...")
    thumb_path = _step(
        "thumbnail",
        lambda: generate_thumbnail(script["title"], script["thumbnail_text"]),
        topic,
    )

    if dry_run:
        print("\n" + "=" * 52)
        print("✅  DRY RUN TAMAMLANDI (upload atlandı)")
        print(f"   Script    → {OUTPUT_DIR}/script.json")
        print(f"   Ses       → {audio_path}")
        print(f"   Video     → {video_path}")
        print(f"   Thumbnail → {thumb_path}")
        print("=" * 52)
        return

    # 6) YouTube upload
    print("\n[main] YouTube'a yükleniyor...")
    video_id = _step(
        "upload",
        lambda: upload_video(
            video_path=video_path,
            title=script["title"],
            description=build_description(script),
            tags=script["tags"] + ["Shorts", "History", "WhatIf", "WarHistory"],
            thumbnail_path=thumb_path,
        ),
        topic,
    )

    # 7) Pinned yorum gönder
    print("\n[main] Pinned yorum gönderiliyor...")
    try:
        from uploader import _get_credentials
        from googleapiclient.discovery import build as yt_build
        creds = _get_credentials()
        yt = yt_build("youtube", "v3", credentials=creds)
        post_pinned_comment(
            yt,
            video_id,
            "Which alternate outcome do you think is most likely? 👇 Let us know!"
        )
    except Exception as e:
        print(f"[main] Yorum gönderilemedi (kritik değil): {e}")

    # 8) Telegram başarı bildirimi
    print("\n[main] Telegram bildirimi gönderiliyor...")
    try:
        send_notification(
            title=script["title"],
            video_id=video_id,
            duration_sec=duration_sec,
            tags=script["tags"],
        )
    except Exception as e:
        print(f"[main] Telegram bildirimi gönderilemedi (kritik değil): {e}")

    print("\n" + "=" * 52)
    print(f"✅  TAMAMLANDI!")
    print(f"   https://youtube.com/shorts/{video_id}")
    print("=" * 52)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WAR SHORTS Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Upload olmadan test et")
    parser.add_argument("--topic", type=str, default=None, help="Belirli bir konu belirt")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, topic_override=args.topic)
    except Exception as e:
        print(f"\n❌ Pipeline başarısız: {e}", file=sys.stderr)
        sys.exit(1)
