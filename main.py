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
from datetime import date

from script_gen import generate_script, save_script
from tts import generate_audio
from video_builder import build_video
from thumbnail import generate_thumbnail
from uploader import upload_video, build_description
from notifier import send_notification


TOPIC_POOL_PATH = "topic_pool.json"
USED_TOPICS_PATH = "used_topics.json"
OUTPUT_DIR = "output"


def load_topics() -> list:
    with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_used() -> dict:
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"used": [], "last_run": None}


def save_used(used_data: dict) -> None:
    with open(USED_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(used_data, f, indent=2, ensure_ascii=False)


def pick_topic(override: str = None) -> str:
    """
    Kullanılmamış bir konu seçer. Tüm konular kullanılmışsa listeyi sıfırlar.
    """
    if override:
        return override

    all_topics = load_topics()
    used_data = load_used()
    used_set = set(used_data.get("used", []))

    available = [t for t in all_topics if t not in used_set]

    if not available:
        print("[main] Tüm konular kullanıldı, liste sıfırlanıyor.")
        available = all_topics
        used_data["used"] = []

    topic = available[0]
    used_data["used"].append(topic)
    used_data["last_run"] = str(date.today())
    save_used(used_data)

    return topic


def cleanup_outputs() -> None:
    """Önceki çalıştırmadan kalan output dosyalarını temizler."""
    files = [
        f"{OUTPUT_DIR}/script.json",
        f"{OUTPUT_DIR}/narration.mp3",
        f"{OUTPUT_DIR}/short.mp4",
        f"{OUTPUT_DIR}/thumbnail.png",
    ]
    for f in files:
        if os.path.exists(f):
            os.remove(f)


def run(dry_run: bool = False, topic_override: str = None) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_outputs()

    print("=" * 50)
    print("⚔️  WAR SHORTS — Pipeline Başlatıldı")
    print("=" * 50)

    # 1) Konu seç
    topic = pick_topic(topic_override)
    print(f"\n[main] Konu: {topic}")

    # 2) Script üret
    print("\n[main] Script üretiliyor...")
    script = generate_script(topic)
    save_script(script)
    print(f"[main] Script: {script['title']}")

    # 3) TTS — ses + VTT altyazı zamanlaması üret
    print("\n[main] Ses üretiliyor...")
    audio_path, vtt_path = generate_audio(script["narration"])

    # Ses süresini al
    from moviepy.editor import AudioFileClip
    audio_clip = AudioFileClip(audio_path)
    duration_sec = audio_clip.duration
    audio_clip.close()

    # 4) Video üret
    print("\n[main] Video üretiliyor...")
    video_path = build_video(script, audio_path, vtt_path)

    # 5) Thumbnail üret
    print("\n[main] Thumbnail üretiliyor...")
    thumb_path = generate_thumbnail(script["title"], script["thumbnail_text"])

    if dry_run:
        print("\n" + "=" * 50)
        print("✅ DRY RUN TAMAMLANDI (upload atlandı)")
        print(f"   Script:    {OUTPUT_DIR}/script.json")
        print(f"   Ses:       {audio_path}")
        print(f"   Video:     {video_path}")
        print(f"   Thumbnail: {thumb_path}")
        print("=" * 50)
        return

    # 6) YouTube'a yükle
    print("\n[main] YouTube'a yükleniyor...")
    video_id = upload_video(
        video_path=video_path,
        title=script["title"],
        description=build_description(script),
        tags=script["tags"] + ["Shorts", "History", "WhatIf", "WarHistory"],
        thumbnail_path=thumb_path,
    )

    # 7) Telegram bildirimi
    print("\n[main] Telegram bildirimi gönderiliyor...")
    send_notification(
        title=script["title"],
        video_id=video_id,
        duration_sec=duration_sec,
        tags=script["tags"],
    )

    print("\n" + "=" * 50)
    print(f"✅ TAMAMLANDI! https://youtube.com/shorts/{video_id}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WAR SHORTS Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Upload olmadan test et")
    parser.add_argument("--topic", type=str, default=None, help="Belirli bir konu belirt")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, topic_override=args.topic)
    except Exception as e:
        print(f"\n❌ HATA: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
