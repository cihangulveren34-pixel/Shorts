"""
freq_batch_producer.py — FREQ SHORTS için toplu video üretimi.

Kullanım:
  python freq_batch_producer.py              # 7 video üret
  python freq_batch_producer.py --count 3   # 3 video üret
  python freq_batch_producer.py --dry-run   # sadece script üret (ses/video yok)
  python freq_batch_producer.py --next      # kuyruktaki sonraki videoyu göster

Üretilen videolar freq_scheduled_queue.json'a kaydedilir.
freq_main.py USE_QUEUE=true ile bu kuyruktan yayınlar.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

from freq_script_gen import generate_freq_script, save_freq_script
from freq_audio_gen import generate_frequency_audio
from freq_video_builder import build_freq_video
from freq_main import pick_topic
from notifier import _send

QUEUE_PATH = "freq_scheduled_queue.json"
BATCH_DIR = "freq_batch_output"


# ─── Kuyruk yardımcıları ─────────────────────────────────────────────────────

def load_queue() -> list:
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue: list) -> None:
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def get_next_queued() -> dict | None:
    """Bugün yayınlanacak (veya gecikmiş) ilk kuyruk öğesini döndürür."""
    queue = load_queue()
    today = str(date.today())
    for item in queue:
        if not item.get("published") and item["scheduled_date"] <= today:
            if item.get("video_path") and os.path.exists(item["video_path"]):
                return item
    return None


def mark_published(scheduled_date: str) -> None:
    queue = load_queue()
    for item in queue:
        if item["scheduled_date"] == scheduled_date:
            item["published"] = True
            item["published_at"] = str(date.today())
    save_queue(queue)


# ─── Batch üretim ────────────────────────────────────────────────────────────

def produce_batch(count: int = 7, dry_run: bool = False) -> None:
    os.makedirs(BATCH_DIR, exist_ok=True)

    queue = load_queue()
    existing_dates = {item["scheduled_date"] for item in queue}

    if queue:
        last_date = max(date.fromisoformat(d) for d in existing_dates)
        start_date = last_date + timedelta(days=1)
    else:
        start_date = date.today() + timedelta(days=1)

    print("=" * 52)
    print(f"🎵  FREQ BATCH — {count} video, {start_date}'den itibaren")
    print("=" * 52)

    produced = []
    for i in range(count):
        slot_date = start_date + timedelta(days=i)
        video_dir = os.path.join(BATCH_DIR, str(slot_date))
        os.makedirs(video_dir, exist_ok=True)

        print(f"\n[{i+1}/{count}] Tarih: {slot_date}")

        topic = None
        try:
            # 1) Frekans seç
            topic = pick_topic()
            print(f"  Frekans: {topic['name']} — {topic['short_benefit']}")

            # 2) Script/metadata üret
            script = generate_freq_script(topic)
            script_path = os.path.join(video_dir, "freq_script.json")
            save_freq_script(script, script_path)
            print(f"  Başlık: {script['title']}")

            if dry_run:
                produced.append({
                    "scheduled_date": str(slot_date),
                    "hz": topic["hz"],
                    "freq_name": topic["name"],
                    "title": script["title"],
                    "script_path": script_path,
                    "audio_path": None,
                    "video_path": None,
                    "published": False,
                    "dry_run": True,
                })
                continue

            # 3) Frekans sesi üret
            audio_path = os.path.join(video_dir, "freq_audio.mp3")
            generate_frequency_audio(
                hz=float(topic["hz"]),
                output_mp3=audio_path,
                duration_sec=62.0,
            )

            # 4) Video üret
            video_path = os.path.join(video_dir, "freq_short.mp4")
            build_freq_video(script, audio_path, video_path)

            produced.append({
                "scheduled_date": str(slot_date),
                "hz": topic["hz"],
                "freq_name": topic["name"],
                "title": script["title"],
                "script_path": script_path,
                "audio_path": audio_path,
                "video_path": video_path,
                "published": False,
            })

            print(f"  ✅ Hazır: {video_path}")

        except Exception as e:
            print(f"  ❌ Hata: {e}", file=sys.stderr)
            produced.append({
                "scheduled_date": str(slot_date),
                "hz": topic["hz"] if topic else "?",
                "freq_name": topic["name"] if topic else "?",
                "title": "?",
                "script_path": None,
                "audio_path": None,
                "video_path": None,
                "published": False,
                "error": str(e),
            })

        if i < count - 1:
            time.sleep(1)

    queue.extend(produced)
    save_queue(queue)

    success = sum(1 for p in produced if not p.get("error"))
    print(f"\n{'='*52}")
    print(f"✅ Batch tamamlandı: {success}/{count} video üretildi")
    print(f"   Kuyruk: {QUEUE_PATH}")
    print(f"{'='*52}")

    try:
        _send(
            f"🎵 *FREQ Batch Tamamlandı*\n\n"
            f"✅ {success}/{count} video hazır\n"
            f"📅 {start_date} → {start_date + timedelta(days=count-1)}\n\n"
            + "\n".join(
                f"{'✅' if not p.get('error') else '❌'} {p['scheduled_date']}: {p.get('title', '?')}"
                for p in produced
            )
        )
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FREQ SHORTS — Batch Producer")
    parser.add_argument("--count", type=int, default=7, help="Üretilecek video sayısı")
    parser.add_argument("--dry-run", action="store_true", help="Sadece script üret (ses/video yok)")
    parser.add_argument("--next", action="store_true", help="Kuyruktaki sonraki videoyu göster")
    args = parser.parse_args()

    if args.next:
        item = get_next_queued()
        if item:
            print(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            print("Kuyrukta bekleyen video yok.")
    else:
        produce_batch(args.count, args.dry_run)
