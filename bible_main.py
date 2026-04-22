"""
bible_main.py — BIBLE SHORTS pipeline orkestratörü.

Kullanım:
  python bible_main.py                      # Normal çalıştırma
  python bible_main.py --dry-run            # Upload olmadan test
  python bible_main.py --topic 0            # Belirli hikaye indexi ile çalıştır

Pipeline:
  1) bible_topic_pool.json'dan hikaye seç
  2) Gemini ile narration + metadata üret
  3) 12 dil localization üret
  4) Edge-TTS → MP3 + VTT
  5) Pexels'ten spiritual footage indir
  6) Video montaj (footage + altyazı overlay + hook + moral)
  7) YouTube'a yükle (categoryId="22" People & Blogs)
  8) VTT altyazı upload
  9) Telegram bildirimi
"""

import argparse
import json
import os
import random
import sys
import traceback

from bible_script_gen import generate_bible_script, save_bible_script
from freq_script_gen import generate_localizations
from tts import generate_audio
from bible_video_builder import build_bible_video
from notifier import send_notification, send_error_notification

OUTPUT_DIR = "output"
TOPIC_POOL_PATH = "bible_topic_pool.json"
USED_TOPICS_PATH = "bible_used_topics.json"
BIBLE_SCRIPT_PATH = os.path.join(OUTPUT_DIR, "bible_script.json")
BIBLE_AUDIO_PATH = os.path.join(OUTPUT_DIR, "narration.mp3")
BIBLE_VTT_PATH = os.path.join(OUTPUT_DIR, "narration.vtt")
BIBLE_VIDEO_PATH = os.path.join(OUTPUT_DIR, "bible_short.mp4")

# TTS ayarları — derin, ciddi, hikaye anlatıcı ses
TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+10%"
TTS_PITCH = "-8Hz"


# ─── Seçim & durum ──────────────────────────────────────────────────────────

def _load_pool() -> list:
    with open(TOPIC_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_used() -> list:
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_used(used: list) -> None:
    with open(USED_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(used, f, indent=2)


def pick_topic(index_override: int = None) -> dict:
    """
    Hikaye seçer. index_override verilmişse o indexteki hikayeyi döner.
    Aksi halde kullanılmamış hikayelerden rastgele seçer.
    Tüm hikayeler kullanıldıysa listeyi sıfırlar.
    """
    pool = _load_pool()

    if index_override is not None:
        if 0 <= index_override < len(pool):
            return pool[index_override]
        raise ValueError(f"Geçersiz topic index: {index_override} (havuzda {len(pool)} hikaye var)")

    used = _load_used()
    used_set = set(used)

    available = [t for t in pool if t["story_id"] not in used_set]
    if not available:
        print("[bible_main] Tüm hikayeler kullanıldı — liste sıfırlanıyor.")
        used = []
        _save_used(used)
        available = pool

    topic = random.choice(available)
    used.append(topic["story_id"])
    _save_used(used)
    return topic


# ─── Adım çalıştırıcı ────────────────────────────────────────────────────────

def _step(name: str, fn, topic_name: str = ""):
    try:
        return fn()
    except Exception as e:
        print(f"\n[bible_main] HATA — {name}: {e}", file=sys.stderr)
        traceback.print_exc()
        try:
            send_error_notification(name, e, topic_name)
        except Exception:
            pass
        raise


# ─── Pipeline ────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, topic_override: int = None) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Önceki çıktıları temizle
    for p in [BIBLE_AUDIO_PATH, BIBLE_VTT_PATH, BIBLE_VIDEO_PATH, BIBLE_SCRIPT_PATH]:
        if os.path.exists(p):
            os.remove(p)

    print("=" * 52)
    print("📖  BIBLE SHORTS — Pipeline Başlatıldı")
    print("=" * 52)

    # 1) Hikaye seç
    topic = pick_topic(topic_override)
    print(f"\n[bible_main] Seçilen hikaye: {topic['title']} ({topic['book']})")

    # 2) Script/metadata üret (Gemini)
    print("\n[bible_main] Narration + metadata üretiliyor...")
    script = _step(
        "Script üretimi",
        lambda: generate_bible_script(topic),
        topic["title"],
    )
    save_bible_script(script, BIBLE_SCRIPT_PATH)
    print(f"[bible_main] Başlık: {script['title']}")
    print(f"[bible_main] Narration: {len(script['narration'].split())} kelime")

    # 3) Çoklu dil çevirileri
    print("\n[bible_main] Çoklu dil çevirileri üretiliyor...")
    localizations = _step(
        "Localization çevirisi",
        lambda: generate_localizations(script),
        topic["title"],
    )
    if not localizations:
        raise RuntimeError("Localization üretilemedi — video yayınlanmayacak.")

    # 4) Edge-TTS → MP3 + VTT
    print(f"\n[bible_main] TTS üretiliyor (ses: {TTS_VOICE})...")
    audio_path, vtt_path = _step(
        "TTS üretimi",
        lambda: generate_audio(script["narration"], OUTPUT_DIR, voice=TTS_VOICE, rate=TTS_RATE, pitch=TTS_PITCH),
        topic["title"],
    )

    # 5-6) Video montaj (Pexels indir + overlay + birleştir)
    print("\n[bible_main] Video montajı yapılıyor...")
    video_path = _step(
        "Video montajı",
        lambda: build_bible_video(script, audio_path, vtt_path, BIBLE_VIDEO_PATH),
        topic["title"],
    )

    if dry_run:
        script["localizations"] = localizations
        save_bible_script(script, BIBLE_SCRIPT_PATH)

        print("\n" + "=" * 52)
        print("✅  DRY RUN TAMAMLANDI (upload atlandı)")
        print(f"   Script → {BIBLE_SCRIPT_PATH}")
        print(f"   Ses    → {audio_path}")
        print(f"   VTT    → {vtt_path}")
        print(f"   Video  → {video_path}")
        print("=" * 52)
        return

    # 7) YouTube'a yükle
    print("\n[bible_main] YouTube'a yükleniyor...")
    from uploader import upload_video

    base_tags = ["Bible Story", "Bible Shorts", "Christian Shorts", "Faith",
                 "Scripture", "God", "Jesus", "Shorts"]
    upload_tags = list(dict.fromkeys(script["tags"] + base_tags))

    description = script.get("description", f"{script['title']}\n\n#BibleStory #Faith #Shorts")

    video_id = _step(
        "YouTube upload",
        lambda: upload_video(
            video_path=video_path,
            title=script["title"],
            description=description,
            tags=upload_tags,
            thumbnail_path=None,
            localizations=localizations,
            category_id="22",  # People & Blogs
        ),
        topic["title"],
    )

    print(f"\n[bible_main] Video yüklendi: https://youtube.com/shorts/{video_id}")

    # 8) VTT altyazı upload
    print("\n[bible_main] Altyazı yükleniyor...")
    try:
        from captions_uploader import upload_captions
        upload_captions(video_id, vtt_path, language="en", name="English")
    except Exception as e:
        print(f"[bible_main] Altyazı yüklenemedi (kritik değil): {e}")

    # 9) Telegram bildirimi
    print("\n[bible_main] Bildirim gönderiliyor...")
    try:
        send_notification(
            title=script["title"],
            video_id=video_id,
            duration_sec=60,
            tags=script["tags"],
        )
    except Exception as e:
        print(f"[bible_main] Telegram bildirimi gönderilemedi (kritik değil): {e}")

    print("\n" + "=" * 52)
    print(f"✅  TAMAMLANDI! (BIBLE SHORTS)")
    print(f"   https://youtube.com/shorts/{video_id}")
    print("=" * 52)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BIBLE SHORTS Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Upload olmadan test et")
    parser.add_argument("--topic", type=int, default=None, help="Belirli bir hikaye indexi (0-based)")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, topic_override=args.topic)
    except Exception as e:
        print(f"\n❌ Pipeline başarısız: {e}", file=sys.stderr)
        sys.exit(1)
