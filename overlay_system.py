"""
overlay_system.py — Video overlay üretim sistemi.

Özellikler:
  - Harita overlay'leri (ülke işaretleme)
  - İstatistik/infografik kartları
  - Bayrak overlay'leri (flagcdn.com)
  - Format bazlı görsel stiller (news_analysis, countdown, mystery)
  - Kırmızı alarm flash efekti
"""

import os
import re
import tempfile
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ uyumluluğu
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS

TARGET_W = 1080
TARGET_H = 1920
FONT_PATH = "assets/fonts/Montserrat-Bold.ttf"
MAP_PATH = "assets/maps/world_base.png"

# ─── Font yardımcısı ─────────────────────────────────────────────────────────

ARABIC_FONT_PATH = "assets/fonts/NotoNaskhArabic-Bold.ttf"


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


def _is_arabic(text: str) -> bool:
    return any(
        "\u0600" <= ch <= "\u06FF"
        or "\uFB50" <= ch <= "\uFDFF"
        or "\uFE70" <= ch <= "\uFEFF"
        for ch in text
    )


def _prepare_arabic_text(text: str) -> str:
    if not _is_arabic(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        import re as _re
        display = get_display(arabic_reshaper.reshape(text))
        # PIL bidi kontrol karakterlerini işleyemiyor — temizle
        display = _re.sub(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]', '', display)
        return display
    except ImportError:
        return text


def _load_arabic_font(size: int) -> ImageFont.FreeTypeFont:
    import glob as _glob
    candidate_paths = [
        ARABIC_FONT_PATH,
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    ]
    candidate_paths += sorted(_glob.glob("/usr/share/fonts/**/*Arabic*Bold*.ttf", recursive=True))
    candidate_paths += sorted(_glob.glob("/usr/share/fonts/**/*Arabic*.ttf", recursive=True))
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return _load_font(size)


# ─── Ülke Veritabanı ─────────────────────────────────────────────────────────

# Ülke adı / alias → standart isim
COUNTRIES = {
    "turkey": "Turkey", "türkiye": "Turkey", "turkiye": "Turkey", "turkish": "Turkey",
    "russia": "Russia", "russian": "Russia", "moscow": "Russia", "kremlin": "Russia", "soviet": "Russia",
    "china": "China", "chinese": "China", "beijing": "China", "prc": "China",
    "united states": "United States", "usa": "United States", "america": "United States",
    "american": "United States", "pentagon": "United States", "washington": "United States",
    "iran": "Iran", "iranian": "Iran", "tehran": "Iran", "persia": "Iran",
    "israel": "Israel", "israeli": "Israel", "tel aviv": "Israel", "mossad": "Israel",
    "india": "India", "indian": "India", "delhi": "India", "new delhi": "India",
    "pakistan": "Pakistan", "pakistani": "Pakistan", "islamabad": "Pakistan",
    "north korea": "North Korea", "pyongyang": "North Korea", "dprk": "North Korea",
    "south korea": "South Korea", "seoul": "South Korea",
    "japan": "Japan", "japanese": "Japan", "tokyo": "Japan",
    "germany": "Germany", "german": "Germany", "berlin": "Germany",
    "france": "France", "french": "France", "paris": "France",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "britain": "United Kingdom",
    "british": "United Kingdom", "england": "United Kingdom", "london": "United Kingdom",
    "ukraine": "Ukraine", "ukrainian": "Ukraine", "kyiv": "Ukraine", "kiev": "Ukraine",
    "saudi arabia": "Saudi Arabia", "saudi": "Saudi Arabia", "riyadh": "Saudi Arabia",
    "egypt": "Egypt", "egyptian": "Egypt", "cairo": "Egypt",
    "iraq": "Iraq", "iraqi": "Iraq", "baghdad": "Iraq",
    "syria": "Syria", "syrian": "Syria", "damascus": "Syria",
    "afghanistan": "Afghanistan", "afghan": "Afghanistan", "kabul": "Afghanistan",
    "brazil": "Brazil", "brazilian": "Brazil",
    "australia": "Australia", "australian": "Australia",
    "canada": "Canada", "canadian": "Canada",
    "italy": "Italy", "italian": "Italy", "rome": "Italy",
    "spain": "Spain", "spanish": "Spain", "madrid": "Spain",
    "poland": "Poland", "polish": "Poland", "warsaw": "Poland",
    "taiwan": "Taiwan", "taiwanese": "Taiwan", "taipei": "Taiwan",
    "vietnam": "Vietnam", "vietnamese": "Vietnam", "hanoi": "Vietnam",
    "indonesia": "Indonesia", "indonesian": "Indonesia", "jakarta": "Indonesia",
    "mexico": "Mexico", "mexican": "Mexico",
    "argentina": "Argentina",
    "south africa": "South Africa",
    "nigeria": "Nigeria",
    "ethiopia": "Ethiopia",
    "kenya": "Kenya",
    "colombia": "Colombia",
    "venezuela": "Venezuela",
    "cuba": "Cuba",
    "greece": "Greece", "greek": "Greece", "athens": "Greece",
    "sweden": "Sweden", "swedish": "Sweden",
    "norway": "Norway", "norwegian": "Norway",
    "finland": "Finland", "finnish": "Finland",
    "nato": "NATO",
    "uae": "UAE", "emirates": "UAE", "abu dhabi": "UAE", "dubai": "UAE",
    "qatar": "Qatar", "doha": "Qatar",
    "libya": "Libya",
    "yemen": "Yemen",
    "lebanon": "Lebanon",
    "jordan": "Jordan",
    "morocco": "Morocco",
    "tunisia": "Tunisia",
    "algeria": "Algeria",
    "sudan": "Sudan",
    "somalia": "Somalia",
    "myanmar": "Myanmar", "burma": "Myanmar",
    "thailand": "Thailand", "thai": "Thailand", "bangkok": "Thailand",
    "philippines": "Philippines", "filipino": "Philippines", "manila": "Philippines",
    "malaysia": "Malaysia",
    "singapore": "Singapore",
    "bangladesh": "Bangladesh",
    "sri lanka": "Sri Lanka",
    "nepal": "Nepal",
    "romania": "Romania",
    "hungary": "Hungary", "budapest": "Hungary",
    "czech republic": "Czech Republic", "czechia": "Czech Republic", "prague": "Czech Republic",
    "austria": "Austria", "vienna": "Austria",
    "switzerland": "Switzerland",
    "belgium": "Belgium", "brussels": "Belgium",
    "netherlands": "Netherlands", "dutch": "Netherlands",
    "portugal": "Portugal",
    "denmark": "Denmark",
    "ireland": "Ireland",
    "scotland": "Scotland",
    "serbia": "Serbia", "belgrade": "Serbia",
    "croatia": "Croatia",
    "bulgaria": "Bulgaria",
    "georgia": "Georgia", "tbilisi": "Georgia",
    "armenia": "Armenia", "yerevan": "Armenia",
    "azerbaijan": "Azerbaijan", "baku": "Azerbaijan",
    "kazakhstan": "Kazakhstan",
    "uzbekistan": "Uzbekistan",
    "turkmenistan": "Turkmenistan",
}

# Ülke → 1280x720 harita koordinatları (x, y)
COUNTRY_COORDS = {
    "Turkey": (720, 280), "Russia": (800, 170), "China": (950, 300),
    "United States": (220, 260), "Iran": (770, 310), "Israel": (720, 310),
    "India": (870, 350), "Pakistan": (840, 320), "North Korea": (990, 260),
    "South Korea": (990, 275), "Japan": (1020, 260), "Germany": (650, 225),
    "France": (630, 240), "United Kingdom": (620, 210), "Ukraine": (710, 230),
    "Saudi Arabia": (750, 340), "Egypt": (700, 330), "Iraq": (745, 305),
    "Syria": (730, 295), "Afghanistan": (830, 300), "Brazil": (370, 460),
    "Australia": (1060, 510), "Canada": (250, 190), "Italy": (655, 255),
    "Spain": (615, 260), "Poland": (665, 220), "Taiwan": (990, 320),
    "Vietnam": (950, 360), "Indonesia": (970, 430), "Mexico": (230, 330),
    "Argentina": (340, 530), "South Africa": (680, 530), "Nigeria": (640, 385),
    "Ethiopia": (725, 390), "Kenya": (730, 420), "Colombia": (310, 380),
    "Venezuela": (330, 370), "Cuba": (280, 330), "Greece": (680, 265),
    "Sweden": (655, 175), "Norway": (645, 165), "Finland": (680, 170),
    "UAE": (775, 340), "Qatar": (770, 340), "Libya": (660, 330),
    "Yemen": (760, 360), "Lebanon": (725, 295), "Jordan": (725, 310),
    "Morocco": (600, 310), "Tunisia": (645, 290), "Algeria": (625, 300),
    "Sudan": (710, 370), "Somalia": (755, 400),
}

# Ülke → ISO bayrak kodu (flagcdn.com için)
COUNTRY_TO_CODE = {
    "Turkey": "tr", "Russia": "ru", "China": "cn", "United States": "us",
    "Iran": "ir", "Israel": "il", "India": "in", "Pakistan": "pk",
    "North Korea": "kp", "South Korea": "kr", "Japan": "jp", "Germany": "de",
    "France": "fr", "United Kingdom": "gb", "Ukraine": "ua", "Saudi Arabia": "sa",
    "Egypt": "eg", "Iraq": "iq", "Syria": "sy", "Afghanistan": "af",
    "Brazil": "br", "Australia": "au", "Canada": "ca", "Italy": "it",
    "Spain": "es", "Poland": "pl", "Taiwan": "tw", "Vietnam": "vn",
    "Indonesia": "id", "Mexico": "mx", "Argentina": "ar", "South Africa": "za",
    "Nigeria": "ng", "Ethiopia": "et", "Kenya": "ke", "Colombia": "co",
    "Venezuela": "ve", "Cuba": "cu", "Greece": "gr", "Sweden": "se",
    "Norway": "no", "Finland": "fi", "UAE": "ae", "Qatar": "qa",
    "Libya": "ly", "Yemen": "ye", "Lebanon": "lb", "Jordan": "jo",
    "Morocco": "ma", "Tunisia": "tn", "Algeria": "dz", "Sudan": "sd",
    "Somalia": "so", "Myanmar": "mm", "Thailand": "th", "Philippines": "ph",
    "Malaysia": "my", "Singapore": "sg", "Bangladesh": "bd", "Sri Lanka": "lk",
    "Nepal": "np", "Romania": "ro", "Hungary": "hu", "Czech Republic": "cz",
    "Austria": "at", "Switzerland": "ch", "Belgium": "be", "Netherlands": "nl",
    "Portugal": "pt", "Denmark": "dk", "Ireland": "ie", "Serbia": "rs",
    "Croatia": "hr", "Bulgaria": "bg", "Georgia": "ge", "Armenia": "am",
    "Azerbaijan": "az", "Kazakhstan": "kz", "Uzbekistan": "uz",
    "Turkmenistan": "tm",
}

# ─── İstatistik Regex Kalıpları ───────────────────────────────────────────────

STAT_PATTERNS = [
    # Currency: $13 billion, $500 million, €2.5 billion
    (r'[\$€£]\s*[\d,.]+\s*(?:billion|million|trillion|thousand|B|M|T)', 'currency'),
    # Military: 48,000 troops, 1,200 tanks, 300 warheads
    (r'[\d,]+\s+(?:troops|soldiers|tanks|aircraft|ships|warheads|missiles|drones|jets|submarines|carriers|divisions|battalions|personnel|fighters|bombers|helicopters|vehicles|rockets|launchers|guns|bases)', 'military'),
    # Speed: Mach 10, 2,000 km/h, 500 mph
    (r'[Mm]ach\s+[\d.]+', 'speed'),
    (r'[\d,]+\s*(?:km/h|mph|knots|m/s)', 'speed'),
    # Percentage: 95%, 40 percent
    (r'[\d.]+\s*(?:%|percent)', 'percentage'),
    # Distance/Range: 2,500 km, 500 miles, 10,000 nautical miles
    (r'[\d,]+\s*(?:km|miles|nautical miles|meters|feet|yards|kilometers|kilometres)', 'distance'),
    # Weight/Tonnage: 50,000 tons, 10 tonnes, 500 kg
    (r'[\d,]+\s*(?:tons?|tonnes?|kg|kilograms?|pounds?|lbs?)', 'weight'),
    # Years/Dates: 1945, 2024, 21st century
    (r'(?:19|20)\d{2}', 'year'),
    # Generic large numbers: 1.5 million, 500,000
    (r'[\d,]+\s*(?:billion|million|trillion|thousand)', 'number'),
]


# ─── Metin Analizi ────────────────────────────────────────────────────────────

def extract_countries_with_timing(narration: str, vtt_chunks: list) -> list:
    """
    Narration metninde geçen ülkeleri VTT zamanlaması ile eşleştirir.
    Returns: [{"country": "Turkey", "start": 3.5, "end": 7.0}, ...]
    """
    found = []
    seen_countries = set()

    # Her VTT chunk'ta ülke ara
    for chunk in vtt_chunks:
        text_lower = chunk["text"].lower()
        for alias, country in COUNTRIES.items():
            if country in seen_countries:
                continue
            # Tam kelime eşleşmesi
            if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
                found.append({
                    "country": country,
                    "start": chunk["start"],
                    "end": chunk["end"],
                })
                seen_countries.add(country)

    return found


def extract_statistics_with_timing(narration: str, vtt_chunks: list) -> list:
    """
    Narration metninde geçen istatistikleri VTT zamanlaması ile eşleştirir.
    Returns: [{"value": "$13 billion", "label": "currency", "start": 5.0, "end": 8.0}, ...]
    """
    found = []
    seen_values = set()

    for chunk in vtt_chunks:
        text = chunk["text"]
        for pattern, label in STAT_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if match in seen_values:
                    continue
                seen_values.add(match)
                found.append({
                    "value": match.strip(),
                    "label": label,
                    "start": chunk["start"],
                    "end": chunk["end"],
                })

    return found


# ─── Harita Overlay ───────────────────────────────────────────────────────────

def create_map_overlay(country: str, base_map_path: str = MAP_PATH) -> np.ndarray | None:
    """
    Dünya haritası üzerinde ülkeyi işaretler.
    Returns: 1080x600 RGBA numpy array veya None.
    """
    if country not in COUNTRY_COORDS:
        return None
    if not os.path.exists(base_map_path):
        print(f"[overlay] Harita bulunamadı: {base_map_path}")
        return None

    try:
        base = Image.open(base_map_path).convert("RGBA")
        base = base.resize((1280, 720), Image.LANCZOS)

        draw = ImageDraw.Draw(base)
        x, y = COUNTRY_COORDS[country]

        # Kırmızı daire (pulsing efekti simülasyonu — dış halo)
        for r, alpha in [(30, 60), (22, 100), (15, 180)]:
            draw.ellipse(
                [(x - r, y - r), (x + r, y + r)],
                fill=(255, 30, 30, alpha),
                outline=None,
            )

        # İç nokta
        draw.ellipse([(x - 8, y - 8), (x + 8, y + 8)], fill=(255, 50, 50, 255))

        # Ülke etiketi
        font = _load_font(28)
        label = country.upper()
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]

        label_x = x - tw // 2
        label_y = y - 50

        # Etiket arka planı
        padding = 6
        draw.rectangle(
            [(label_x - padding, label_y - padding),
             (label_x + tw + padding, label_y + (bbox[3] - bbox[1]) + padding)],
            fill=(0, 0, 0, 180),
        )
        draw.text((label_x, label_y), label, font=font, fill=(255, 255, 255, 255))

        # Ok çizgisi (etiket → nokta)
        draw.line([(x, label_y + (bbox[3] - bbox[1]) + padding + 2), (x, y - 15)],
                  fill=(255, 50, 50, 200), width=2)

        # Final boyutlandırma: 1080x600 (video içine sığacak şekilde)
        result = base.resize((TARGET_W, 600), Image.LANCZOS)
        return np.array(result)

    except Exception as e:
        print(f"[overlay] Harita overlay hatası ({country}): {e}")
        return None


# ─── İstatistik Kartları ──────────────────────────────────────────────────────

def create_stat_card(value: str, label: str) -> np.ndarray:
    """
    Modern glassmorphism istatistik kartı.
    Returns: 460x200 RGBA numpy array.
    """
    w, h = 460, 200
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Arka plan: koyu yarı saydam, yuvarlak köşeli
    draw.rounded_rectangle([(0, 0), (w, h)], radius=20,
                            fill=(12, 12, 20, 210))

    # Sol kenar aksan çizgisi (kırmızı dikey)
    draw.rounded_rectangle([(0, 0), (5, h)], radius=4,
                            fill=(220, 40, 40, 255))

    # Üst ince çizgi (soluk beyaz — glass efekti)
    draw.rectangle([(5, 0), (w, 1)], fill=(255, 255, 255, 30))

    # Etiket — küçük, kırmızı, üstte
    label_map = {
        "currency": "ECONOMIC VALUE",
        "military": "MILITARY FORCE",
        "speed": "SPEED",
        "percentage": "PERCENTAGE",
        "distance": "RANGE",
        "weight": "WEIGHT",
        "number": "KEY FIGURE",
    }
    label_text = label_map.get(label, label.upper())
    font_label = _load_font(22)
    lbbox = draw.textbbox((0, 0), label_text, font=font_label)
    lw = lbbox[2] - lbbox[0]
    draw.text((28, 22), label_text, font=font_label, fill=(200, 50, 50, 230))

    # Etiket altında ince seperatör
    draw.rectangle([(28, 50), (w - 28, 51)], fill=(255, 255, 255, 18))

    # Büyük değer metni
    font_big = _load_font(68)
    bbox = draw.textbbox((0, 0), value, font=font_big)
    text_w = bbox[2] - bbox[0]
    if text_w > w - 56:
        font_big = _load_font(50)
        bbox = draw.textbbox((0, 0), value, font=font_big)
        text_w = bbox[2] - bbox[0]

    vx = (w - text_w) // 2
    vy = 64

    # Hafif gölge
    draw.text((vx + 2, vy + 2), value, font=font_big, fill=(0, 0, 0, 120))
    # Beyaz ana değer
    draw.text((vx, vy), value, font=font_big, fill=(255, 255, 255, 255))

    return np.array(img)


# ─── Bayrak Overlay ──────────────────────────────────────────────────────────

_flag_cache = {}  # session boyunca cache


def download_flag(country: str) -> str | None:
    """
    flagcdn.com'dan bayrak PNG indirir. Cache kullanır.
    Returns: dosya yolu veya None.
    """
    if country in _flag_cache:
        return _flag_cache[country]

    code = COUNTRY_TO_CODE.get(country)
    if not code:
        return None

    url = f"https://flagcdn.com/w160/{code}.png"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix=f"flag_{code}_")
        tmp.write(resp.content)
        tmp.close()
        _flag_cache[country] = tmp.name
        print(f"[overlay] Bayrak indirildi: {country} ({code})")
        return tmp.name
    except Exception as e:
        print(f"[overlay] Bayrak indirilemedi ({country}): {e}")
        return None


def create_flag_overlay(flag_path: str) -> np.ndarray | None:
    """
    Bayrak görselini overlay formatına çevirir.
    Returns: 200x140 RGBA numpy array (beyaz border dahil).
    """
    try:
        flag = Image.open(flag_path).convert("RGBA")
        flag = flag.resize((180, 120), Image.LANCZOS)

        # Beyaz border ile canvas
        canvas = Image.new("RGBA", (200, 140), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([(0, 0), (199, 139)], fill=(255, 255, 255, 230))
        canvas.paste(flag, (10, 10), flag)

        # Hafif gölge efekti
        shadow = Image.new("RGBA", (200, 140), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rectangle([(3, 3), (199, 139)], fill=(0, 0, 0, 60))

        result = Image.alpha_composite(shadow, canvas)
        return np.array(result)

    except Exception as e:
        print(f"[overlay] Bayrak overlay hatası: {e}")
        return None


# ─── Format Bazlı Overlay'ler ─────────────────────────────────────────────────

def create_breaking_banner(duration: float, title: str = "") -> np.ndarray:
    """
    Kırmızı 'BREAKING MILITARY ANALYSIS' banner (üst, 200px yükseklik).
    title verilirse ikinci satırda altın rengiyle script başlığı gösterilir.
    Returns: RGBA numpy array.
    """
    w, h = TARGET_W, 200
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Kırmızı gradient arka plan
    for y in range(h):
        alpha = int(220 - (y / h) * 80)
        r_val = max(140, int(200 - (y / h) * 60))
        draw.line([(0, y), (w, y)], fill=(r_val, 15, 15, alpha))

    # Ana metin
    font = _load_font(38)
    text = "BREAKING MILITARY ANALYSIS"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (w - tw) // 2
    ty = 20

    # Gölge + metin
    draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 0, 0, 180))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Script başlığı (altın rengi, ikinci satır)
    if title:
        is_ar = _is_arabic(title)
        font_title = _load_arabic_font(26) if is_ar else _load_font(26)
        title_short = (title[:55] + "…") if len(title) > 58 else title
        title_display = _prepare_arabic_text(title_short) if is_ar else title_short
        t2_bbox = draw.textbbox((0, 0), title_display, font=font_title)
        t2w = t2_bbox[2] - t2_bbox[0]
        t2x = (w - t2w) // 2
        t2y = ty + (bbox[3] - bbox[1]) + 8
        draw.text((t2x + 1, t2y + 1), title_display, font=font_title, fill=(0, 0, 0, 160))
        draw.text((t2x, t2y), title_display, font=font_title, fill=(255, 220, 0, 240))

    # Alt altın çizgi
    draw.rectangle([(40, h - 8), (w - 40, h - 4)], fill=(255, 220, 0, 200))

    # "LIVE" badge
    font_small = _load_font(24)
    draw.rounded_rectangle([(30, ty + 4), (110, ty + 38)], radius=4,
                           fill=(255, 30, 30, 255))
    draw.text((46, ty + 7), "LIVE", font=font_small, fill=(255, 255, 255, 255))

    return np.array(img)


def create_news_ticker(text: str, duration: float) -> np.ndarray:
    """
    Alt kayan haber ticker arka planı (100px yükseklik).
    Returns: RGBA numpy array.
    """
    w, h = TARGET_W, 100
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Koyu arka plan
    draw.rectangle([(0, 0), (w, h)], fill=(10, 10, 20, 210))

    # Üst kırmızı çizgi
    draw.rectangle([(0, 0), (w, 4)], fill=(220, 30, 30, 255))

    # Metin — Arapça ve Latin ayrı fontlarla çizilir
    ty_base = None
    if _is_arabic(text):
        ar_font = _load_arabic_font(26)
        lat_font = _load_font(24)
        lat_text = "MILITARY INTELLIGENCE REPORT"
        ar_display = _prepare_arabic_text(text)
        # Latin metin solda
        lat_bbox = draw.textbbox((0, 0), lat_text, font=lat_font)
        ty_base = (h - (lat_bbox[3] - lat_bbox[1])) // 2
        draw.text((20, ty_base), lat_text, font=lat_font, fill=(200, 200, 210, 255))
        # Arapça metin sağda
        ar_bbox = draw.textbbox((0, 0), ar_display, font=ar_font)
        ar_x = w - (ar_bbox[2] - ar_bbox[0]) - 20
        ar_ty = (h - (ar_bbox[3] - ar_bbox[1])) // 2
        draw.text((ar_x, ar_ty), ar_display, font=ar_font, fill=(200, 200, 210, 255))
    else:
        font = _load_font(26)
        ticker_text = f"    {text}    |    MILITARY INTELLIGENCE REPORT    |    {text}    "
        bbox = draw.textbbox((0, 0), ticker_text, font=font)
        ty_base = (h - (bbox[3] - bbox[1])) // 2
        draw.text((20, ty_base), ticker_text, font=font, fill=(200, 200, 210, 255))

    return np.array(img)


def create_lower_third(title: str, label: str = "MILITARY ANALYSIS") -> np.ndarray:
    """
    TV chyron (lower third) overlay — 1080x140px RGBA.
    Sol kenardan sağa doğru azalan gradient arka plan + kırmızı aksan çizgileri.
    Returns: RGBA numpy array.
    """
    w, h = TARGET_W, 140
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient arka plan: sol opak → sağ yarı saydam
    for x in range(w):
        alpha = int(200 * max(0, 1.0 - (x / w) * 0.55))
        draw.line([(x, 0), (x, h)], fill=(8, 8, 18, alpha))

    # Sol kırmızı aksan çizgisi
    draw.rectangle([(0, 0), (5, h)], fill=(220, 30, 30, 255))

    # Üst ince kırmızı çizgi
    draw.rectangle([(0, 0), (w, 3)], fill=(220, 30, 30, 220))

    # Kategori etiketi (kırmızı, küçük, üst)
    font_label = _load_font(22)
    draw.text((18, 14), label.upper(), font=font_label, fill=(200, 50, 50, 230))

    # Script başlığı (beyaz, büyük, alt)
    is_ar = _is_arabic(title)
    font_title = _load_arabic_font(32) if is_ar else _load_font(32)
    title_short = (title[:52] + "…") if len(title) > 55 else title
    title_display = _prepare_arabic_text(title_short) if is_ar else title_short
    t_bbox = draw.textbbox((0, 0), title_display, font=font_title)
    # Arapça: sağdan hizala; Latin: soldan hizala
    tx = w - 18 - (t_bbox[2] - t_bbox[0]) if is_ar else 18
    draw.text((tx, 52), title_display, font=font_title, fill=(255, 255, 255, 240))

    # Alt ince kırmızı çizgi
    draw.rectangle([(0, h - 3), (w, h)], fill=(220, 30, 30, 180))

    return np.array(img)


def create_countdown_number(number: int) -> np.ndarray:
    """
    Büyük sayı overlay (400x400px, kırmızı daire içinde).
    Returns: RGBA numpy array.
    """
    size = 400
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dış halo
    for r, alpha in [(190, 30), (170, 60), (150, 100)]:
        cx, cy = size // 2, size // 2
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                     fill=(200, 20, 20, alpha))

    # Ana daire
    r = 130
    cx, cy = size // 2, size // 2
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                 fill=(220, 30, 30, 240))

    # Sayı
    font = _load_font(160)
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2
    ty = (size - th) // 2 - 15

    draw.text((tx + 3, ty + 3), text, font=font, fill=(0, 0, 0, 120))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    return np.array(img)


def create_glitch_frame(frame: np.ndarray) -> np.ndarray:
    """
    RGB split + static noise glitch efekti.
    Returns: glitch uygulanmış numpy array.
    """
    h, w = frame.shape[:2]
    result = frame.copy()

    # RGB channel shift
    shift = np.random.randint(5, 15)
    result[:, shift:, 0] = frame[:, :-shift, 0]   # Red shift right
    result[:, :-shift, 2] = frame[:, shift:, 2]    # Blue shift left

    # Random horizontal line glitches
    n_lines = np.random.randint(3, 8)
    for _ in range(n_lines):
        y = np.random.randint(0, h)
        line_h = np.random.randint(2, 10)
        x_shift = np.random.randint(-30, 30)
        y_end = min(y + line_h, h)
        if x_shift > 0:
            result[y:y_end, x_shift:] = frame[y:y_end, :w - x_shift]
        elif x_shift < 0:
            result[y:y_end, :w + x_shift] = frame[y:y_end, -x_shift:]

    # Static noise overlay
    noise = np.random.randint(0, 40, (h, w, 3), dtype=np.uint8)
    result = np.clip(result.astype(np.int16) + noise.astype(np.int16), 0, 255).astype(np.uint8)

    return result


def create_format_overlays(format_type: str, duration: float, title: str) -> list:
    """
    Format bazlı overlay bilgilerini döndürür.
    Returns: [{"type": "banner"|"ticker"|"countdown"|"glitch", "data": np.ndarray, "start": float, "end": float, "position": tuple}, ...]
    """
    overlays = []

    if format_type == "news_analysis":
        # Kırmızı BREAKING banner (üst) — ilk 5 saniye + son 5 saniye
        banner = create_breaking_banner(duration, title=title)
        overlays.append({
            "type": "banner",
            "data": banner,
            "start": 0.0,
            "end": min(5.0, duration),
            "position": ("center", 0),
        })
        if duration > 15:
            overlays.append({
                "type": "banner",
                "data": banner,
                "start": max(0, duration - 8.0),
                "end": duration,
                "position": ("center", 0),
            })

        # Ticker banner'ın hemen altında (y=200) — video boyunca
        ticker = create_news_ticker(title, duration)
        overlays.append({
            "type": "ticker",
            "data": ticker,
            "start": 0.0,
            "end": duration,
            "position": ("center", 200),
        })

        # Lower third chyron — hook sonrası (4s) ve video ortasında (ikişer kez)
        lower = create_lower_third(title)
        guard = duration - 7.0  # CTA bölgesine girmemek için
        for lt in [4.0, duration * 0.5]:
            if lt + 4.0 < guard:
                overlays.append({
                    "type": "lower_third",
                    "data": lower,
                    "start": lt,
                    "end": lt + 4.0,
                    "position": ("center", TARGET_H - 400),
                })

    elif format_type == "countdown":
        # Büyük sayılar — 3, 2, 1
        countdown_times = [3.0, 12.0, 25.0]
        for i, t in enumerate(countdown_times):
            if t >= duration:
                continue
            num = 3 - i
            if num < 1:
                break
            cd = create_countdown_number(num)
            overlays.append({
                "type": "countdown",
                "data": cd,
                "start": t,
                "end": t + 1.5,
                "position": ("center", TARGET_H // 2 - 200),
            })

    elif format_type == "mystery":
        # Glitch efekti — klip geçişlerinde
        # Glitch bilgisi — video_builder'da uygulanacak
        glitch_times = [5.0, 15.0, 30.0, 45.0]
        for t in glitch_times:
            if t >= duration:
                continue
            overlays.append({
                "type": "glitch",
                "data": None,  # Frame bazlı uygulanacak
                "start": t,
                "end": t + 0.3,
                "position": None,
            })

    return overlays


# ─── Kırmızı Alarm Flash ─────────────────────────────────────────────────────

def create_red_flash_data() -> np.ndarray:
    """
    Kırmızı alarm efekti için 1080x1920 RGBA frame.
    Returns: RGBA numpy array.
    """
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 0, 0, 127))
    # Merkeze doğru hafifleyen gradient
    draw = ImageDraw.Draw(img)
    cx, cy = TARGET_W // 2, TARGET_H // 2
    for i in range(20):
        alpha = max(0, 127 - i * 6)
        inset = i * 25
        if inset >= min(cx, cy):
            break
        draw.rectangle(
            [(inset, inset), (TARGET_W - inset, TARGET_H - inset)],
            fill=(255, 0, 0, alpha),
        )
    return np.array(img)
