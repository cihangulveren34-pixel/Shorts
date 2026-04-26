"""
binaural_main.py — Binaural Beats + Math Geometry Shorts pipeline orkestratoru.

Kullanim:
  python binaural_main.py                  # Normal calistirma
  python binaural_main.py --dry-run        # Upload olmadan test
  python binaural_main.py --topic 0        # Belirli topic index ile calistir

Pipeline:
  1) binaural_topic_pool.json'dan konu sec
  2) Gemini ile title/hook/tags uret (binaural_script_gen)
  3) Binaural beat sesi uret (freq_audio_gen reuse)
  4) Manim ile matematik animasyonu uret (binaural_anim_gen)
  5) Video montaji: animasyon + overlay (binaural_video_builder)
  6) YouTube'a yukle (uploader.py reuse)
  7) Telegram bildirimi gonder (notifier.py reuse)
"""

import argparse
import json
import os
import random
import sys
import traceback

from binaural_script_gen import generate_binaural_script, save_binaural_script
from freq_script_gen import generate_localizations
from freq_audio_gen import generate_frequency_audio
from binaural_anim_gen import generate_math_animation
from binaural_video_builder import build_binaural_video
from notifier import send_notification, send_error_notification

OUTPUT_DIR = "output"
TOPIC_POOL_PATH = "binaural_topic_pool.json"
USED_TOPICS_PATH = "binaural_used_topics.json"
AUDIO_PATH = os.path.join(OUTPUT_DIR, "binaural_audio.mp3")
ANIM_PATH = os.path.join(OUTPUT_DIR, "binaural_anim.mp4")
VIDEO_PATH = os.path.join(OUTPUT_DIR, "binaural_short.mp4")
SCRIPT_PATH = os.path.join(OUTPUT_DIR, "binaural_script.json")

DURATION_SEC = 30  # Shorts suresi


# ─── Konu secimi & durum ──────────────────────────────────────────────────────

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


def _topic_key(topic: dict) -> str:
    """Benzersiz topic anahtari."""
    return f"{topic['math_type']}_{topic['beat_hz']}_{topic['beat_band']}"


def pick_topic(index_override: int = None) -> dict:
    """
    Konu secer. index_override verilmisse o index'i doner.
    Aksi halde kullanilmamis konulardan rastgele secer.
    Tumu kullanildiysa listeyi sifirlar.
    """
    pool = _load_pool()

    if index_override is not None:
        if 0 <= index_override < len(pool):
            return pool[index_override]
        raise ValueError(f"Index {index_override} gecersiz (0-{len(pool)-1} araliginda olmali).")

    used = _load_used()
    used_set = set(used)

    available = [t for t in pool if _topic_key(t) not in used_set]
    if not available:
        print("[binaural_main] Tum konular kullanildi — liste sifirlaniyor.")
        used = []
        _save_used(used)
        available = pool

    topic = random.choice(available)
    used.append(_topic_key(topic))
    _save_used(used)
    return topic


import requests

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
BG_VIDEO_PATH = os.path.join(OUTPUT_DIR, "binaural_bg.mp4")

# ─── Pexels Yardimcisi ───────────────────────────────────────────────────────

def _download_pexels_bg(mood: str) -> str:
    """Konunun mood'una uygun stok video indirir."""
    if not PEXELS_API_KEY:
        print("[binaural_main] PEXELS_API_KEY bulunamadi — stok video atlandi.")
        return None

    queries = {
        "sleep": ["dark space", "deep ocean", "starry night", "slow clouds"],
        "meditation": ["zen garden", "ethereal particles", "soft light", "water ripples"],
        "energy": ["abstract energy", "fire", "lava", "digital neural network"],
        "spiritual": ["nebula", "galaxy", "incense smoke", "aurora borealis"],
        "clarity": ["mountain peak", "clear sky", "geometric crystal", "clean water"],
        "cosmic": ["deep space", "supernova", "black hole", "galaxy zoom"],
        "calm": ["forest sunlight", "slow waves", "floating dust", "calm rain"],
    }
    
    q_list = queries.get(mood, ["abstract dark background", "ambient texture"])
    query = random.choice(q_list)
    
    print(f"[binaural_main] Pexels'tan '{query}' videosu araniyor...")
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait&size=medium"
    headers = {"Authorization": PEXELS_API_KEY}
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if not data.get("videos"):
            print(f"[binaural_main] '{query}' icin video bulunamadi.")
            return None
            
        video = random.choice(data["videos"])
        # En uygun MP4 linkini bul
        files = [f for f in video["video_files"] if f["file_type"] == "video/mp4"]
        if not files: return None
        
        # 1080x1920'ye en yakin olani sec
        target_file = min(files, key=lambda f: abs(f.get("width", 0) - 1080))
        download_url = target_file["link"]
        
        print(f"[binaural_main] Stok video indiriliyor: {download_url}")
        v_resp = requests.get(download_url, timeout=30)
        with open(BG_VIDEO_PATH, "wb") as f:
            f.write(v_resp.content)
            
        return BG_VIDEO_PATH
    except Exception as e:
        print(f"[binaural_main] Pexels hatasi: {e}")
        return None


# ─── Adim calistiricisi ──────────────────────────────────────────────────────

def _step(name: str, fn, topic_name: str = ""):
    try:
        return fn()
    except Exception as e:
        print(f"\n[binaural_main] HATA — {name}: {e}", file=sys.stderr)
        traceback.print_exc()
        try:
            send_error_notification(name, e, topic_name)
        except Exception:
            pass
        raise


# ─── Pipeline ────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, topic_index: int = None) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Onceki ciktilari temizle
    for p in [AUDIO_PATH, ANIM_PATH, VIDEO_PATH, SCRIPT_PATH]:
        if os.path.exists(p):
            os.remove(p)

    print("=" * 56)
    print("🔮  BINAURAL GEOMETRY SHORTS — Pipeline Baslatildi")
    print("=" * 56)

    # 1) Konu sec
    topic = pick_topic(topic_index)
    topic_name = topic["title_name"]
    print(f"\n[binaural_main] Secilen konu: {topic_name}")
    print(f"   Math: {topic['math_type']} | Beat: {topic['beat_hz']} Hz {topic['beat_band']}")

    # 2) Script/metadata uret (Gemini)
    print("\n[binaural_main] Metadata uretiliyor...")
    script = _step(
        "Script uretimi",
        lambda: generate_binaural_script(topic),
        topic_name,
    )
    save_binaural_script(script, SCRIPT_PATH)
    print(f"[binaural_main] Baslik: {script['title']}")

    # 2.5) Coklu dil cevirileri
    print("\n[binaural_main] Coklu dil cevirileri uretiliyor...")
    localizations = _step(
        "Localization cevirisi",
        lambda: generate_localizations(script),
        topic_name,
    )
    if not localizations:
        raise RuntimeError("Localization uretilemedi — video yayinlanmayacak.")

    # 3) Binaural beat sesi uret (freq_audio_gen reuse)
    print(f"\n[binaural_main] {topic['carrier_hz']} Hz carrier + {topic['beat_hz']} Hz binaural ses uretiliyor...")
    audio_path = _step(
        "Ses uretimi",
        lambda: generate_frequency_audio(
            hz=float(topic["carrier_hz"]),
            output_mp3=AUDIO_PATH,
            duration_sec=DURATION_SEC,
            binaural_offset=float(topic["beat_hz"]),
        ),
        topic_name,
    )

    # 4) Manim matematik animasyonu uret
    print(f"\n[binaural_main] {topic['math_type']} animasyonu uretiliyor ({DURATION_SEC}s)...")
    anim_path = _step(
        "Animasyon uretimi",
        lambda: generate_math_animation(
            math_type=topic["math_type"],
            duration_sec=DURATION_SEC,
            output_path=ANIM_PATH,
            mood=topic["mood"],
        ),
        topic_name,
    )

    # 4.5) Arka plan stok videosu indir (Cinematic Upgrade)
    print(f"\n[binaural_main] Mood ({topic['mood']}) icin stok video araniyor...")
    bg_path = _step(
        "Stok video indirme",
        lambda: _download_pexels_bg(topic["mood"]),
        topic_name,
    )

    # 5) Video montaji
    print("\n[binaural_main] Video montaji yapiliyor...")
    video_path = _step(
        "Video montaji",
        lambda: build_binaural_video(
            script=script,
            audio_path=audio_path,
            anim_path=anim_path,
            output_path=VIDEO_PATH,
            bg_video_path=bg_path
        ),
        topic_name,
    )

    if dry_run:
        if localizations:
            script["localizations"] = localizations
            save_binaural_script(script, SCRIPT_PATH)

        print("\n" + "=" * 56)
        print("✅  DRY RUN TAMAMLANDI (upload atlandi)")
        print(f"   Script    → {SCRIPT_PATH}")
        print(f"   Ses       → {audio_path}")
        print(f"   Animasyon → {anim_path}")
        print(f"   Video     → {video_path}")
        print("=" * 56)
        return

    # 6) YouTube'a yukle
    print("\n[binaural_main] YouTube'a yukleniyor...")
    from uploader import upload_video

    base_tags = ["Sacred Geometry", "Binaural Beats", "Meditation Music",
                 "Math Animation", "Sleep Music", "Focus Music", "Shorts"]
    upload_tags = list(dict.fromkeys(script["tags"] + base_tags))

    description = script.get("description", f"{script['title']}\n\n#BinauralBeats #SacredGeometry")

    video_id = _step(
        "YouTube upload",
        lambda: upload_video(
            video_path=video_path,
            title=script["title"],
            description=description,
            tags=upload_tags,
            thumbnail_path=None,
            localizations=localizations,
            category_id="27",  # Education
        ),
        topic_name,
    )

    print(f"\n[binaural_main] Video yuklendi: https://youtube.com/shorts/{video_id}")

    # 7) Telegram bildirimi
    print("\n[binaural_main] Bildirim gonderiliyor...")
    try:
        send_notification(
            title=script["title"],
            video_id=video_id,
            duration_sec=DURATION_SEC,
            tags=script["tags"],
        )
    except Exception as e:
        print(f"[binaural_main] Telegram bildirimi gonderilemedi (kritik degil): {e}")

    print("\n" + "=" * 56)
    print(f"✅  TAMAMLANDI! (BINAURAL GEOMETRY SHORTS)")
    print(f"   https://youtube.com/shorts/{video_id}")
    print("=" * 56)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Binaural Geometry Shorts Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Upload olmadan test et")
    parser.add_argument("--topic", type=int, default=None, help="Belirli bir topic index (0-based)")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, topic_index=args.topic)
    except Exception as e:
        print(f"\n❌ Pipeline basarisiz: {e}", file=sys.stderr)
        sys.exit(1)
