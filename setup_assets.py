"""
setup_assets.py — CC0 lisanslı SFX ve arka plan müziklerini otomatik indirir.

Kaynaklar (tamamen ücretsiz, API key gerektirmez):
  - Pixabay Audio API: ses efektleri ve müzik
  - Freesound.org API: ücretsiz hesap gerekli (FREESOUND_API_KEY)

Kullanım:
  python setup_assets.py              # Tüm varlıkları indir
  python setup_assets.py --sfx-only   # Sadece SFX
  python setup_assets.py --music-only # Sadece müzik
"""

import argparse
import os
import time
import requests

SFX_DIR = "assets/sfx"
MUSIC_DIR = "assets/music"
MAP_DIR = "assets/maps"
FONTS_DIR = "assets/fonts"

# Arapça font (Google Noto Fonts — OFL lisansı)
# NOT: notofonts/noto-fonts monoreposu dağıtıldı, artık bireysel repolar var.
_ARABIC_FONT_URLS = [
    # 1) Bireysel repo (güncel)
    "https://github.com/notofonts/arabic-naskh/raw/main/fonts/NotoNaskhArabic/ttf/NotoNaskhArabic-Bold.ttf",
    # 2) Google Fonts mirror
    "https://fonts.gstatic.com/s/notonaskharabic/v33/RrQPboN_4yJ0CjmYYkRmEXbFAoHRFQIXHxBUz9Z4.ttf",
    # 3) jsDelivr CDN üzerinden eski monorepo
    "https://cdn.jsdelivr.net/gh/notofonts/noto-fonts@main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Bold.ttf",
]
ARABIC_FONT_DEST = "assets/fonts/NotoNaskhArabic-Bold.ttf"

# Pixabay Audio API (ücretsiz, API key opsiyonel)
PIXABAY_API = "https://pixabay.com/api/videos/sounds/"

# İndirilecek SFX listesi: (dosya adı, arama terimi)
SFX_TARGETS = [
    ("drum_hit.wav",    "dramatic drum hit"),
    ("sword_clash.wav", "sword clash metal"),
    ("explosion.wav",   "explosion boom"),
    ("trumpet.wav",     "epic trumpet fanfare"),
]

# Müzik artık repo'da mevcut (assets/music/*.mp3 — Incompetech CC BY 4.0)
# setup_assets.py sadece SFX indirir, müzik kontrolü yapar.
MUSIC_TARGETS = []

# Alternatif: Freesound.org API
FREESOUND_API = "https://freesound.org/apiv2/search/text/"

# Hardcoded CC0 fallback URL'ler (Pixabay başarısız olursa)
FALLBACK_URLS = {
    "drum_hit.wav":             "https://cdn.pixabay.com/audio/2022/03/24/audio_8073b04b93.mp3",
    "sword_clash.wav":          "https://cdn.pixabay.com/audio/2022/01/18/audio_d0c6ff1cbf.mp3",
    "explosion.wav":            "https://cdn.pixabay.com/audio/2022/01/13/audio_6d5e8a5a11.mp3",
    "trumpet.wav":              "https://cdn.pixabay.com/audio/2022/11/22/audio_febc508520.mp3",
}


def _download(url: str, dest: str, label: str) -> bool:
    """URL'den dosyayı indirir. Başarılı ise True döndürür."""
    try:
        headers = {"User-Agent": "WarShorts/1.0 (video asset downloader)"}
        r = requests.get(url, timeout=30, stream=True, headers=headers)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = os.path.getsize(dest) / 1024
        print(f"  ✅ {label} → {dest} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return False


def _pixabay_search(query: str, api_key: str = None) -> str | None:
    """Pixabay'de ses arar, bulunan ilk öğenin URL'sini döndürür."""
    params = {"q": query, "per_page": 3}
    if api_key:
        params["key"] = api_key

    try:
        resp = requests.get(PIXABAY_API, params=params, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if hits:
            return hits[0].get("audio", {}).get("url") or hits[0].get("url")
    except Exception as e:
        print(f"  [pixabay] Arama hatası ({query}): {e}")
    return None


def _freesound_search(query: str, api_key: str) -> str | None:
    """Freesound'da ses arar, preview URL'sini döndürür."""
    try:
        resp = requests.get(
            FREESOUND_API,
            params={
                "query": query,
                "token": api_key,
                "fields": "previews",
                "filter": "license:Creative Commons 0",
                "page_size": 1,
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["previews"].get("preview-hq-mp3")
    except Exception as e:
        print(f"  [freesound] Arama hatası ({query}): {e}")
    return None


def download_world_map() -> None:
    """Wikimedia'dan 1280x720 dünya haritası indirir → assets/maps/world_base.png"""
    os.makedirs(MAP_DIR, exist_ok=True)
    dest = os.path.join(MAP_DIR, "world_base.png")

    if os.path.exists(dest):
        print(f"  ⏭️  world_base.png zaten mevcut, atlandı.")
        return

    print(f"\n🗺️  Dünya haritası indiriliyor ({MAP_DIR}/)...")

    # Wikimedia Commons — Equirectangular dünya haritası (Public Domain)
    map_urls = [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Equirectangular-projection.jpg/1280px-Equirectangular-projection.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Equirectangular_projection_SW.jpg/1280px-Equirectangular_projection_SW.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Gall%E2%80%93Peters_projection_SW.jpg/1280px-Gall%E2%80%93Peters_projection_SW.jpg",
    ]

    for url in map_urls:
        if _download(url, dest, "world_base.png"):
            # Boyutlandır ve koyu tema uygula
            try:
                from PIL import Image, ImageEnhance
                img = Image.open(dest).convert("RGB")
                img = img.resize((1280, 720), Image.LANCZOS)
                # Karartma — video overlay olarak kullanılacak
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(0.5)
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.3)
                img.save(dest)
                print(f"  ✅ Harita işlendi: 1280x720, koyu tema")
            except Exception as e:
                print(f"  ⚠️  Harita işleme hatası: {e}")
            return

    print(f"  ⚠️  Harita indirilemedi. overlay_system haritasız çalışacak.")


def download_sfx(pixabay_key: str = None, freesound_key: str = None) -> None:
    os.makedirs(SFX_DIR, exist_ok=True)
    print(f"\n🔊 SFX indiriliyor ({SFX_DIR}/)...")

    for filename, query in SFX_TARGETS:
        dest = os.path.join(SFX_DIR, filename)
        if os.path.exists(dest):
            print(f"  ⏭️  {filename} zaten mevcut, atlandı.")
            continue

        url = None

        # 1) Pixabay dene
        if pixabay_key or True:  # API key opsiyonel
            url = _pixabay_search(query, pixabay_key)

        # 2) Freesound dene
        if not url and freesound_key:
            url = _freesound_search(query, freesound_key)

        # 3) Hardcoded fallback
        if not url:
            url = FALLBACK_URLS.get(filename)
            if url:
                print(f"  ⚠️  {filename}: fallback URL kullanılıyor.")

        if url:
            _download(url, dest, filename)
        else:
            print(f"  ⚠️  {filename}: URL bulunamadı, manuel ekleyin.")

        time.sleep(0.5)


def download_music(pixabay_key: str = None, freesound_key: str = None) -> None:
    os.makedirs(MUSIC_DIR, exist_ok=True)
    print(f"\n🎵 Müzik kontrolü ({MUSIC_DIR}/)...")

    # Müzik dosyaları repo'da mevcut (Incompetech CC BY 4.0)
    music_files = [f for f in os.listdir(MUSIC_DIR) if f.endswith((".mp3", ".wav"))]
    if music_files:
        print(f"  ✅ {len(music_files)} müzik dosyası mevcut.")
    else:
        print(f"  ⚠️  Müzik dosyası bulunamadı! assets/music/ klasörüne mp3 ekleyin.")


def download_arabic_font() -> None:
    """Arapça altyazı ve başlık overlay için Noto Naskh Arabic Bold fontunu indirir."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    if os.path.exists(ARABIC_FONT_DEST):
        print(f"  ⏭️  NotoNaskhArabic-Bold.ttf zaten mevcut, atlandı.")
        return
    print(f"\n🔤 Arapça font indiriliyor...")
    for url in _ARABIC_FONT_URLS:
        if _download(url, ARABIC_FONT_DEST, "NotoNaskhArabic-Bold.ttf"):
            # Geçerli TTF mı kontrol et
            if os.path.exists(ARABIC_FONT_DEST) and os.path.getsize(ARABIC_FONT_DEST) > 50_000:
                print(f"  ✅ Font indirildi ({url.split('/')[2]})")
                return
            try:
                os.unlink(ARABIC_FONT_DEST)
            except OSError:
                pass
    print("  ⚠️  Font indirilemedi — sistem fontu kullanılacak (apt: fonts-noto-core)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WAR SHORTS — Varlık İndirici")
    parser.add_argument("--sfx-only", action="store_true")
    parser.add_argument("--music-only", action="store_true")
    args = parser.parse_args()

    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    freesound_key = os.environ.get("FREESOUND_API_KEY")

    print("=" * 50)
    print("📦 WAR SHORTS — Asset Setup")
    print("=" * 50)

    if not args.music_only:
        download_sfx(pixabay_key, freesound_key)

    if not args.sfx_only:
        download_music(pixabay_key, freesound_key)

    # Dünya haritası (overlay_system için)
    download_world_map()

    # Arapça font
    download_arabic_font()

    print("\n✅ Tamamlandı!")
    print(f"   SFX:   {SFX_DIR}/")
    print(f"   Müzik: {MUSIC_DIR}/")
