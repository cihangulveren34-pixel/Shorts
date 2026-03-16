"""
video_builder.py — Pexels + Pixabay'dan footage indirir, MoviePy ile 1080×1920 Short üretir.
Özellikler:
  - Çift kaynaklı klip (Pexels + Pixabay)
  - Style Profile sistemi (her video benzersiz görünüm)
  - 6 yönlü Ken Burns efekti
  - 8 renk tonu preset'i (mood-aware)
  - 4 farklı geçiş tipi
  - Film grain + vignette overlay
  - VTT tabanlı kesin zamanlı altyazı
  - Hook overlay, CTA ekranı, progress bar, watermark
  - Mood-based müzik seçimi
"""

import os
import json
import random
import requests
import tempfile
import shutil
import subprocess
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ uyumluluğu
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    ColorClip,
    concatenate_videoclips,
)
from moviepy.video.VideoClip import VideoClip

TARGET_W = 1080
TARGET_H = 1920
PEXELS_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
DVIDS_API = "https://api.dvidshub.net/search"
ARCHIVE_API = "https://archive.org/advancedsearch.php"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
LOGO_PATH = "assets/logo.png"
INTRO_PATH = "assets/intro.mp4"
OUTRO_PATH = "assets/outro.mp4"
CROSSFADE_DUR = 0.4
CTA_DURATION = 3.0

# Ses efekti dosyaları
SFX = {
    "hook":   "assets/sfx/drum_hit.wav",
    "twist":  "assets/sfx/sword_clash.wav",
    "payoff": "assets/sfx/explosion.wav",
    "cta":    "assets/sfx/trumpet.wav",
}

# Müzik havuzu: (dosya, mood anahtar kelimeleri)
MUSIC_POOL = [
    ("assets/music/epic_01_strength_of_titans.mp3", ["epic", "battle", "war", "empire", "army"]),
    ("assets/music/epic_02_ice_giants.mp3", ["epic", "cold", "north", "viking", "fall"]),
    ("assets/music/epic_03_gothamlicious.mp3", ["epic", "dark", "power", "conquer", "reign"]),
    ("assets/music/dark_04_burn_the_world.mp3", ["destroy", "nuclear", "bomb", "apocalypse", "invasion"]),
    ("assets/music/action_05_adventures.mp3", ["adventure", "explore", "discover", "hero", "victory"]),
    ("assets/music/dark_06_southern_gothic.mp3", ["dark", "mystery", "secret", "conspiracy", "betrayal"]),
    ("assets/music/suspense_07_stay_the_course.mp3", ["suspense", "tension", "crisis", "standoff", "cold war"]),
    ("assets/music/dark_08_tyrant.mp3", ["tyrant", "dictator", "regime", "oppression", "revolution"]),
    ("assets/music/action_09_big_drumming.mp3", ["action", "military", "march", "troops", "combat"]),
    ("assets/music/action_10_new_hero.mp3", ["hero", "rise", "triumph", "victory", "liberation"]),
    ("assets/music/action_11_trouble_tribals.mp3", ["tribal", "ancient", "primitive", "clash", "territory"]),
    ("assets/music/dark_12_feral_angel.mp3", ["dark", "somber", "tragedy", "loss", "aftermath"]),
]
MUSIC_FALLBACK = "assets/music/epic_01_strength_of_titans.mp3"

# ─── 8 Renk Tonu Preset'i ────────────────────────────────────────────────────

COLOR_GRADES = {
    "war_blue": {
        "desaturate": 0.30, "contrast": 1.15,
        "r_shift": -5, "g_shift": 0, "b_shift": +8,
    },
    "vintage_sepia": {
        "desaturate": 0.20, "contrast": 1.10,
        "r_shift": +15, "g_shift": +5, "b_shift": -10,
    },
    "cold_winter": {
        "desaturate": 0.25, "contrast": 1.20,
        "r_shift": -10, "g_shift": +2, "b_shift": +15,
    },
    "high_contrast_bw": {
        "desaturate": 1.0, "contrast": 1.30,
        "r_shift": 0, "g_shift": 0, "b_shift": 0,
    },
    "faded_washed": {
        "desaturate": 0.15, "contrast": 0.85,
        "r_shift": +5, "g_shift": +5, "b_shift": +5,
    },
    "vivid_saturated": {
        "desaturate": -0.20, "contrast": 1.25,
        "r_shift": +3, "g_shift": +3, "b_shift": +3,
    },
    "neutral": {
        "desaturate": 0.0, "contrast": 1.0,
        "r_shift": 0, "g_shift": 0, "b_shift": 0,
    },
    "dark_cinematic": {
        "desaturate": 0.35, "contrast": 1.35,
        "r_shift": -8, "g_shift": -8, "b_shift": -5,
    },
}

# Mood → uygun renk tonları eşleşmesi
MOOD_COLOR_MAP = {
    "dark":       ["dark_cinematic", "high_contrast_bw", "war_blue"],
    "epic":       ["vivid_saturated", "war_blue", "vintage_sepia"],
    "cold":       ["cold_winter", "war_blue", "faded_washed"],
    "mysterious": ["dark_cinematic", "faded_washed", "vintage_sepia"],
    "inspiring":  ["vivid_saturated", "vintage_sepia", "neutral"],
    "neutral":    list(COLOR_GRADES.keys()),
}

# Ken Burns efekt tipleri
KB_EFFECTS = ["zoom_in", "zoom_out", "pan_right", "pan_left", "pan_down", "diagonal_ur"]

# Geçiş tipleri
TRANSITION_TYPES = ["crossfade", "fade_black", "hard_cut", "slide"]


# ─── Style Profile ───────────────────────────────────────────────────────────

@dataclass
class StyleProfile:
    """Her video için benzersiz görsel stil konfigürasyonu."""
    color_grade: str
    transition_type: str
    ken_burns_pool: list
    vignette_intensity: float
    film_grain_intensity: float


# Stop words — title'dan keyword çıkarırken filtrele
_STOP_WORDS = {"what", "if", "the", "a", "an", "is", "was", "were", "had", "have", "has",
               "did", "do", "does", "not", "never", "ever", "in", "on", "at", "to", "for",
               "of", "and", "or", "but", "vs", "how", "why", "who", "that", "this", "it",
               "be", "been", "being", "are", "am", "with", "from", "by", "about", "into",
               "ya", "olmasaydı", "eğer", "ve", "bir", "bu", "neden", "nasıl"}


def _extract_title_keywords(title: str) -> list[str]:
    """Title'dan arama için anlamlı keyword'ler çıkarır."""
    import re
    words = re.findall(r"[a-zA-ZğüşöçıİĞÜŞÖÇ]{3,}", title.lower())
    meaningful = [w for w in words if w not in _STOP_WORDS]
    # İlk 4 anlamlı kelimeyi döndür
    return meaningful[:4]


def _infer_mood(script: dict) -> str:
    """Script içeriğinden mood çıkarır."""
    text = (script.get("title", "") + " " + script.get("narration", "")).lower()
    keywords = " ".join(kw.lower() for kw in script.get("search_keywords", []))
    combined = text + " " + keywords

    dark_words = ["destroy", "fall", "death", "tragedy", "loss", "defeat",
                  "apocalypse", "massacre", "collapse", "extinction", "nuclear"]
    if any(w in combined for w in dark_words):
        return "dark"

    epic_words = ["empire", "conquer", "victory", "rise", "triumph", "glory",
                  "legendary", "hero", "revolution", "power"]
    if any(w in combined for w in epic_words):
        return "epic"

    cold_words = ["winter", "north", "ice", "frozen", "arctic", "snow", "cold war"]
    if any(w in combined for w in cold_words):
        return "cold"

    return "neutral"


def _generate_style_profile(script: dict) -> StyleProfile:
    """Video için rastgele ama mood-aware stil profili üretir."""
    # Script'ten gelen mood alanını kullan, yoksa text'ten çıkar
    mood = script.get("mood") if script.get("mood") in MOOD_COLOR_MAP else _infer_mood(script)

    # Renk tonu: %70 mood'a uygun, %30 tamamen rastgele
    if random.random() < 0.7:
        color_grade = random.choice(MOOD_COLOR_MAP[mood])
    else:
        color_grade = random.choice(list(COLOR_GRADES.keys()))

    # Geçiş: tamamen rastgele
    transition_type = random.choice(TRANSITION_TYPES)

    # Ken Burns: 6 efektten 3-4'ü seçilir
    ken_burns_pool = random.sample(KB_EFFECTS, random.randint(3, 4))

    # Overlay yoğunlukları
    vignette_intensity = random.choice([0.0, 0.0, 0.2, 0.3, 0.4])
    film_grain_intensity = random.choice([0.0, 0.0, 0.0, 0.15, 0.25])

    profile = StyleProfile(
        color_grade=color_grade,
        transition_type=transition_type,
        ken_burns_pool=ken_burns_pool,
        vignette_intensity=vignette_intensity,
        film_grain_intensity=film_grain_intensity,
    )

    print(f"[video_builder] Style Profile:")
    print(f"  Mood: {mood} | Color: {color_grade} | Transition: {transition_type}")
    print(f"  KB Pool: {ken_burns_pool}")
    print(f"  Vignette: {vignette_intensity:.1f} | Grain: {film_grain_intensity:.2f}")

    return profile


# ─── Müzik seçimi ────────────────────────────────────────────────────────────

def _pick_music(script: dict) -> str:
    """Script içeriğine göre en uygun arka plan müziğini seçer."""
    text = (script.get("title", "") + " " + script.get("narration", "")).lower()
    keywords = [kw.lower() for kw in script.get("search_keywords", [])]

    scores = []
    for path, mood_words in MUSIC_POOL:
        if not os.path.exists(path):
            continue
        score = sum(1 for mw in mood_words if mw in text or mw in " ".join(keywords))
        scores.append((path, score))

    if not scores:
        return MUSIC_FALLBACK

    max_score = max(s for _, s in scores)
    if max_score > 0:
        best = [p for p, s in scores if s == max_score]
        pick = random.choice(best)
    else:
        pick = random.choice([p for p, _ in scores])

    print(f"[video_builder] Müzik seçildi: {os.path.basename(pick)}")
    return pick


# ─── Font yardımcısı ─────────────────────────────────────────────────────────

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        FONT_PATH,
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ─── Klip indirme ────────────────────────────────────────────────────────────

def _download_clip(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    for chunk in r.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name


def _best_pexels_url(video: dict) -> str:
    for q in ("hd", "sd"):
        for vf in video.get("video_files", []):
            if vf.get("quality") == q:
                return vf["link"]
    return video["video_files"][0]["link"]


def _fetch_pexels_clips(keywords: list, api_key: str, n: int, seen_ids: set) -> list:
    """Pexels'ten n adet benzersiz klip indirir."""
    headers = {"Authorization": api_key}
    downloaded = []

    queries = []
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]))
    if len(keywords) >= 3:
        queries.append(" ".join(keywords[1:3]))
    for kw in keywords:
        queries.append(kw)

    suffixes = ["cinematic", "dramatic", "aerial", "dark", "historical", "ancient"]
    for kw in keywords[:3]:
        queries.append(f"{kw} {random.choice(suffixes)}")

    # Konuya bağlı tematik fallback'ler
    topic_fallbacks = []
    kw_lower = " ".join(k.lower() for k in keywords)
    if any(w in kw_lower for w in ["turkey", "turkish", "bayraktar", "kaan", "akinci"]):
        topic_fallbacks = ["military drone flying", "fighter jet cockpit", "turkish flag waving", "military parade formation"]
    elif any(w in kw_lower for w in ["iran", "iranian", "tehran", "hormuz"]):
        topic_fallbacks = ["missile launch trail", "military parade missiles", "oil tanker ocean", "desert military base"]
    elif any(w in kw_lower for w in ["russia", "russian", "moscow", "kremlin"]):
        topic_fallbacks = ["russian military parade", "submarine underwater", "hypersonic missile launch", "arctic military base"]
    elif any(w in kw_lower for w in ["china", "chinese", "beijing", "taiwan"]):
        topic_fallbacks = ["aircraft carrier ocean", "military ships formation", "fighter jet formation flying", "chinese military parade"]
    elif any(w in kw_lower for w in ["israel", "israeli", "mossad", "iron dome"]):
        topic_fallbacks = ["missile interception night sky", "military technology screen", "fighter jet desert", "soldiers tactical formation"]
    elif any(w in kw_lower for w in ["america", "us ", "pentagon", "nato"]):
        topic_fallbacks = ["aircraft carrier aerial ocean", "stealth bomber flying", "navy fleet formation", "military base aerial"]
    elif any(w in kw_lower for w in ["uae", "emirates", "qatar", "saudi", "gulf"]):
        topic_fallbacks = ["modern city desert aerial", "fighter jet desert flying", "military vehicles desert", "luxury city skyline night"]
    elif any(w in kw_lower for w in ["drone", "swarm", "autonomous", "ai warfare"]):
        topic_fallbacks = ["military drone closeup", "drone swarm sky", "technology circuit board", "robot military futuristic"]
    elif any(w in kw_lower for w in ["nuclear", "nuke", "missile", "hypersonic", "icbm"]):
        topic_fallbacks = ["nuclear explosion dramatic", "missile launch smoke trail", "rocket launch cinematic", "mushroom cloud dramatic"]
    elif any(w in kw_lower for w in ["cyber", "hack", "internet", "satellite", "space"]):
        topic_fallbacks = ["server room technology", "satellite earth orbit", "space station earth", "digital code screen green"]
    elif any(w in kw_lower for w in ["submarine", "navy", "carrier", "ship", "fleet"]):
        topic_fallbacks = ["submarine underwater dramatic", "aircraft carrier ocean aerial", "warship ocean dramatic", "navy fleet formation"]

    # Genel fallback (son çare — askeri/modern)
    general_fallbacks = [
        "military dramatic cinematic", "fighter jet flying dramatic",
        "explosion smoke dramatic", "soldiers tactical night vision",
    ]
    random.shuffle(topic_fallbacks)
    random.shuffle(general_fallbacks)
    queries.extend(topic_fallbacks)
    queries.extend(general_fallbacks)

    for query in queries:
        if len(downloaded) >= n:
            break
        page = random.randint(1, 4)
        params = {"query": query, "per_page": 10, "page": page, "size": "medium"}
        try:
            resp = requests.get(PEXELS_API, headers=headers, params=params, timeout=20)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            random.shuffle(videos)
            for v in videos:
                if len(downloaded) >= n:
                    break
                vid = f"pexels_{v.get('id')}"
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                url = _best_pexels_url(v)
                print(f"[video_builder] Pexels klip {len(downloaded)+1}/{n} (id:{vid})...")
                downloaded.append(_download_clip(url))
        except Exception as e:
            print(f"[video_builder] Pexels hata ({query}): {e}")

    return downloaded


def _fetch_pixabay_clips(keywords: list, api_key: str, n: int, seen_ids: set) -> list:
    """Pixabay'dan n adet benzersiz klip indirir."""
    downloaded = []

    queries = []
    if len(keywords) >= 2:
        queries.append("+".join(keywords[:2]))
    for kw in keywords[:3]:
        queries.append(kw)

    # Konuya bağlı Pixabay fallback'ler
    kw_lower = " ".join(k.lower() for k in keywords)
    pixabay_topic = []
    if any(w in kw_lower for w in ["drone", "bayraktar", "turkey", "uav"]):
        pixabay_topic = ["drone+flying", "military+drone", "technology+aircraft"]
    elif any(w in kw_lower for w in ["missile", "nuclear", "hypersonic", "rocket"]):
        pixabay_topic = ["rocket+launch", "missile+military", "explosion+fire"]
    elif any(w in kw_lower for w in ["navy", "carrier", "submarine", "ship"]):
        pixabay_topic = ["warship+ocean", "submarine+underwater", "aircraft+carrier"]
    elif any(w in kw_lower for w in ["fighter", "stealth", "jet", "aircraft"]):
        pixabay_topic = ["fighter+jet", "airplane+military", "cockpit+pilot"]
    elif any(w in kw_lower for w in ["cyber", "hack", "ai", "technology"]):
        pixabay_topic = ["technology+computer", "server+room", "digital+code"]
    elif any(w in kw_lower for w in ["soldier", "army", "military", "war"]):
        pixabay_topic = ["soldiers+military", "army+tanks", "military+training"]

    pixabay_general = [
        "military+dramatic", "fighter+jet", "explosion+dramatic",
        "technology+futuristic", "soldiers+formation",
    ]
    random.shuffle(pixabay_topic)
    random.shuffle(pixabay_general)
    queries.extend(pixabay_topic)
    queries.extend(pixabay_general)

    for query in queries:
        if len(downloaded) >= n:
            break
        params = {
            "key": api_key, "q": query,
            "per_page": 10, "page": random.randint(1, 3),
            "video_type": "all",
        }
        try:
            resp = requests.get(PIXABAY_VIDEO_API, params=params, timeout=20)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            random.shuffle(hits)
            for hit in hits:
                if len(downloaded) >= n:
                    break
                vid = f"pixabay_{hit.get('id')}"
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                videos = hit.get("videos", {})
                url = None
                for quality in ("large", "medium", "small"):
                    v_data = videos.get(quality, {})
                    if v_data.get("url"):
                        url = v_data["url"]
                        break
                if not url:
                    continue
                print(f"[video_builder] Pixabay klip {len(downloaded)+1}/{n} (id:{vid})...")
                downloaded.append(_download_clip(url))
        except Exception as e:
            print(f"[video_builder] Pixabay hata ({query}): {e}")

    return downloaded


def _fetch_pexels_photos(keywords: list, api_key: str, n: int = 3) -> list:
    """Pexels'ten fotoğraf indirir."""
    headers = {"Authorization": api_key}
    downloaded = []

    queries = []
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]))
    for kw in keywords[:3]:
        queries.append(kw)

    # Askeri/sinematik suffix'ler
    for kw in keywords[:2]:
        queries.append(f"{kw} military")
        queries.append(f"{kw} dramatic")

    for query in queries:
        if len(downloaded) >= n:
            break
        params = {"query": query, "per_page": 5, "page": random.randint(1, 3), "size": "large"}
        try:
            resp = requests.get(PEXELS_PHOTO_API, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            random.shuffle(photos)
            for photo in photos:
                if len(downloaded) >= n:
                    break
                # En iyi çözünürlüğü al
                url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
                if not url:
                    continue
                try:
                    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    r = requests.get(url, timeout=30)
                    r.raise_for_status()
                    tmp.write(r.content)
                    tmp.close()
                    downloaded.append(tmp.name)
                    print(f"[video_builder] Pexels fotoğraf {len(downloaded)}/{n}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[video_builder] Pexels foto hata ({query}): {e}")

    return downloaded


def _fetch_wikimedia_photos(keywords: list, limit: int = 3) -> list:
    """Wikimedia Commons'tan fotoğraf indirir (askeri keyword'ler için öncelikli)."""
    downloaded = []

    queries = []
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]) + " military")
    for kw in keywords[:3]:
        queries.append(kw)

    for query in queries:
        if len(downloaded) >= limit:
            break
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,  # File namespace
            "gsrsearch": query,
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 1920,
        }
        try:
            headers = {"User-Agent": "WarShorts/1.0 (video asset downloader)"}
            resp = requests.get(WIKIMEDIA_API, params=params, timeout=15, headers=headers)
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                if len(downloaded) >= limit:
                    break
                imageinfo = page.get("imageinfo", [{}])[0]
                url = imageinfo.get("thumburl") or imageinfo.get("url")
                if not url:
                    continue
                # Sadece resim dosyaları
                if not any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    continue
                try:
                    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    r = requests.get(url, timeout=30)
                    r.raise_for_status()
                    tmp.write(r.content)
                    tmp.close()
                    downloaded.append(tmp.name)
                    print(f"[video_builder] Wikimedia foto {len(downloaded)}/{limit}")
                except Exception:
                    pass
        except Exception as e:
            print(f"[video_builder] Wikimedia hata ({query}): {e}")

    return downloaded


def _photo_to_video(photo_path: str, duration: float, kb_effect: str = "zoom_in",
                    intensity: float = 0.05) -> VideoFileClip:
    """Fotoğrafı Ken Burns efektli video klibine çevirir."""
    img = Image.open(photo_path).convert("RGB")

    # 1080x1920 oranına crop + resize
    target_ratio = TARGET_W / TARGET_H
    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    # Biraz büyüt (Ken Burns için margin)
    scale = 1 + intensity + 0.02
    base_w = int(TARGET_W * scale)
    base_h = int(TARGET_H * scale)
    img = img.resize((base_w, base_h), Image.LANCZOS)
    base_arr = np.array(img)

    def make_frame(t):
        progress = t / max(duration, 0.01)

        if kb_effect == "zoom_in":
            s = 1 + intensity * progress
        elif kb_effect == "zoom_out":
            s = 1 + intensity * (1 - progress)
        elif kb_effect == "pan_right":
            s = 1.0
        elif kb_effect == "pan_left":
            s = 1.0
        else:
            s = 1 + intensity * progress * 0.5

        bh, bw = base_arr.shape[:2]
        crop_w, crop_h = TARGET_W, TARGET_H

        if kb_effect == "pan_right":
            max_x = bw - crop_w
            x = int(max_x * progress)
            y = (bh - crop_h) // 2
        elif kb_effect == "pan_left":
            max_x = bw - crop_w
            x = int(max_x * (1 - progress))
            y = (bh - crop_h) // 2
        elif kb_effect == "pan_down":
            x = (bw - crop_w) // 2
            max_y = bh - crop_h
            y = int(max_y * progress)
        else:
            # Zoom — merkeze crop
            cur_w = int(crop_w / s) if s > 0 else crop_w
            cur_h = int(crop_h / s) if s > 0 else crop_h
            cur_w = min(cur_w, bw)
            cur_h = min(cur_h, bh)

            resized = Image.fromarray(base_arr).resize(
                (int(bw * s), int(bh * s)), Image.LANCZOS
            )
            rw, rh = resized.size
            x = (rw - crop_w) // 2
            y = (rh - crop_h) // 2
            x = max(0, min(x, rw - crop_w))
            y = max(0, min(y, rh - crop_h))
            return np.array(resized.crop((x, y, x + crop_w, y + crop_h)))

        x = max(0, min(x, bw - crop_w))
        y = max(0, min(y, bh - crop_h))
        return base_arr[y:y + crop_h, x:x + crop_w]

    clip = VideoClip(make_frame, duration=duration)
    clip = clip.set_fps(30)
    return clip


def _fetch_dvids_clips(keywords: list, api_key: str, n: int, seen_ids: set) -> list:
    """DVIDS'ten (ABD Savunma Bakanlığı) gerçek askeri video indirir. Public Domain."""
    if not shutil.which("ffmpeg"):
        print("[video_builder] ffmpeg bulunamadı, DVIDS atlanıyor.")
        return []

    downloaded = []
    queries = []
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]))
    for kw in keywords[:4]:
        queries.append(kw)

    # Askeri fallback sorguları
    military_fallbacks = [
        "military exercise", "fighter jet", "aircraft carrier",
        "special operations", "drone strike", "naval operations",
    ]
    random.shuffle(military_fallbacks)
    queries.extend(military_fallbacks[:3])

    for query in queries:
        if len(downloaded) >= n:
            break
        params = {
            "q": query,
            "max_results": 10,
            "api_key": api_key,
        }
        try:
            resp = requests.get(DVIDS_API, params=params, timeout=20)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            random.shuffle(results)
            for asset in results:
                if len(downloaded) >= n:
                    break
                # Sadece video
                if asset.get("type") != "video":
                    continue
                vid = f"dvids_{asset.get('id')}"
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                hls_url = asset.get("hls_url")
                if not hls_url:
                    continue
                # HLS → MP4 (ffmpeg subprocess)
                try:
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix="dvids_")
                    tmp.close()
                    cmd = [
                        "ffmpeg", "-y", "-i", hls_url,
                        "-c", "copy", "-t", "30",  # max 30 saniye
                        "-loglevel", "error",
                        tmp.name,
                    ]
                    result = subprocess.run(cmd, timeout=60, capture_output=True)
                    if result.returncode == 0 and os.path.getsize(tmp.name) > 10000:
                        downloaded.append(tmp.name)
                        print(f"[video_builder] DVIDS klip {len(downloaded)}/{n} (id:{vid})")
                    else:
                        os.unlink(tmp.name)
                except (subprocess.TimeoutExpired, Exception) as e:
                    print(f"[video_builder] DVIDS indirme hatası: {e}")
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
        except Exception as e:
            print(f"[video_builder] DVIDS arama hatası ({query}): {e}")

    return downloaded


def _fetch_archive_clips(keywords: list, n: int, seen_ids: set) -> list:
    """Internet Archive'dan Public Domain askeri video indirir. API key gereksiz."""
    downloaded = []
    queries = []
    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:2]))
    for kw in keywords[:3]:
        queries.append(kw)

    # Koleksiyon bazlı fallback'ler
    archive_fallbacks = [
        "military aircraft", "world war", "nuclear test",
        "navy ships", "military training", "cold war",
    ]
    random.shuffle(archive_fallbacks)
    queries.extend(archive_fallbacks[:2])

    headers = {"User-Agent": "WarShorts/1.0 (video asset downloader)"}

    for query in queries:
        if len(downloaded) >= n:
            break
        search_q = f"({query}) AND mediatype:movies AND collection:(usgovfilms OR military)"
        params = {
            "q": search_q,
            "output": "json",
            "rows": 10,
            "page": 1,
            "sort[]": "downloads desc",
            "fl[]": "identifier,title",
        }
        try:
            resp = requests.get(ARCHIVE_API, params=params, timeout=20, headers=headers)
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                if len(downloaded) >= n:
                    break
                identifier = doc.get("identifier")
                if not identifier:
                    continue
                vid = f"archive_{identifier}"
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                # Metadata'dan mp4 dosyası bul
                try:
                    meta_url = f"https://archive.org/metadata/{identifier}"
                    meta_resp = requests.get(meta_url, timeout=15, headers=headers)
                    meta_resp.raise_for_status()
                    files = meta_resp.json().get("files", [])
                    # mp4 dosyası ara (boyut < 50MB)
                    mp4_file = None
                    for f in files:
                        name = f.get("name", "")
                        size = int(f.get("size", 0) or 0)
                        fmt = f.get("format", "").lower()
                        if (name.lower().endswith(".mp4") or "mpeg4" in fmt or "mp4" in fmt) \
                                and 0 < size < 50 * 1024 * 1024:
                            mp4_file = name
                            break
                    if not mp4_file:
                        continue
                    # İndir
                    dl_url = f"https://archive.org/download/{identifier}/{mp4_file}"
                    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix="archive_")
                    r = requests.get(dl_url, stream=True, timeout=60, headers=headers)
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    tmp.close()
                    if os.path.getsize(tmp.name) > 10000:
                        downloaded.append(tmp.name)
                        print(f"[video_builder] Archive klip {len(downloaded)}/{n}: {identifier}")
                    else:
                        os.unlink(tmp.name)
                except Exception as e:
                    print(f"[video_builder] Archive indirme hatası ({identifier}): {e}")
        except Exception as e:
            print(f"[video_builder] Archive arama hatası ({query}): {e}")

    return downloaded


def _fetch_clips(keywords: list, n: int = 8) -> list:
    """
    DVIDS + Archive + Pexels + Pixabay'dan klip + fotoğraf indirip karıştırır.
    %60 video + %40 fotoğraf pattern: V, V, F, V, F, V, V, F
    Returns: [("video", path), ("photo", path), ...] tuple listesi.
    """
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    dvids_key = os.environ.get("DVIDS_API_KEY")

    if not pexels_key:
        raise RuntimeError("PEXELS_API_KEY eksik")

    seen_ids = set()

    # Video klipleri (%60)
    n_videos = max(1, int(n * 0.6))
    n_photos = n - n_videos

    video_paths = []

    # ─── 1) DVIDS — gerçek askeri footage (Public Domain) ────────────
    n_dvids = 2 if dvids_key else 0
    if dvids_key:
        try:
            dvids_clips = _fetch_dvids_clips(keywords, dvids_key, n_dvids, seen_ids)
            video_paths.extend(dvids_clips)
            print(f"[video_builder] DVIDS: {len(dvids_clips)} klip")
        except Exception as e:
            print(f"[video_builder] DVIDS hatası: {e}")

    # ─── 2) Internet Archive — tarihi askeri footage (Public Domain) ──
    n_archive = 2 if not dvids_key else 1
    try:
        archive_clips = _fetch_archive_clips(keywords, n_archive, seen_ids)
        video_paths.extend(archive_clips)
        print(f"[video_builder] Archive: {len(archive_clips)} klip")
    except Exception as e:
        print(f"[video_builder] Archive hatası: {e}")

    # ─── 3) Pexels + Pixabay — stock footage (kalan) ─────────────────
    n_stock = max(0, n_videos - len(video_paths))
    if n_stock > 0:
        if pixabay_key:
            n_pex = n_stock // 2
            n_pix = n_stock - n_pex
            print(f"[video_builder] {n_pex} Pexels + {n_pix} Pixabay stock video...")
            pexels_clips = _fetch_pexels_clips(keywords, pexels_key, n_pex, seen_ids)
            pixabay_clips = _fetch_pixabay_clips(keywords, pixabay_key, n_pix, seen_ids)
            for i in range(max(len(pexels_clips), len(pixabay_clips))):
                if i < len(pexels_clips):
                    video_paths.append(pexels_clips[i])
                if i < len(pixabay_clips):
                    video_paths.append(pixabay_clips[i])
        else:
            print(f"[video_builder] {n_stock} Pexels stock video...")
            video_paths.extend(_fetch_pexels_clips(keywords, pexels_key, n_stock, seen_ids))

    # Yeterli video yoksa Pexels'ten tamamla
    if len(video_paths) < n_videos:
        extra = _fetch_pexels_clips(keywords, pexels_key, n_videos - len(video_paths), seen_ids)
        video_paths.extend(extra)

    # Fotoğraf indirme — Wikimedia öncelikli, Pexels yedek
    photo_paths = []
    if n_photos > 0:
        # Askeri keyword'ler için Wikimedia öncelikli
        kw_lower = " ".join(k.lower() for k in keywords)
        military_kw = ["military", "army", "navy", "air force", "weapon", "tank", "missile",
                       "drone", "fighter", "war", "soldier", "submarine", "aircraft"]
        is_military = any(w in kw_lower for w in military_kw)

        if is_military:
            wiki_photos = _fetch_wikimedia_photos(keywords, limit=n_photos)
            photo_paths.extend(wiki_photos)

        # Kalan fotoğrafları Pexels'ten al
        remaining = n_photos - len(photo_paths)
        if remaining > 0:
            pexels_photos = _fetch_pexels_photos(keywords, pexels_key, remaining)
            photo_paths.extend(pexels_photos)

    if not video_paths and not photo_paths:
        raise RuntimeError("Hiç klip veya fotoğraf indirilemedi.")

    # Pattern: V, V, F, V, F, V, V, F (yaklaşık)
    mixed = []
    vi, pi = 0, 0
    pattern = ["video", "video", "photo", "video", "photo", "video", "video", "photo"]
    for slot in pattern[:n]:
        if slot == "video" and vi < len(video_paths):
            mixed.append(("video", video_paths[vi]))
            vi += 1
        elif slot == "photo" and pi < len(photo_paths):
            mixed.append(("photo", photo_paths[pi]))
            pi += 1
        elif vi < len(video_paths):
            mixed.append(("video", video_paths[vi]))
            vi += 1
        elif pi < len(photo_paths):
            mixed.append(("photo", photo_paths[pi]))
            pi += 1

    # Kalan medyaları ekle
    while vi < len(video_paths) and len(mixed) < n:
        mixed.append(("video", video_paths[vi]))
        vi += 1
    while pi < len(photo_paths) and len(mixed) < n:
        mixed.append(("photo", photo_paths[pi]))
        pi += 1

    if not mixed:
        raise RuntimeError("Hiç medya birleştirilemedi.")

    print(f"[video_builder] Toplam: {sum(1 for t,_ in mixed if t=='video')} video + "
          f"{sum(1 for t,_ in mixed if t=='photo')} fotoğraf")
    return mixed[:n]


# ─── Resize / crop ───────────────────────────────────────────────────────────

def _resize_to_shorts(clip: VideoFileClip) -> VideoFileClip:
    w, h = clip.size
    target_ratio = TARGET_W / TARGET_H
    current_ratio = w / h
    if current_ratio > target_ratio:
        clip = clip.resize(height=TARGET_H)
        clip = clip.crop(x_center=clip.w // 2, width=TARGET_W, height=TARGET_H)
    else:
        clip = clip.resize(width=TARGET_W)
        clip = clip.crop(y_center=clip.h // 2, width=TARGET_W, height=TARGET_H)
    return clip


# ─── Ken Burns — 6 yön ───────────────────────────────────────────────────────

def _apply_ken_burns(clip: VideoFileClip, effect_type: str = "zoom_in",
                     intensity: float = 0.03) -> VideoFileClip:
    """6 farklı Ken Burns hareketi uygular."""
    dur = clip.duration

    if effect_type == "zoom_in":
        def transform(get_frame, t):
            frame = get_frame(t)
            scale = 1 + intensity * (t / max(dur, 0.01))
            h, w = frame.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            img = Image.fromarray(frame).resize((nw, nh), Image.LANCZOS)
            x, y = (nw - w) // 2, (nh - h) // 2
            return np.array(img.crop((x, y, x + w, y + h)))

    elif effect_type == "zoom_out":
        def transform(get_frame, t):
            frame = get_frame(t)
            scale = 1 + intensity * (1 - t / max(dur, 0.01))
            h, w = frame.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            img = Image.fromarray(frame).resize((nw, nh), Image.LANCZOS)
            x, y = (nw - w) // 2, (nh - h) // 2
            return np.array(img.crop((x, y, x + w, y + h)))

    elif effect_type == "pan_right":
        def transform(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            nw = int(w * (1 + intensity))
            img = Image.fromarray(frame).resize((nw, h), Image.LANCZOS)
            progress = t / max(dur, 0.01)
            x = int((nw - w) * progress)
            return np.array(img.crop((x, 0, x + w, h)))

    elif effect_type == "pan_left":
        def transform(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            nw = int(w * (1 + intensity))
            img = Image.fromarray(frame).resize((nw, h), Image.LANCZOS)
            progress = 1 - (t / max(dur, 0.01))
            x = int((nw - w) * progress)
            return np.array(img.crop((x, 0, x + w, h)))

    elif effect_type == "pan_down":
        def transform(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            nh = int(h * (1 + intensity))
            img = Image.fromarray(frame).resize((w, nh), Image.LANCZOS)
            progress = t / max(dur, 0.01)
            y = int((nh - h) * progress)
            return np.array(img.crop((0, y, w, y + h)))

    elif effect_type == "diagonal_ur":
        def transform(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            nw, nh = int(w * (1 + intensity)), int(h * (1 + intensity))
            img = Image.fromarray(frame).resize((nw, nh), Image.LANCZOS)
            progress = t / max(dur, 0.01)
            x = int((nw - w) * progress)
            y = int((nh - h) * (1 - progress))
            return np.array(img.crop((x, y, x + w, y + h)))

    else:
        return clip

    return clip.fl(transform, apply_to="video")


# ─── Renk tonu — parametrik ──────────────────────────────────────────────────

def _color_grade(clip: VideoFileClip, preset: str = "war_blue") -> VideoFileClip:
    """COLOR_GRADES'den preset uygular."""
    params = COLOR_GRADES.get(preset, COLOR_GRADES["war_blue"])

    def grade(frame):
        f = frame.astype(np.float32)
        grey = f.mean(axis=2, keepdims=True)
        desat = params["desaturate"]
        if desat >= 0:
            f = f * (1 - desat) + grey * desat
        else:
            f = f + (f - grey) * abs(desat)
        f = (f - 128) * params["contrast"] + 128
        f[:, :, 0] = f[:, :, 0] + params["r_shift"]
        f[:, :, 1] = f[:, :, 1] + params["g_shift"]
        f[:, :, 2] = f[:, :, 2] + params["b_shift"]
        return np.clip(f, 0, 255).astype(np.uint8)

    return clip.fl_image(grade)


# ─── Overlay efektleri ────────────────────────────────────────────────────────

def _add_vignette(clip: VideoFileClip, intensity: float) -> VideoFileClip:
    """Kenar karartma efekti (0.0-1.0)."""
    if intensity <= 0:
        return clip

    # Vignette maskesini bir kere hesapla
    h, w = TARGET_H, TARGET_W
    Y, X = np.ogrid[:h, :w]
    cy, cx = h // 2, w // 2
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    mask = 1.0 - (dist / max_dist) ** 2 * intensity * 0.7
    mask = np.clip(mask, 0, 1).astype(np.float32)

    def apply_vig(frame):
        h_f, w_f = frame.shape[:2]
        if h_f != h or w_f != w:
            return frame
        return np.clip(frame.astype(np.float32) * mask[:, :, np.newaxis],
                       0, 255).astype(np.uint8)

    return clip.fl_image(apply_vig)


def _add_film_grain(clip: VideoFileClip, intensity: float) -> VideoFileClip:
    """Film grain noise overlay (0.0-1.0)."""
    if intensity <= 0:
        return clip

    noise_level = 255 * intensity * 0.05

    def apply_grain(frame):
        noise = np.random.normal(0, noise_level, frame.shape)
        return np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    return clip.fl_image(apply_grain)


# ─── Çoklu klip montajı + geçişler ───────────────────────────────────────────

def _build_background(clip_paths: list, total_duration: float,
                      style: StyleProfile) -> VideoFileClip:
    """
    Klipleri style profile'a göre işler ve birleştirir.
    clip_paths: [("video", path), ("photo", path), ...] veya [path, ...] (geriye uyumlu)
    """
    processed = []
    per_clip = total_duration / len(clip_paths)

    for i, item in enumerate(clip_paths):
        # Geriye uyumluluk: tuple veya string
        if isinstance(item, tuple):
            media_type, path = item
        else:
            media_type, path = "video", item

        kb = style.ken_burns_pool[i % len(style.ken_burns_pool)]

        if media_type == "photo":
            try:
                c = _photo_to_video(path, per_clip, kb_effect=kb)
                c = _color_grade(c, style.color_grade)
            except Exception as e:
                print(f"[video_builder] Fotoğraf işleme hatası, atlaniyor: {e}")
                continue
        else:
            c = VideoFileClip(path, audio=False)
            c = _resize_to_shorts(c)
            c = _color_grade(c, style.color_grade)
            c = _apply_ken_burns(c, kb)

            # Süre ayarı
            if c.duration < per_clip:
                repeats = int(per_clip / c.duration) + 1
                c = concatenate_videoclips([c] * repeats)
            c = c.subclip(0, per_clip)

        # Overlay efektleri
        if style.vignette_intensity > 0:
            c = _add_vignette(c, style.vignette_intensity)
        if style.film_grain_intensity > 0:
            c = _add_film_grain(c, style.film_grain_intensity)

        processed.append(c)

    if len(processed) == 1:
        return processed[0]

    # Geçiş uygulama
    tt = style.transition_type

    if tt == "hard_cut":
        bg = concatenate_videoclips(processed, method="compose")
    elif tt == "fade_black":
        clips = []
        for i, c in enumerate(processed):
            if i > 0:
                c = c.fadein(CROSSFADE_DUR)
            if i < len(processed) - 1:
                c = c.fadeout(CROSSFADE_DUR)
            clips.append(c)
        bg = concatenate_videoclips(clips, method="compose")
    elif tt == "slide":
        clips = [processed[0].crossfadeout(CROSSFADE_DUR * 0.5)]
        for i, c in enumerate(processed[1:], 1):
            c = c.crossfadein(CROSSFADE_DUR * 0.5)
            if i < len(processed) - 1:
                c = c.crossfadeout(CROSSFADE_DUR * 0.5)
            clips.append(c)
        bg = concatenate_videoclips(clips, method="compose",
                                    padding=-CROSSFADE_DUR * 0.5)
    else:  # crossfade (varsayılan)
        clips = [processed[0].crossfadeout(CROSSFADE_DUR)]
        for i, c in enumerate(processed[1:], 1):
            c = c.crossfadein(CROSSFADE_DUR)
            if i < len(processed) - 1:
                c = c.crossfadeout(CROSSFADE_DUR)
            clips.append(c)
        bg = concatenate_videoclips(clips, method="compose",
                                    padding=-CROSSFADE_DUR)

    # Tam uzunluğa getir
    if bg.duration < total_duration:
        bg = concatenate_videoclips([bg, bg]).subclip(0, total_duration)
    else:
        bg = bg.subclip(0, total_duration)

    return bg


# ─── Altyazı ─────────────────────────────────────────────────────────────────

def _render_subtitle_image(text: str) -> np.ndarray:
    font = _load_font(46)
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0] + 40
    text_h = bbox[3] - bbox[1] + 24

    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (text_w, text_h)], fill=(0, 0, 0, 160))
    for dx, dy in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
        draw.text((20 + dx, 12 + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((20, 12), text, font=font, fill=(255, 255, 255, 255))
    return np.array(img)


def _make_subtitle_clips(chunks: list, total_duration: float) -> list:
    clips = []
    for chunk in chunks:
        start = chunk["start"]
        end = min(chunk["end"], total_duration - CTA_DURATION - 0.1)
        dur = end - start
        if dur <= 0:
            continue
        img_arr = _render_subtitle_image(chunk["text"])
        h, w = img_arr.shape[:2]
        clips.append(
            ImageClip(img_arr, ismask=False)
            .set_duration(dur)
            .set_start(start)
            .set_position(((TARGET_W - w) // 2, TARGET_H - h - 320))
        )
    return clips


def _make_fallback_subtitle_clips(narration: str, audio_duration: float) -> list:
    words = narration.split()
    secs_per_word = audio_duration / max(len(words), 1)
    n = 5
    chunks = []
    for i in range(0, len(words), n):
        group = words[i:i + n]
        chunks.append({
            "start": i * secs_per_word,
            "end": min((i + n) * secs_per_word, audio_duration),
            "text": " ".join(group),
        })
    return _make_subtitle_clips(chunks, audio_duration)


# ─── Hook overlay ────────────────────────────────────────────────────────────

def _make_hook_clip(hook_text: str, duration: float = 3.0) -> ImageClip:
    font = _load_font(64)
    max_w = TARGET_W - 80
    words = hook_text.split()
    lines, current = [], []
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)

    for word in words:
        test = " ".join(current + [word])
        if dd.textbbox((0, 0), test, font=font)[2] > max_w and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    line_h = 76
    h = line_h * len(lines) + 30
    img = Image.new("RGBA", (TARGET_W, h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (TARGET_W, h + 20)], fill=(0, 0, 0, 180))

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (TARGET_W - lw) // 2
        y = 15 + i * line_h
        for dx, dy in [(-3, -3), (3, 3), (-3, 3), (3, -3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 220, 0, 255))

    return (
        ImageClip(np.array(img))
        .set_duration(duration)
        .set_start(0)
        .set_position(("center", 160))
        .crossfadeout(0.5)
    )


# ─── CTA bitiş ekranı ────────────────────────────────────────────────────────

def _make_cta_clip(total_duration: float, duration: float = CTA_DURATION) -> list:
    start = total_duration - duration

    bg = (
        ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0))
        .set_opacity(0.75)
        .set_duration(duration)
        .set_start(start)
        .crossfadein(0.4)
    )

    bar = (
        ColorClip(size=(TARGET_W, 8), color=(200, 30, 30))
        .set_duration(duration)
        .set_start(start)
        .set_position(("center", TARGET_H // 2 - 100))
    )

    font_big = _load_font(80)
    font_sub = _load_font(44)

    def _text_img(text, font, color, outline=(0, 0, 0)):
        dummy = Image.new("RGBA", (1, 1))
        dd = ImageDraw.Draw(dummy)
        bbox = dd.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0] + 20
        h = bbox[3] - bbox[1] + 20
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for dx, dy in [(-3, -3), (3, 3), (-3, 3), (3, -3), (0, -3), (0, 3), (-3, 0), (3, 0)]:
            draw.text((10 + dx, 10 + dy), text, font=font, fill=(*outline, 255))
        draw.text((10, 10), text, font=font, fill=(*color, 255))
        return np.array(img)

    follow_arr = _text_img("FOLLOW", font_big, (255, 220, 0))
    fh, fw = follow_arr.shape[:2]
    follow_clip = (
        ImageClip(follow_arr).set_duration(duration).set_start(start)
        .set_position(((TARGET_W - fw) // 2, TARGET_H // 2 - 80))
        .crossfadein(0.4)
    )

    sub_arr = _text_img("FOR MORE WHAT-IFS!", font_sub, (255, 255, 255))
    sh, sw = sub_arr.shape[:2]
    sub_clip = (
        ImageClip(sub_arr).set_duration(duration).set_start(start)
        .set_position(((TARGET_W - sw) // 2, TARGET_H // 2 + 20))
        .crossfadein(0.5)
    )

    arrow_arr = _text_img("TAP FOLLOW  ^", font_sub, (200, 30, 30))
    ah, aw = arrow_arr.shape[:2]
    arrow_clip = (
        ImageClip(arrow_arr).set_duration(duration).set_start(start)
        .set_position(((TARGET_W - aw) // 2, TARGET_H // 2 + 90))
        .crossfadein(0.6)
    )

    return [bg, bar, follow_clip, sub_clip, arrow_clip]


# ─── Progress bar ────────────────────────────────────────────────────────────

def _make_progress_bar(total_duration: float, bar_h: int = 8) -> VideoClip:
    def make_frame(t):
        w = int(TARGET_W * min(t / total_duration, 1.0))
        frame = np.zeros((bar_h, TARGET_W, 3), dtype=np.uint8)
        if w > 0:
            frame[:, :w] = [200, 30, 30]
        return frame

    return (
        VideoClip(make_frame, duration=total_duration)
        .set_position(("center", TARGET_H - bar_h - 2))
    )


# ─── Logo / watermark ────────────────────────────────────────────────────────

def _make_watermark_clip(total_duration: float) -> ImageClip | None:
    if not os.path.exists(LOGO_PATH):
        return None

    logo = Image.open(LOGO_PATH).convert("RGBA")
    max_size = 120
    w, h = logo.size
    if w > max_size:
        ratio = max_size / w
        logo = logo.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    r, g, b, a = logo.split()
    a = a.point(lambda x: int(x * 0.6))
    logo.putalpha(a)

    arr = np.array(logo)
    lh, lw = arr.shape[:2]
    x = TARGET_W - lw - 24
    y = 24

    return (
        ImageClip(arr).set_duration(total_duration).set_start(0)
        .set_position((x, y))
    )


# ─── Ses efektleri ───────────────────────────────────────────────────────────

def _build_sfx_audio(audio_duration: float) -> list:
    timings = {
        "hook":   0.1,
        "twist":  15.0,
        "payoff": 40.0,
        "cta":    max(0, audio_duration - 0.5),
    }
    sfx_clips = []
    for key, t in timings.items():
        path = SFX.get(key, "")
        if not path or not os.path.exists(path):
            continue
        try:
            sfx = AudioFileClip(path).volumex(0.35).set_start(t)
            if t + sfx.duration > audio_duration + CTA_DURATION:
                sfx = sfx.subclip(0, audio_duration + CTA_DURATION - t)
            sfx_clips.append(sfx)
            print(f"[video_builder] SFX eklendi: {key} @ {t:.1f}s")
        except Exception as e:
            print(f"[video_builder] SFX yüklenemedi ({key}): {e}")

    return sfx_clips


# ─── Ana fonksiyon ───────────────────────────────────────────────────────────

def build_video(
    script: dict,
    audio_path: str,
    vtt_path: str = None,
    output_path: str = "output/short.mp4",
) -> str:
    """Script, ses ve VTT'den 1080x1920 Short üretir."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Style profile (her video benzersiz görünüm)
    style = _generate_style_profile(script)

    # 1) Çoklu klip indir (Pexels + Pixabay)
    # search_keywords + title'dan ek keyword'ler çıkar
    keywords = list(script.get("search_keywords", []))
    title_words = _extract_title_keywords(script.get("title", ""))
    for tw in title_words:
        if tw not in " ".join(keywords).lower():
            keywords.append(tw)
    clip_paths = _fetch_clips(keywords, n=8)

    # 2) Ses süresi
    narration_audio = AudioFileClip(audio_path)
    total_duration = narration_audio.duration + CTA_DURATION + 0.3

    # 3) Arka plan: çoklu klip + efektler + geçişler
    bg = _build_background(clip_paths, total_duration, style)

    # 4) Overlay katmanları
    layers = [bg]

    # Hook (ilk 3 sn)
    layers.append(_make_hook_clip(script["hook"], duration=min(3.0, total_duration)))

    # Altyazılar
    vtt_chunks = []
    if vtt_path and os.path.exists(vtt_path):
        from tts import parse_vtt
        vtt_chunks = parse_vtt(vtt_path)
        layers.extend(_make_subtitle_clips(vtt_chunks, total_duration))
        print(f"[video_builder] VTT: {len(vtt_chunks)} altyazı chunk'ı")
    else:
        layers.extend(_make_fallback_subtitle_clips(script["narration"], narration_audio.duration))

    # ─── Overlay System Entegrasyonu ──────────────────────────────────
    try:
        from overlay_system import (
            extract_countries_with_timing,
            extract_statistics_with_timing,
            create_map_overlay,
            create_stat_card,
            download_flag,
            create_flag_overlay,
            create_format_overlays,
            create_red_flash_data,
            create_glitch_frame,
        )

        narration_text = script.get("narration", "")
        video_format = script.get("format", "classic_whatif")

        if vtt_chunks:
            # 1) Harita overlay'leri (max 3 ülke)
            try:
                countries = extract_countries_with_timing(narration_text, vtt_chunks)
                for entry in countries[:3]:
                    map_arr = create_map_overlay(entry["country"])
                    if map_arr is not None:
                        h, w = map_arr.shape[:2]
                        start = entry["start"]
                        dur = min(3.5, entry["end"] - entry["start"] + 1.5)
                        layers.append(
                            ImageClip(map_arr, ismask=False)
                            .set_duration(dur)
                            .set_start(start)
                            .set_position(("center", 200))
                            .crossfadein(0.3)
                            .crossfadeout(0.3)
                        )
                        print(f"[video_builder] Harita overlay: {entry['country']} @ {start:.1f}s")
            except Exception as e:
                print(f"[video_builder] Harita overlay hatası: {e}")

            # 2) İstatistik kartları (max 4 stat)
            try:
                stats = extract_statistics_with_timing(narration_text, vtt_chunks)
                for entry in stats[:4]:
                    card_arr = create_stat_card(entry["value"], entry["label"])
                    h, w = card_arr.shape[:2]
                    start = entry["start"]
                    dur = min(2.5, entry["end"] - entry["start"] + 1.0)
                    layers.append(
                        ImageClip(card_arr, ismask=False)
                        .set_duration(dur)
                        .set_start(start)
                        .set_position(((TARGET_W - w) // 2, 350))
                        .crossfadein(0.2)
                        .crossfadeout(0.2)
                    )
                    print(f"[video_builder] Stat kart: {entry['value']} @ {start:.1f}s")
            except Exception as e:
                print(f"[video_builder] Stat kart hatası: {e}")

            # 3) Bayrak overlay'leri (max 3 ülke)
            try:
                countries_for_flags = extract_countries_with_timing(narration_text, vtt_chunks)
                for entry in countries_for_flags[:3]:
                    flag_path = download_flag(entry["country"])
                    if flag_path:
                        flag_arr = create_flag_overlay(flag_path)
                        if flag_arr is not None:
                            h, w = flag_arr.shape[:2]
                            start = entry["start"]
                            dur = min(3.0, entry["end"] - entry["start"] + 1.0)
                            layers.append(
                                ImageClip(flag_arr, ismask=False)
                                .set_duration(dur)
                                .set_start(start)
                                .set_position((TARGET_W - w - 30, TARGET_H - h - 350))
                                .crossfadein(0.2)
                                .crossfadeout(0.2)
                            )
                            print(f"[video_builder] Bayrak overlay: {entry['country']} @ {start:.1f}s")
            except Exception as e:
                print(f"[video_builder] Bayrak overlay hatası: {e}")

        # 4) Format bazlı overlay'ler
        try:
            title = script.get("title", "")
            format_overlays = create_format_overlays(video_format, total_duration, title)
            for ov in format_overlays:
                if ov["type"] == "glitch":
                    # Glitch efekti — geçiş anlarında frame bazlı uygulanır
                    # (bg klibine doğrudan uygulama yapılmaz, karmaşıklık nedeniyle atlat)
                    continue
                if ov["data"] is not None:
                    h, w = ov["data"].shape[:2]
                    dur = ov["end"] - ov["start"]
                    if dur <= 0:
                        continue
                    pos = ov["position"]
                    layers.append(
                        ImageClip(ov["data"], ismask=False)
                        .set_duration(dur)
                        .set_start(ov["start"])
                        .set_position(pos)
                        .crossfadein(0.2)
                        .crossfadeout(0.2)
                    )
            if format_overlays:
                print(f"[video_builder] Format overlay'ler ({video_format}): {len(format_overlays)} adet")
        except Exception as e:
            print(f"[video_builder] Format overlay hatası: {e}")

        # 5) Kırmızı alarm flash'ları (15sn twist + 40sn payoff)
        try:
            flash_times = [15.0, 40.0]
            flash_dur = 0.3
            for ft in flash_times:
                if ft + flash_dur > total_duration:
                    continue
                flash_arr = create_red_flash_data()
                layers.append(
                    ImageClip(flash_arr, ismask=False)
                    .set_duration(flash_dur)
                    .set_start(ft)
                    .set_position((0, 0))
                    .crossfadein(0.1)
                    .crossfadeout(0.15)
                )
            print(f"[video_builder] Kırmızı flash @ {[t for t in flash_times if t + flash_dur <= total_duration]}")
        except Exception as e:
            print(f"[video_builder] Kırmızı flash hatası: {e}")

    except ImportError:
        print("[video_builder] overlay_system.py bulunamadı, overlay'ler atlanıyor.")
    except Exception as e:
        print(f"[video_builder] Overlay system genel hatası: {e}")
    # ─── Overlay System Sonu ──────────────────────────────────────────

    # CTA bitiş ekranı
    layers.extend(_make_cta_clip(total_duration))

    # Logo/watermark
    wm = _make_watermark_clip(total_duration)
    if wm:
        layers.append(wm)

    # İlerleme çubuğu
    layers.append(_make_progress_bar(total_duration))

    # 5) Kompozit
    final_video = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    final_video = final_video.set_duration(total_duration)

    # 6) Ses: TTS + müzik + sfx
    audio_tracks = [narration_audio]
    music_path = _pick_music(script)
    if music_path and os.path.exists(music_path):
        music = AudioFileClip(music_path).volumex(0.135)
        if music.duration < total_duration:
            from moviepy.audio.fx.audio_loop import audio_loop
            music = audio_loop(music, nloops=int(total_duration / music.duration) + 1)
        music = music.subclip(0, total_duration)
        audio_tracks.append(music)

    sfx_clips = _build_sfx_audio(narration_audio.duration)
    audio_tracks.extend(sfx_clips)

    final_video = final_video.set_audio(CompositeAudioClip(audio_tracks))

    # 7) Branded intro / outro
    segments = []
    if os.path.exists(INTRO_PATH):
        try:
            intro = VideoFileClip(INTRO_PATH, audio=True)
            intro = _resize_to_shorts(intro)
            segments.append(intro.crossfadeout(0.3))
        except Exception as e:
            print(f"[video_builder] Intro yüklenemedi: {e}")

    final_video_faded = final_video.crossfadein(0.3) if segments else final_video
    segments.append(final_video_faded)

    if os.path.exists(OUTRO_PATH):
        try:
            outro = VideoFileClip(OUTRO_PATH, audio=True)
            outro = _resize_to_shorts(outro)
            segments.append(outro.crossfadein(0.3))
        except Exception as e:
            print(f"[video_builder] Outro yüklenemedi: {e}")

    if len(segments) > 1:
        final_video = concatenate_videoclips(segments, method="compose", padding=-0.3)

    # 8) Export
    print(f"[video_builder] Render ediliyor -> {output_path}")
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=os.path.join(os.path.dirname(output_path), "temp_audio.m4a"),
        remove_temp=True,
        threads=2,
        preset="fast",
        verbose=False,
        logger=None,
    )

    # Cleanup
    narration_audio.close()
    for item in clip_paths:
        path = item[1] if isinstance(item, tuple) else item
        try:
            os.unlink(path)
        except OSError:
            pass

    print(f"[video_builder] Video hazır: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys

    script_path = sys.argv[1] if len(sys.argv) > 1 else "output/script.json"
    audio_path = sys.argv[2] if len(sys.argv) > 2 else "output/narration.mp3"
    vtt_path = sys.argv[3] if len(sys.argv) > 3 else "output/narration.vtt"

    with open(script_path, encoding="utf-8") as f:
        script = json.load(f)

    build_video(script, audio_path, vtt_path if os.path.exists(vtt_path) else None)
