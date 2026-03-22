#!/usr/bin/env python3
"""
pytubefix YouTube OAuth token üreticisi.

Bu scripti LOCAL makinende bir kere çalıştır:
    python setup_yt_oauth.py

VEYA GitHub Actions workflow'unu kullan (telefondan da çalışır):
    Actions → "YouTube OAuth Token Kurulumu" → Run workflow

Ne yapar:
1. pytubefix'i OAuth device-code flow ile çalıştırır.
2. Ekranda bir URL + kod gösterir → tarayıcıda Google hesabınla onayla.
3. Token .pytubefix_oauth.json dosyasına kaydedilir.
4. Token içeriğini ekrana basar → GitHub Secret olarak kaydet.

GitHub Actions'ta kullanım:
- Repository Settings → Secrets → New repository secret
- Name: PYTUBEFIX_OAUTH_TOKEN
- Value: Bu scriptin çıktısındaki JSON
"""
import json
import os
import subprocess
import sys


def main():
    print("pytubefix güncelleniyor...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "pytubefix"],
                   capture_output=True)

    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              ".pytubefix_oauth.json")

    if os.path.isfile(token_path):
        print(f"\nMevcut token bulundu: {token_path}")
        ans = input("Yeni token üretmek istiyor musun? [e/H]: ").strip().lower()
        if ans != "e":
            _print_token(token_path)
            return

    print("\n" + "=" * 60)
    print("YouTube OAuth Device Code Flow başlatılıyor...")
    print("=" * 60)
    print()
    print("Aşağıda bir URL ve kod göreceksin.")
    print("1) URL'yi tarayıcıda aç")
    print("2) Google hesabınla giriş yap")
    print("3) Kodu gir ve onayla")
    print("4) Bu terminal'e geri dön — token otomatik kaydedilecek")
    print()

    try:
        from pytubefix import YouTube
    except ImportError:
        print("pytubefix kurulu değil: pip install pytubefix")
        sys.exit(1)

    try:
        yt = YouTube(
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            client="ANDROID_TESTSUITE",
            use_oauth=True,
            allow_oauth_cache=True,
            token_file=token_path,
        )
        print(f"\nVideo başlığı: {yt.title}")
        print("OAuth başarılı!")
    except Exception as e:
        print(f"\nHata: {e}")
        if not os.path.isfile(token_path):
            sys.exit(1)

    if os.path.isfile(token_path):
        _print_token(token_path)
    else:
        print("\nToken dosyası oluşturulamadı!")
        sys.exit(1)


def _print_token(path: str):
    with open(path) as f:
        token_data = f.read().strip()

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
    print(f"Secret adı: PYTUBEFIX_OAUTH_TOKEN")
    print(f"Secret değeri:")
    print()
    print(token_data)
    print()
    print("=" * 60)
    print("Adımlar:")
    print("1. GitHub repo → Settings → Secrets and variables → Actions")
    print("2. 'New repository secret' tıkla")
    print("3. Name: PYTUBEFIX_OAUTH_TOKEN")
    print("4. Value: Yukarıdaki JSON'ı yapıştır")
    print("5. 'Add secret' tıkla")
    print("=" * 60)


if __name__ == "__main__":
    main()
