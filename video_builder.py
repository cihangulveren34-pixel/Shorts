"""
video_builder.py — YouTube CC + DVIDS + Archive'dan footage indirir, MoviePy ile 1080×1920 Short üretir.
Özellikler:
  - YouTube Creative Commons lisanslı gerçek askeri videolar (yt-dlp)
  - DVIDS + Internet Archive fallback
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
DVIDS_API = "https://api.dvidshub.net/search"
ARCHIVE_API = "https://archive.org/advancedsearch.php"
YT_COOKIES_PATH = os.environ.get("YT_COOKIES_PATH", "yt_cookies.txt")

# ─── Invidious instances (YouTube proxy) ──────────────────────────────────────
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://invidious.fdn.fr",
    "https://inv.tux.pizza",
    "https://invidious.privacyredirect.com",
    "https://invidious.protokolla.fi",
]

# ─── YouTube CC Askeri Keyword Havuzu ────────────────────────────────────────

YT_MILITARY_KEYWORDS = {
    "training": [
        "military training footage", "army training exercise footage",
        "military drill footage", "combat training footage",
        "army boot camp footage", "military obstacle course footage",
        "live fire exercise footage", "infantry training footage",
        "paratrooper training footage", "military academy footage",
        "amphibious assault training footage", "urban warfare training footage",
        "night vision military training footage", "joint military exercise footage",
        "ranger training footage", "marine corps training footage",
    ],
    "jets": [
        "fighter jet takeoff footage", "fighter jet cockpit footage",
        "F-35 footage", "F-22 raptor footage", "Su-57 footage",
        "fighter jet dogfight footage", "air force scramble footage",
        "military jet formation footage", "stealth bomber footage",
        "B-2 bomber footage", "fighter jet landing footage",
        "supersonic jet footage", "jet afterburner footage",
        "eurofighter typhoon footage", "rafale fighter footage",
        "F-16 footage", "F-15 eagle footage", "MiG-29 footage",
    ],
    "helicopter": [
        "military helicopter takeoff footage", "attack helicopter firing footage",
        "Apache helicopter footage", "Black Hawk helicopter footage",
        "helicopter gunship footage", "military helicopter rescue footage",
        "CH-47 Chinook footage", "helicopter air assault footage",
        "Ka-52 helicopter footage", "military helicopter formation footage",
        "medevac helicopter footage", "helicopter fast rope footage",
    ],
    "tanks": [
        "tank firing footage", "tank live fire exercise footage",
        "M1 Abrams tank footage", "Leopard 2 tank footage",
        "tank battle footage", "armored vehicle footage",
        "tank convoy footage", "T-90 tank footage",
        "tank urban combat footage", "Challenger 2 tank footage",
        "Merkava tank footage", "tank night firing footage",
        "armored personnel carrier footage", "tank column footage",
    ],
    "drone": [
        "military drone footage", "drone surveillance footage",
        "Bayraktar TB2 footage", "drone strike footage",
        "UAV military footage", "predator drone footage",
        "reaper drone footage", "combat drone footage",
        "drone swarm military footage", "reconnaissance drone footage",
        "military quadcopter footage", "kamikaze drone footage",
        "drone warfare footage", "tactical drone footage",
    ],
    "navy": [
        "navy exercise footage", "aircraft carrier operations footage",
        "warship footage", "destroyer ship footage",
        "submarine footage", "naval fleet footage",
        "navy SEAL footage", "amphibious landing footage",
        "aircraft carrier takeoff footage", "battleship footage",
        "frigate naval footage", "naval bombardment footage",
        "submarine surfacing footage", "carrier strike group footage",
        "navy fleet formation footage", "cruiser warship footage",
    ],
    "special_forces": [
        "special forces training footage", "navy seals training footage",
        "special operations footage", "delta force footage",
        "SAS training footage", "commando raid footage",
        "special forces night raid footage", "counter terrorism footage",
        "hostage rescue footage", "special forces parachute footage",
        "green beret footage", "spetsnaz training footage",
        "special forces CQB footage", "SWAT tactical footage",
    ],
    "missiles": [
        "missile launch footage", "ICBM launch footage",
        "cruise missile footage", "anti ship missile footage",
        "patriot missile footage", "S-400 missile footage",
        "hypersonic missile footage", "ballistic missile footage",
        "missile defense system footage", "THAAD missile footage",
        "iron dome interception footage", "tomahawk cruise missile footage",
        "nuclear missile test footage", "air defense missile footage",
    ],
    "explosions": [
        "military explosion footage", "bomb explosion footage",
        "airstrike footage", "demolition military footage",
        "artillery firing footage", "howitzer firing footage",
        "carpet bombing footage", "precision strike footage",
        "bunker buster footage", "controlled demolition military footage",
        "mortar firing footage", "rocket artillery footage",
    ],
    "misc": [
        "military parade footage", "soldiers marching footage",
        "military ceremony footage", "troops deployment footage",
        "military logistics footage", "military base footage",
        "war memorial footage", "veterans ceremony footage",
        "military equipment footage", "defense industry footage",
        "military convoy footage", "armed forces footage",
        "military flag ceremony footage", "soldiers patrol footage",
        "military camp footage", "army barracks footage",
    ],
}
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


def _pick_yt_category(keywords: list) -> str:
    """Script keyword'lerine göre en uygun YT keyword kategorisini seçer."""
    kw_lower = " ".join(k.lower() for k in keywords)

    category_hints = {
        "jets": ["jet", "fighter", "f-35", "f-22", "f-16", "stealth", "bomber", "aircraft", "air force", "kaan", "su-57", "rafale"],
        "helicopter": ["helicopter", "apache", "black hawk", "chinook", "heli", "ka-52"],
        "tanks": ["tank", "abrams", "leopard", "armored", "t-90", "merkava", "challenger"],
        "drone": ["drone", "uav", "bayraktar", "tb2", "reaper", "predator", "akinci", "swarm"],
        "navy": ["navy", "carrier", "submarine", "ship", "destroyer", "fleet", "frigate", "cruiser", "naval"],
        "special_forces": ["special forces", "seal", "delta", "sas", "commando", "spetsnaz", "green beret"],
        "missiles": ["missile", "icbm", "hypersonic", "patriot", "s-400", "iron dome", "thaad", "nuclear", "nuke", "rocket"],
        "explosions": ["explosion", "bomb", "airstrike", "artillery", "howitzer", "demolition", "mortar"],
        "training": ["training", "exercise", "drill", "boot camp"],
    }

    for cat, hints in category_hints.items():
        if any(h in kw_lower for h in hints):
            return cat

    return random.choice(list(YT_MILITARY_KEYWORDS.keys()))


def _download_via_invidious(video_id: str, out_path: str) -> bool:
    """Invidious proxy üzerinden YouTube videosu indir."""
    instances = list(INVIDIOUS_INSTANCES)
    random.shuffle(instances)
    for base in instances:
        try:
            # Video bilgisi al
            api_url = f"{base}/api/v1/videos/{video_id}"
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            # En iyi mp4 formatı bul (720p+)
            stream_url = None
            for fmt in data.get("formatStreams", []) + data.get("adaptiveFormats", []):
                if fmt.get("container") == "mp4" and fmt.get("type", "").startswith("video/"):
                    quality = fmt.get("qualityLabel", "")
                    if any(q in quality for q in ["720p", "1080p", "480p"]):
                        stream_url = fmt.get("url")
                        break
            if not stream_url:
                # Herhangi bir mp4 stream al
                for fmt in data.get("formatStreams", []):
                    if fmt.get("container") == "mp4":
                        stream_url = fmt.get("url")
                        break
            if not stream_url:
                continue
            # İndir
            vid_resp = requests.get(stream_url, timeout=60, stream=True)
            if vid_resp.status_code != 200:
                continue
            with open(out_path, "wb") as f:
                for chunk in vid_resp.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
            if os.path.getsize(out_path) > 10000:
                return True
        except Exception:
            continue
    return False


def _search_invidious(query: str, max_results: int = 5) -> list[dict]:
    """Invidious API ile YouTube'da arama yap. [{videoId, title, lengthSeconds}, ...]"""
    instances = list(INVIDIOUS_INSTANCES)
    random.shuffle(instances)
    for base in instances:
        try:
            params = {"q": query, "type": "video", "sort_by": "relevance"}
            resp = requests.get(f"{base}/api/v1/search", params=params, timeout=15)
            if resp.status_code != 200:
                continue
            results = []
            for item in resp.json()[:max_results]:
                if item.get("type") == "video":
                    results.append({
                        "videoId": item["videoId"],
                        "title": item.get("title", ""),
                        "lengthSeconds": item.get("lengthSeconds", 0),
                    })
            if results:
                return results
        except Exception:
            continue
    return []


def _download_via_cobalt(video_id: str, out_path: str) -> bool:
    """cobalt.tools API ile YouTube videosu indir."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        resp = requests.post(
            "https://api.cobalt.tools/",
            json={"url": url, "videoQuality": "720"},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return False
        data = resp.json()
        download_url = data.get("url")
        if not download_url:
            return False
        vid_resp = requests.get(download_url, timeout=60, stream=True)
        if vid_resp.status_code != 200:
            return False
        with open(out_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
        return os.path.getsize(out_path) > 10000
    except Exception:
        return False


def _download_via_pytubefix(video_id: str, out_path: str) -> bool:
    """pytubefix kütüphanesi ile YouTube videosu indir."""
    try:
        from pytubefix import YouTube as PYT
        yt = PYT(f"https://www.youtube.com/watch?v={video_id}")
        stream = (yt.streams.filter(progressive=True, file_extension="mp4")
                  .order_by("resolution").desc().first())
        if not stream:
            stream = yt.streams.filter(file_extension="mp4").order_by("resolution").desc().first()
        if not stream:
            return False
        stream.download(filename=out_path)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 10000
    except Exception:
        return False


def _download_via_ytdlp(video_id: str, out_path: str) -> bool:
    """yt-dlp ile YouTube videosu indir (son çare)."""
    if not shutil.which("yt-dlp"):
        return False
    cmd = [
        "yt-dlp",
        f"https://www.youtube.com/watch?v={video_id}",
        "--format", "bestvideo[height>=720][ext=mp4]+bestaudio[ext=m4a]/best[height>=720][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--max-filesize", "100M",
        "--no-playlist", "--no-warnings", "--quiet", "--no-progress",
        "--geo-bypass",
        "-o", out_path,
    ]
    if os.path.exists(YT_COOKIES_PATH):
        cmd.extend(["--cookies", YT_COOKIES_PATH])
    try:
        result = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 10000
    except Exception:
        return False


def _download_youtube_video(video_id: str, out_path: str) -> bool:
    """YouTube videosu indir — fallback zinciri: Invidious → pytubefix → cobalt → yt-dlp"""
    methods = [
        ("Invidious", lambda: _download_via_invidious(video_id, out_path)),
        ("pytubefix", lambda: _download_via_pytubefix(video_id, out_path)),
        ("cobalt", lambda: _download_via_cobalt(video_id, out_path)),
        ("yt-dlp", lambda: _download_via_ytdlp(video_id, out_path)),
    ]
    for name, fn in methods:
        try:
            if fn():
                print(f"[video_builder] YouTube indirme OK ({name}): {video_id}")
                return True
        except Exception:
            pass
        # Başarısız olursa dosyayı temizle
        try:
            if os.path.exists(out_path):
                os.unlink(out_path)
        except OSError:
            pass
    return False


def _cut_segment(full_path: str, seen_ids: set, query: str, idx: int) -> str | None:
    """Tam videodan rastgele 5-10sn segment keser. Başarılı olursa segment path döner."""
    if not shutil.which("ffmpeg"):
        return full_path  # ffmpeg yoksa tam videoyu döndür

    # Video süresini al
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        full_path,
    ]
    try:
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
        video_duration = float(probe_result.stdout.strip())
    except Exception:
        video_duration = 30.0

    segment_dur = random.uniform(5.0, 10.0)
    if video_duration <= segment_dur + 1:
        segment_start = 0
        segment_dur = min(segment_dur, video_duration)
    else:
        max_start = max(0, video_duration - segment_dur - 1)
        segment_start = random.uniform(0, max_start)

    segment_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix="ytcc_seg_")
    segment_file.close()

    cut_cmd = [
        "ffmpeg", "-y",
        "-ss", str(segment_start),
        "-i", full_path,
        "-t", str(segment_dur),
        "-c", "copy",
        "-loglevel", "error",
        segment_file.name,
    ]
    try:
        cut_result = subprocess.run(cut_cmd, timeout=30, capture_output=True)
    except Exception:
        try:
            os.unlink(segment_file.name)
        except OSError:
            pass
        return None

    # Orijinal tam videoyu sil
    try:
        os.unlink(full_path)
    except OSError:
        pass

    if cut_result.returncode == 0 and os.path.exists(segment_file.name) and os.path.getsize(segment_file.name) > 5000:
        vid_id = f"ytcc_{hash(query)}_{idx}"
        if vid_id not in seen_ids:
            seen_ids.add(vid_id)
            return segment_file.name
    try:
        os.unlink(segment_file.name)
    except OSError:
        pass
    return None


def _fetch_youtube_cc_clips(keywords: list, n: int, seen_ids: set) -> list[str]:
    """YouTube'dan video indirir — Invidious arama + çoklu indirme yöntemi.
    Returns: list of file paths.
    """
    downloaded = []

    # Keyword havuzundan sorgu listesi oluştur
    category = _pick_yt_category(keywords)
    yt_pool = list(YT_MILITARY_KEYWORDS.get(category, []))
    random.shuffle(yt_pool)

    # Script keyword'lerinden de sorgu ekle
    script_queries = []
    for kw in keywords[:3]:
        script_queries.append(f"{kw} footage")
    if len(keywords) >= 2:
        script_queries.append(f"{keywords[0]} {keywords[1]} footage")

    # Karışık sorgu listesi: script keywords + havuz keywords
    all_queries = script_queries + yt_pool
    seen_queries = set()
    unique_queries = []
    for q in all_queries:
        ql = q.lower()
        if ql not in seen_queries:
            seen_queries.add(ql)
            unique_queries.append(q)

    for query in unique_queries:
        if len(downloaded) >= n:
            break

        try:
            print(f"[video_builder] YouTube aranıyor: '{query}'...")

            # Invidious ile arama yap
            results = _search_invidious(query, max_results=5)
            if not results:
                print(f"[video_builder] YouTube arama sonuç yok: '{query}'")
                continue

            # Bulunan videolardan birini indir
            for video in results:
                if len(downloaded) >= n:
                    break
                vid_id = video["videoId"]
                if vid_id in seen_ids:
                    continue

                # Geçici dosya
                tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix="ytcc_full_")
                tmp.close()

                if _download_youtube_video(vid_id, tmp.name):
                    segment = _cut_segment(tmp.name, seen_ids, query, len(downloaded))
                    if segment:
                        downloaded.append(segment)
                        print(f"[video_builder] YouTube klip {len(downloaded)}/{n}: "
                              f"'{video.get('title', vid_id)[:60]}'")
                        break
                else:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    print(f"[video_builder] YouTube indirilemedi: {vid_id}")

        except Exception as e:
            print(f"[video_builder] YouTube hata ({query}): {e}")

    return downloaded


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


def _fetch_clips(keywords: list, n: int = 10) -> list[str]:
    """
    YouTube CC + DVIDS + Archive'dan video klip indirir.
    Returns: list of file paths (sadece video, tuple yok).
    """
    dvids_key = os.environ.get("DVIDS_API_KEY")
    seen_ids = set()
    video_paths = []

    # ─── 1) YouTube CC — ana kaynak ──────────────────────────────────
    try:
        yt_clips = _fetch_youtube_cc_clips(keywords, n, seen_ids)
        video_paths.extend(yt_clips)
        print(f"[video_builder] YouTube CC: {len(yt_clips)} klip")
    except Exception as e:
        print(f"[video_builder] YouTube CC hatası: {e}")

    # ─── 2) DVIDS — ek klipler (Public Domain) ──────────────────────
    if len(video_paths) < n and dvids_key:
        n_dvids = min(2, n - len(video_paths))
        try:
            dvids_clips = _fetch_dvids_clips(keywords, dvids_key, n_dvids, seen_ids)
            video_paths.extend(dvids_clips)
            print(f"[video_builder] DVIDS: {len(dvids_clips)} klip")
        except Exception as e:
            print(f"[video_builder] DVIDS hatası: {e}")

    # ─── 3) Internet Archive — son çare fallback ─────────────────────
    if len(video_paths) < n:
        n_archive = n - len(video_paths)
        try:
            archive_clips = _fetch_archive_clips(keywords, n_archive, seen_ids)
            video_paths.extend(archive_clips)
            if archive_clips:
                print(f"[video_builder] Archive fallback: {len(archive_clips)} klip")
        except Exception as e:
            print(f"[video_builder] Archive hatası: {e}")

    if not video_paths:
        raise RuntimeError("Hiç video klip indirilemedi.")

    print(f"[video_builder] Toplam: {len(video_paths)} video klip")
    return video_paths[:n]


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
    Video klipleri style profile'a göre işler ve birleştirir.
    clip_paths: list[str] — video dosya yolları.
    """
    processed = []
    per_clip = total_duration / len(clip_paths)

    for i, path in enumerate(clip_paths):
        kb = style.ken_burns_pool[i % len(style.ken_burns_pool)]

        try:
            c = VideoFileClip(path, audio=False)
            c = _resize_to_shorts(c)
            c = _color_grade(c, style.color_grade)
            c = _apply_ken_burns(c, kb)

            # Süre ayarı
            if c.duration < per_clip:
                repeats = int(per_clip / c.duration) + 1
                c = concatenate_videoclips([c] * repeats)
            c = c.subclip(0, per_clip)
        except Exception as e:
            print(f"[video_builder] Klip işleme hatası, atlanıyor: {e}")
            continue

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

    # 1) Çoklu klip indir (YouTube CC + DVIDS + Archive)
    # search_keywords + title'dan ek keyword'ler çıkar
    keywords = list(script.get("search_keywords", []))
    title_words = _extract_title_keywords(script.get("title", ""))
    for tw in title_words:
        if tw not in " ".join(keywords).lower():
            keywords.append(tw)
    clip_paths = _fetch_clips(keywords, n=10)

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
        video_format = script.get("format", "news_analysis")

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
    for path in clip_paths:
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
