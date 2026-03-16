# WAR SHORTS — Otomatik YouTube Shorts Pipeline

Tarihsel "ya olsaydı?" senaryoları üzerine 50-55 saniyelik YouTube Shorts videoları üreten tam otomatik bir içerik üretim sistemi.

---

## Özellikler

- Google Gemini 1.5 Flash ile ücretsiz senaryo üretimi
- Edge TTS ile otomatik sesli anlatım
- Pexels'tan ücretsiz video klip indirme
- Ken Burns zoom, altyazı, ilerleme çubuğu, CTA ekranı
- YouTube'a otomatik yükleme
- Instagram, TikTok, Twitter, Facebook'a çapraz paylaşım
- Türkçe ve İngilizce dil desteği
- Telegram ve Discord bildirim sistemi
- Toplu üretim (haftada 7 video)
- GitHub Actions ile tam otomasyon

---

## Gereksinimler

### Sistem Gereksinimleri

- Python 3.9+
- FFmpeg
- ImageMagick
- fonts-liberation (Linux)

### Gerekli API Anahtarları

| Servis | Zorunlu | Açıklama |
|--------|---------|----------|
| [Google Gemini API](https://aistudio.google.com/app/apikey) | Evet | Senaryo üretimi (ücretsiz: günde 1500 istek) |
| [Pexels API](https://www.pexels.com/api/) | Evet | Stok video klipleri (ücretsiz) |
| YouTube OAuth2 | Evet | Video yükleme |
| [Telegram Bot](https://t.me/BotFather) | Hayır | Bildirimler |
| Discord Webhook | Hayır | Bildirimler |
| Instagram API | Hayır | Çapraz paylaşım |
| TikTok API | Hayır | Çapraz paylaşım |
| Twitter API | Hayır | Çapraz paylaşım |
| Facebook API | Hayır | Çapraz paylaşım |

---

## Kurulum

### 1. Depoyu Klonla

```bash
git clone https://github.com/kullanici/war-shorts.git
cd war-shorts
```

### 2. Sistem Bağımlılıklarını Yükle

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg imagemagick fonts-liberation
```

**macOS:**
```bash
brew install ffmpeg imagemagick
```

**Windows:**
- [FFmpeg](https://ffmpeg.org/download.html) indirip PATH'e ekle
- [ImageMagick](https://imagemagick.org/script/download.php) kur

### 3. Python Bağımlılıklarını Yükle

```bash
pip install -r requirements.txt
```

### 4. Ortam Değişkenlerini Ayarla

`.env` dosyası oluştur veya ortam değişkenlerini dışa aktar:

```bash
# Zorunlu
export GEMINI_API_KEY="gemini_api_anahtarin"
export PEXELS_API_KEY="pexels_api_anahtarin"

# YouTube (aşağıdaki adımdan sonra doldurulacak)
export YOUTUBE_TOKEN_JSON='{"token": "..."}'

# İsteğe bağlı bildirimler
export TELEGRAM_BOT_TOKEN="telegram_bot_token"
export TELEGRAM_CHAT_ID="telegram_sohbet_id"
export DISCORD_WEBHOOK_URL="discord_webhook_url"
```

### 5. YouTube OAuth2 Token Al

Google Cloud Console'dan `client_secret.json` dosyasını indirip proje dizinine koy, ardından:

```bash
python get_youtube_token.py
```

Tarayıcı açılacak, YouTube hesabına izin ver. Bu işlem `token.json` dosyasını üretir.

`token.json` içeriğini `YOUTUBE_TOKEN_JSON` ortam değişkenine kopyala.

### 6. Medya Varlıklarını İndir

```bash
python setup_assets.py
```

Bu betik `assets/` klasörüne ücretsiz müzik ve ses efektleri indirir.

---

## Kullanım

### Tekli Video Üretimi (Günlük)

```bash
# Tek video üret ve yükle
python main.py

# Yüklemeden test et
python main.py --dry-run

# Belirli bir konu zorla
python main.py --topic "Napoleon Waterloo'yu Kazansaydı"

# Türkçe içerik üret
LANGUAGE=tr python main.py
```

### Toplu Üretim (Haftalık)

```bash
# 7 video üret, kuyruğa ekle
python batch_producer.py

# Özel sayıda video üret
python batch_producer.py --count 3

# Sadece senaryo oluştur (video yok)
python batch_producer.py --dry-run
```

Toplu üretimde videolar `scheduled_queue.json` dosyasına eklenir ve `main.py` her çalıştığında sıradaki videoyu yayınlar.

### Analitik ve Raporlar

```bash
# Haftalık performans raporu
python analytics.py

# HTML performans panosu (tarayıcıda aç)
python performance_dashboard.py

# İzleyici tutma analizi
python retention_analyzer.py

# En iyi yükleme zamanları
python upload_time_optimizer.py
```

### Optimizasyon Araçları

```bash
# Başlıkları geçmiş performansa göre iyileştir
python title_optimizer.py

# Trend etiketleri öner
python hashtag_optimizer.py

# Konu havuzunu genişlet
python topic_expander.py

# Rakip kanal takibi
python competitor_tracker.py
```

### Çapraz Paylaşım

```bash
python poster_instagram.py  # Instagram'a paylaş
python poster_tiktok.py     # TikTok'a paylaş
python poster_twitter.py    # Twitter'a paylaş
python poster_facebook.py   # Facebook'a paylaş
```

---

## GitHub Actions ile Otomasyon

### Gizli Değişkenleri Ayarla

GitHub reposunda **Settings → Secrets and variables → Actions** bölümüne git ve şunları ekle:

```
GEMINI_API_KEY
PEXELS_API_KEY
YOUTUBE_TOKEN_JSON
TELEGRAM_BOT_TOKEN      (isteğe bağlı)
TELEGRAM_CHAT_ID        (isteğe bağlı)
DISCORD_WEBHOOK_URL     (isteğe bağlı)
INSTAGRAM_ACCESS_TOKEN  (isteğe bağlı)
INSTAGRAM_USER_ID       (isteğe bağlı)
TIKTOK_ACCESS_TOKEN     (isteğe bağlı)
TWITTER_API_KEY         (isteğe bağlı)
TWITTER_API_SECRET      (isteğe bağlı)
TWITTER_ACCESS_TOKEN    (isteğe bağlı)
TWITTER_ACCESS_TOKEN_SECRET (isteğe bağlı)
FACEBOOK_PAGE_ID        (isteğe bağlı)
FACEBOOK_ACCESS_TOKEN   (isteğe bağlı)
```

### Otomatik Zamanlamalar

| Workflow | Zamanlama | Görev |
|----------|-----------|-------|
| `daily.yml` | Her gün 09:00 UTC | Tek video üret ve yükle |
| `batch.yml` | Her Pazar 06:00 UTC | 7 video üret, kuyruğa ekle |
| `weekly_report.yml` | Her Pazartesi 08:00 UTC | Analitik rapor oluştur |
| `title_optimizer.yml` | Haftalık | Başlık optimizasyonu |
| `ab_test.yml` | Haftalık | Thumbnail A/B testi |
| `auto_reply.yml` | Günlük | Yorumlara otomatik yanıt |
| `tracker.yml` | Haftalık | Rakip kanal takibi |

### Manuel Tetikleme

GitHub'da **Actions** sekmesine git, istediğin workflow'u seç ve **Run workflow** düğmesine bas.

---

## Klasör Yapısı

```
war-shorts/
├── main.py                  # Ana orkestratör
├── script_gen.py            # Senaryo üretimi (Gemini)
├── tts.py                   # Sesli anlatım (Edge TTS)
├── video_builder.py         # Video derleme (MoviePy)
├── thumbnail.py             # Thumbnail üretimi
├── uploader.py              # YouTube yükleme
├── batch_producer.py        # Toplu üretim
├── analytics.py             # Performans analizi
├── setup_assets.py          # Varlık indirme
├── get_youtube_token.py     # YouTube OAuth2
├── requirements.txt         # Python bağımlılıkları
├── topic_pool.json          # Konu havuzu (50+ konu)
├── used_topics.json         # Kullanılmış konular
├── scheduled_queue.json     # Yayın kuyruğu
├── assets/
│   ├── fonts/               # Yazı tipleri
│   ├── music/               # Arka plan müziği
│   ├── sfx/                 # Ses efektleri
│   ├── logo.png             # Filigran
│   ├── intro.mp4            # 2 saniyelik açılış
│   └── outro.mp4            # 3 saniyelik kapanış
├── output/                  # Üretilen dosyalar (git'e dahil değil)
└── .github/workflows/       # GitHub Actions workflow'ları
```

---

## Dil Desteği

Varsayılan dil İngilizce'dir. Türkçe içerik için:

```bash
# Yerel çalıştırma
LANGUAGE=tr python main.py

# GitHub Actions
# Settings → Variables → New variable
# LANGUAGE = tr
```

---

## Sorun Giderme

**`ffmpeg: command not found` hatası**
```bash
sudo apt-get install ffmpeg  # Linux
brew install ffmpeg           # macOS
```

**`ImageMagick policy` hatası (Linux)**
```bash
sudo nano /etc/ImageMagick-6/policy.xml
# Şu satırı bul ve kaldır veya yorum satırı yap:
# <policy domain="path" rights="none" pattern="@*"/>
```

**YouTube token süresi doldu**
```bash
python get_youtube_token.py  # Token'ı yenile
```

**Pexels klip bulunamıyor**
- Konu çok spesifik olabilir; `topic_pool.json` dosyasında daha genel konular dene

**Gemini API hatası**
- Günlük 1500 istek limitini kontrol et
- API anahtarının aktif olduğunu doğrula

---

## Katkıda Bulunma

1. Depoyu fork'la
2. Yeni bir dal oluştur: `git checkout -b ozellik/yeni-ozellik`
3. Değişikliklerini kaydet: `git commit -m 'Yeni özellik ekle'`
4. Dalı gönder: `git push origin ozellik/yeni-ozellik`
5. Pull Request aç

---

## Lisans

MIT License — Özgürce kullan, değiştir ve dağıt.
