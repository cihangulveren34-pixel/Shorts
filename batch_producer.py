"""
batch_producer.py — Bir haftanın videolarını (7 adet) tek seferde üretir.
Üretilen scriptler + ses + video dosyaları scheduled_queue.json'a yazılır.
Daily pipeline her gün kuyruktan 1 video yayınlar.

Kullanım:
  python batch_producer.py            # 7 video üret
  python batch_producer.py --count 3  # 3 video üret
  python batch_producer.py --dry-run  # sadece scriptleri üret (video yok)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta

from script_gen import save_script
from tts import generate_audio
from video_builder import build_video
from thumbnail import generate_thumbnail
from topic_selector import pick_trending_topic
from notifier import _send

# ─── v2 modülleri ──────────────────────────────────────────────────────
from smart_regenerator import smart_generate
from trend_predictor import rank_topics
from engagement_booster import generate_engagement_pack
from series_manager import (
    has_series_potential, detect_and_plan_series, start_series,
    get_active_series, get_series_topic_override, advance_series,
    enrich_script_with_series,
)
from ab_title_generator import pick_best_title


QUEUE_PATH = "scheduled_queue.json"
BATCH_DIR = "batch_output"


def load_queue() -> list:
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue: list) -> None:
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def _load_used() -> dict:
    path = "used_topics.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"used": [], "last_run": None}


def _save_used(data: dict) -> None:
    with open("used_topics.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def produce_batch(count: int = 7, dry_run: bool = False, language: str = "en") -> None:
    os.makedirs(BATCH_DIR, exist_ok=True)

    queue = load_queue()
    existing_dates = {item["scheduled_date"] for item in queue}

    # Mevcut kuyruktan sonraki tarihleri hesapla
    if queue:
        last_date = max(date.fromisoformat(d) for d in existing_dates)
        start_date = last_date + timedelta(days=1)
    else:
        start_date = date.today() + timedelta(days=1)

    print("=" * 52)
    print(f"📦 BATCH ÜRETİM — {count} video, {start_date}'den itibaren")
    print("=" * 52)

    produced = []
    batch_seen_ids: set = set()   # Batch boyunca klip tekrarını önler
    batch_used_topics: set = set()  # Batch içi konu tekrarını önler
    for i in range(count):
        slot_date = start_date + timedelta(days=i)
        video_dir = os.path.join(BATCH_DIR, str(slot_date))
        os.makedirs(video_dir, exist_ok=True)

        print(f"\n[{i+1}/{count}] Tarih: {slot_date}")

        try:
            # 1) Konu seç — seri sistemi devre dışı
            # extra_exclude: bu batch'te zaten kullanılan konuları tekrar seçme
            topic, used_data = pick_trending_topic(extra_exclude=batch_used_topics)
            batch_used_topics.add(topic)
            print(f"  Konu: {topic}")
            _save_used(used_data)

            # 2) Script üret — akıllı yeniden üretim ile
            script, score_bd = smart_generate(topic, language)
            print(f"  Script skor: {score_bd.total}/100")

            # 2d) A/B başlık optimizasyonu
            try:
                pick_best_title(script)
            except Exception as e:
                print(f"  ⚠️ A/B başlık hatası: {e}", file=sys.stderr)

            script_path = os.path.join(video_dir, "script.json")
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script, f, indent=2, ensure_ascii=False)
            print(f"  Script: {script['title']}")

            if dry_run:
                produced.append({
                    "scheduled_date": str(slot_date),
                    "topic": topic,
                    "title": script["title"],
                    "script_path": script_path,
                    "video_path": None,
                    "audio_path": None,
                    "thumbnail_path": None,
                    "published": False,
                    "dry_run": True,
                })
                continue

            # 3) TTS
            audio_path, vtt_path = generate_audio(
                script["narration"],
                output_dir=video_dir,
                voice=script.get("tts_voice"),
            )

            # 4) Video
            video_path = build_video(
                script, audio_path, vtt_path,
                output_path=os.path.join(video_dir, "short.mp4"),
                seen_ids=batch_seen_ids,
            )

            # 5) Thumbnail
            thumb_path = generate_thumbnail(
                script["title"],
                script["thumbnail_text"],
                output_path=os.path.join(video_dir, "thumbnail.png"),
            )

            # 6) Etkileşim paketi üret (upload sırasında kullanılacak)
            engagement = None
            try:
                engagement = generate_engagement_pack(script)
            except Exception as e:
                print(f"  ⚠️ Etkileşim paketi hatası: {e}", file=sys.stderr)

            # 6b) Seri sistemi devre dışı

            produced.append({
                "scheduled_date": str(slot_date),
                "topic": topic,
                "title": script["title"],
                "script_path": script_path,
                "video_path": video_path,
                "audio_path": audio_path,
                "thumbnail_path": thumb_path,
                "language": language,
                "published": False,
                "engagement_pack": engagement,
                "score": score_bd.total,
            })

            print(f"  ✅ Video hazır: {video_path} (skor: {score_bd.total}/100)")

        except Exception as e:
            print(f"  ❌ Hata: {e}", file=sys.stderr)
            produced.append({
                "scheduled_date": str(slot_date),
                "topic": topic if "topic" in dir() else "?",
                "title": "?",
                "script_path": None,
                "video_path": None,
                "published": False,
                "error": str(e),
            })

        # Kısa bekleme (API rate limit)
        if i < count - 1:
            time.sleep(2)

    # Kuyruğa ekle
    queue.extend(produced)
    save_queue(queue)

    success = sum(1 for p in produced if not p.get("error"))

    # used_topics.json'u git'e commit et (batch sonrası kalıcı dedup)
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "add", "used_topics.json"], check=True)
        diff_result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_result.returncode != 0:  # Staged değişiklik varsa commit et
            subprocess.run(
                ["git", "commit", "-m", f"chore: batch sonrası used_topics güncelle ({success}/{count} video)"],
                check=True,
            )
            print("  ✅ used_topics.json git'e commit edildi")
        else:
            print("  ℹ️ used_topics.json değişmedi, commit atlandı")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️ Git commit başarısız (devam ediliyor): {e}", file=sys.stderr)
    print(f"\n{'='*52}")
    print(f"✅ Batch tamamlandı: {success}/{count} video üretildi")
    print(f"   Kuyruk: {QUEUE_PATH}")
    print(f"{'='*52}")

    # Telegram bildirimi
    _send(
        f"📦 *Batch Üretim Tamamlandı*\n\n"
        f"✅ {success}/{count} video hazır\n"
        f"📅 {start_date} → {start_date + timedelta(days=count-1)}\n\n"
        + "\n".join(
            f"{'✅' if not p.get('error') else '❌'} {p['scheduled_date']}: {p.get('title','?')}"
            for p in produced
        )
    )


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WAR SHORTS — Batch Producer")
    parser.add_argument("--count", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--language", default=os.environ.get("LANGUAGE", "en"))
    parser.add_argument("--next", action="store_true", help="Kuyruktan sonraki öğeyi göster")
    args = parser.parse_args()

    if args.next:
        item = get_next_queued()
        if item:
            print(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            print("Kuyrukta bekleyen video yok.")
    else:
        produce_batch(args.count, args.dry_run, args.language)
