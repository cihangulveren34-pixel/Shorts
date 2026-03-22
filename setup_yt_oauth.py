#!/usr/bin/env python3
"""
yt-dlp YouTube OAuth2 token üreticisi.

Bu scripti LOCAL makinende bir kere çalıştır:
    python setup_yt_oauth.py

Ne yapar:
1. yt-dlp'yi OAuth2 device-code flow ile çalıştırır.
2. Ekranda bir URL + kod gösterir → tarayıcıda Google hesabınla onayla.
3. Token ~/.cache/yt-dlp/youtube-oauth2/token.json dosyasına kaydedilir.
4. Token içeriğini ekrana basar → GitHub Secret olarak kaydet.

GitHub Actions'ta kullanım:
- Repository Settings → Secrets → New repository secret
- Name: YT_OAUTH2_TOKEN
- Value: Bu scriptin çıktısındaki JSON
"""
import json
import os
import subprocess
import sys


def main():
    # Önce yt-dlp'nin güncel olduğundan emin ol
    print("yt-dlp güncelleniyor...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                   capture_output=True)

    token_path = os.path.expanduser(
        "~/.cache/yt-dlp/youtube-oauth2/token.json")

    # Mevcut token varsa sor
    if os.path.isfile(token_path):
        print(f"\nMevcut token bulundu: {token_path}")
        ans = input("Yeni token üretmek istiyor musun? [e/H]: ").strip().lower()
        if ans != "e":
            _print_token(token_path)
            return

    print("\n" + "=" * 60)
    print("YouTube OAuth2 Device Code Flow başlatılıyor...")
    print("=" * 60)
    print()
    print("Aşağıda bir URL ve kod göreceksin.")
    print("1) URL'yi tarayıcıda aç")
    print("2) Google hesabınla giriş yap")
    print("3) Kodu gir ve onayla")
    print("4) Bu terminal'e geri dön — token otomatik kaydedilecek")
    print()

    # yt-dlp'yi OAuth2 ile çalıştır (kısa bir video, sadece info çek)
    cmd = [
        "yt-dlp",
        "--username", "oauth2",
        "--password", "",
        "--skip-download",
        "--print", "title",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # "Me at the zoo"
    ]

    result = subprocess.run(cmd, timeout=120)

    if result.returncode != 0:
        print("\nHata: OAuth2 flow başarısız oldu.")
        print("yt-dlp'nin güncel olduğundan emin ol: pip install -U yt-dlp")
        sys.exit(1)

    if os.path.isfile(token_path):
        _print_token(token_path)
    else:
        # Bazı yt-dlp versiyonları farklı path kullanabilir
        cache_dir = os.path.expanduser("~/.cache/yt-dlp")
        print(f"\nToken dosyası beklenen yerde bulunamadı: {token_path}")
        print(f"Cache dizini içeriği:")
        for root, dirs, files in os.walk(cache_dir):
            for f in files:
                fp = os.path.join(root, f)
                print(f"  {fp}")
                if f.endswith(".json") and "oauth" in fp.lower():
                    print(f"\n  ^ Bu dosya OAuth2 token olabilir!")
                    _print_token(fp)
                    return
        print("\nToken bulunamadı. yt-dlp versiyonunu kontrol et.")
        sys.exit(1)


def _print_token(path: str):
    with open(path) as f:
        token_data = f.read().strip()

    # JSON olduğunu doğrula
    try:
        json.loads(token_data)
    except json.JSONDecodeError:
        print(f"Uyarı: {path} geçerli JSON değil!")
        print(f"İçerik: {token_data[:200]}")
        return

    print()
    print("=" * 60)
    print("TOKEN HAZIR — Aşağıdaki değeri GitHub Secret olarak kaydet:")
    print("=" * 60)
    print()
    print(f"Secret adı: YT_OAUTH2_TOKEN")
    print(f"Secret değeri:")
    print()
    print(token_data)
    print()
    print("=" * 60)
    print("Adımlar:")
    print("1. GitHub repo → Settings → Secrets and variables → Actions")
    print("2. 'New repository secret' tıkla")
    print("3. Name: YT_OAUTH2_TOKEN")
    print("4. Value: Yukarıdaki JSON'ı yapıştır")
    print("5. 'Add secret' tıkla")
    print("=" * 60)


if __name__ == "__main__":
    main()
