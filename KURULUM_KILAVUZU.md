# ⚔️ WAR SHORTS Pipeline — Kurulum ve Kullanım Kılavuzu

> Sıfırdan otomatik YouTube Shorts kanalı kurmak için adım adım rehber.
> Hiç kod bilgisi gerekmez. Tek yapman gereken kopyala-yapıştır.

---

## İçindekiler

1. [Bu Proje Ne Yapar?](#1-bu-proje-ne-yapar)
2. [Nasıl Çalışır?](#2-nasıl-çalışır)
3. [Nelere İhtiyacın Var?](#3-nelere-ihtiyacın-var)
4. [Adım 1 — GitHub Kurulumu](#adım-1--github-kurulumu)
5. [Adım 2 — Google Gemini API](#adım-2--google-gemini-api)
6. [Adım 3 — Pexels API](#adım-3--pexels-api)
7. [Adım 4 — YouTube OAuth Token](#adım-4--youtube-oauth-token)
8. [Adım 5 — Telegram Bot](#adım-5--telegram-bot)
9. [Adım 6 — Discord Webhook](#adım-6--discord-webhook)
10. [Adım 7 — Instagram (İsteğe Bağlı)](#adım-7--instagram-isteğe-bağlı)
11. [Adım 8 — TikTok (İsteğe Bağlı)](#adım-8--tiktok-isteğe-bağlı)
12. [Adım 9 — Twitter/X (İsteğe Bağlı)](#adım-9--twitterx-isteğe-bağlı)
13. [Adım 10 — Facebook (İsteğe Bağlı)](#adım-10--facebook-isteğe-bağlı)
14. [GitHub Secrets Ayarlama](#github-secrets-ayarlama)
15. [İlk Çalıştırma](#ilk-çalıştırma)
16. [Otomatik Zamanlama](#otomatik-zamanlama)
17. [Tüm Modüller](#tüm-modüller)
18. [Tüm Workflow'lar](#tüm-workflowlar)
19. [Sorun Giderme](#sorun-giderme)
20. [Sık Sorulan Sorular](#sık-sorulan-sorular)

---

## 1. Bu Proje Ne Yapar?

Her gün **tamamen otomatik olarak**:

- 🤖 Gemini AI ile savaş/tarih senaryosu yazar ("What if Rome never fell?")
- 🎙️ Metni sese çevirir (Edge TTS, ücretsiz)
- 🎬 Pexels'tan video klip indirir, altyazı ve efekt ekler
- 🖼️ Thumbnail oluşturur
- 📤 YouTube'a yükler, başlık/açıklama/tag ekler
- 📲 Instagram, TikTok, Twitter ve Facebook'a çapraz paylaşım yapar
- 📊 Her Pazartesi performans raporu gönderir
- 🔔 Her adımda Telegram ve Discord'a bildirim atar

**Tüm bunlar ücretsiz.** Tek ücretli servis isteğe bağlı Gemini API (aylık birkaç dolar).

---

## 2. Nasıl Çalışır?

```
Her gün saat 09:00 UTC (GitHub Actions Cron)
         │
         ▼
   topic_selector.py ──► topic_pool.json'dan trend konu seç
   rss_monitor.py    ──► RSS haberlerinden yeni konu ekle
   topic_expander.py ──► Konu azalırsa Gemini ile genişlet
         │
         ▼
   script_gen.py ──► Gemini AI ile 60 saniyelik script yaz
   script_scorer.py ──► Kalite skoru (100 üzerinden)
         │
         ▼
   tts.py ──► Edge TTS ile MP3 + VTT altyazı dosyası
         │
         ▼
   video_builder.py ──► Pexels klip + altyazı + müzik + efekt
   video_validator.py ──► Upload öncesi kalite kontrolü
         │
         ▼
   thumbnail.py ──► 1280×720 PNG kapak resmi
   ab_thumbnail.py ──► A/B test için 2 varyant
         │
         ▼
   uploader.py ──► YouTube'a yükle
         │
         ├── end_screen.py ──► Bitiş kartı ekle
         ├── captions_uploader.py ──► Resmi altyazı
         ├── subtitle_translator.py ──► ES/FR/PT çeviri
         ├── playlist_manager.py ──► Playlist'e ekle
         ├── hashtag_optimizer.py ──► SEO açıklama
         ├── community_post.py ──► Community tab
         ├── poster_instagram.py ──► Instagram Reels
         ├── poster_tiktok.py ──► TikTok
         ├── poster_twitter.py ──► Tweet
         ├── poster_facebook.py ──► Facebook Reels
         └── notifier.py + discord_notify.py ──► Bildirimler
```

---

## 3. Nelere İhtiyacın Var?

### Zorunlu (Ücretsiz)
| Servis | Ne için | Link |
|--------|---------|------|
| GitHub hesabı | Kodu barındırma + otomasyon | github.com |
| Google hesabı | YouTube API + Gemini | google.com |
| Pexels hesabı | Video klip indirme | pexels.com/api |
| Telegram hesabı | Bildirim almak | telegram.org |

### İsteğe Bağlı (Ücretsiz)
| Servis | Ne için |
|--------|---------|
| Discord sunucusu | Discord bildirimleri |
| Instagram hesabı (Business) | Reels çapraz paylaşım |
| TikTok Developer hesabı | TikTok çapraz paylaşım |
| Twitter Developer hesabı | Tweet atma |
| Facebook Sayfası | Facebook Reels |

### Bilgisayarda Kurulu Olması Gerekenler
- Git (git-scm.com)
- Python 3.11+ (python.org) — Yalnızca token alma işlemi için

---

## Adım 1 — GitHub Kurulumu

### 1.1 Repo'yu Fork Et

1. Bu reponun GitHub sayfasına git
2. Sağ üstteki **Fork** butonuna tıkla
3. **"Create fork"** de
4. Artık kendi hesabında `Shorts` adında bir repo var

### 1.2 Repo'yu Bilgisayarına Çek

Terminal aç ve şunu yaz:
```bash
git clone https://github.com/KULLANICI_ADIN/Shorts.git
cd Shorts
```

### 1.3 GitHub Actions'ı Aktif Et

1. Repo sayfanda **Actions** sekmesine tıkla
2. **"I understand my workflows, go ahead and enable them"** butonuna tıkla

---

## Adım 2 — Google Gemini API

Script üretimi için kullanılır. **Ücretsiz tier günde 1500 istek** destekler.

1. **aistudio.google.com** adresine git
2. Sol menüden **"Get API key"** tıkla
3. **"Create API key"** → proje seç → **"Create API key in new project"**
4. Çıkan uzun anahtarı kopyala ve bir yere kaydet

> 💡 Bu anahtar şuna benzer: `AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXX`

---

## Adım 3 — Pexels API

Ücretsiz stok video indirmek için kullanılır.

1. **pexels.com** adresine git, hesap oluştur
2. **pexels.com/api** adresine git
3. **"Your API Key"** bölümünde anahtarın görünür
4. Kopyala ve kaydet

---

## Adım 4 — YouTube OAuth Token

Bu en önemli ve en uzun adım. Bir kez yapılır.

### 4.1 Google Cloud Console'da Proje Oluştur

1. **console.cloud.google.com** adresine git
2. Üstteki proje seçiciden **"New Project"** tıkla
3. Proje adı: `war-shorts` → **"Create"**

### 4.2 YouTube API'lerini Aktif Et

1. Sol menü → **"APIs & Services"** → **"Library"**
2. Şunları arayıp etkinleştir (**"Enable"** butonu):
   - `YouTube Data API v3`
   - `YouTube Analytics API`
   - `Google Drive API` (Drive yedek istiyorsan)

### 4.3 OAuth İzin Ekranı

1. **"APIs & Services"** → **"OAuth consent screen"**
2. **"External"** seç → **"Create"**
3. App name: `WAR SHORTS`
4. Support email: kendi emailin
5. **"Save and Continue"** × 3 kez
6. Son ekranda **"Back to Dashboard"**

### 4.4 OAuth Credentials Oluştur

1. **"APIs & Services"** → **"Credentials"**
2. **"+ Create Credentials"** → **"OAuth client ID"**
3. Application type: **"Desktop app"**
4. Name: `war-shorts-desktop`
5. **"Create"**
6. Çıkan ekranda **"Download JSON"** tıkla
7. İndirilen dosyayı `client_secret.json` olarak kaydet
8. Bu dosyayı Shorts klasörüne koy

### 4.5 Token Al

Terminal'de Shorts klasöründeyken:
```bash
pip install google-auth-oauthlib google-api-python-client
python get_youtube_token.py
```

Tarayıcı otomatik açılacak:
1. Google hesabınla giriş yap
2. **"WAR SHORTS uygulamasına izin ver"** ekranında **"Continue"** tıkla
3. Tüm izinleri onayla

Terminal'de şunu göreceksin:
```
Token kaydedildi: token.json
```

### 4.6 Token'ı Secret'a Çevir

```bash
cat token.json
```

Çıkan JSON içeriğini kopyala. Bunu GitHub Secret olarak kaydedeceğiz (aşağıdaki bölümde).

---

## Adım 5 — Telegram Bot

Pipeline hataları ve başarı bildirimleri için.

### 5.1 Bot Oluştur

1. Telegram'da **@BotFather**'a mesaj at
2. `/newbot` yaz
3. Bot adı: `WAR SHORTS Bot`
4. Kullanıcı adı: `warshorts_SENIN_ADIN_bot`
5. BotFather sana şuna benzer bir token verecek:
   ```
   7123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   Bunu kaydet → `TELEGRAM_BOT_TOKEN`

### 5.2 Chat ID Al

**Yöntem 1 — Kanaldan:**
1. Telegram'da bir kanal oluştur
2. Botu kanala admin olarak ekle
3. **@userinfobot**'a kanalın kullanıcı adını at, Chat ID verecek

**Yöntem 2 — Kendin için:**
1. Bota bir mesaj at
2. Tarayıcıda şu adresi aç:
   ```
   https://api.telegram.org/botTOKENIN/getUpdates
   ```
   `TOKENIN` yerine botun tokenini yaz
3. Çıkan JSON'da `"chat":{"id":123456789}` kısmındaki sayı senin Chat ID'n

---

## Adım 6 — Discord Webhook

Discord bildirimleri için. **İsteğe bağlı.**

1. Discord sunucunda bir kanal oluştur (örn: `#war-shorts-bot`)
2. Kanalın üzerine sağ tıkla → **"Edit Channel"**
3. **"Integrations"** → **"Webhooks"** → **"New Webhook"**
4. İsim ver, **"Copy Webhook URL"** tıkla
5. URL'yi kaydet → `DISCORD_WEBHOOK_URL`

---

## Adım 7 — Instagram (İsteğe Bağlı)

Instagram Reels çapraz paylaşımı için.

**Gereksinimler:**
- Instagram Business veya Creator hesabı
- Facebook Sayfasına bağlı olmalı

### 7.1 Facebook Developer Hesabı

1. **developers.facebook.com** → **"My Apps"** → **"Create App"**
2. Tür: **"Business"**
3. App adı: `WAR SHORTS`

### 7.2 Instagram Basic Display API Ekle

1. App Dashboard'da **"Add Product"** → **Instagram Graph API**
2. **"Settings"** → **"Basic"** → `App ID` ve `App Secret`'ı kaydet

### 7.3 Access Token Al

1. **Graph API Explorer** → `graph.facebook.com/explorer`
2. Uygulaman seç
3. İzinler: `instagram_basic`, `instagram_content_publish`
4. **"Generate Access Token"**
5. Token'ı kaydet → `INSTAGRAM_ACCESS_TOKEN`

### 7.4 User ID Al

```
https://graph.facebook.com/me?fields=id&access_token=TOKENIN
```
Dönen `id` değeri → `INSTAGRAM_USER_ID`

---

## Adım 8 — TikTok (İsteğe Bağlı)

1. **developers.tiktok.com** → Hesap oluştur
2. **"My Apps"** → **"Create app"**
3. Tür: **"Web"**
4. **Content Posting API** ürünü ekle
5. OAuth flow ile `tiktok_video.publish` izni al
6. Access Token → `TIKTOK_ACCESS_TOKEN`

---

## Adım 9 — Twitter/X (İsteğe Bağlı)

1. **developer.twitter.com** → **"Sign up"**
2. **"Free"** planı seç (1500 tweet/ay yeterli)
3. Proje ve App oluştur
4. **"Keys and Tokens"** sekmesinden şunları al:
   - API Key → `TWITTER_API_KEY`
   - API Key Secret → `TWITTER_API_SECRET`
   - Access Token → `TWITTER_ACCESS_TOKEN`
   - Access Token Secret → `TWITTER_ACCESS_TOKEN_SECRET`

---

## Adım 10 — Facebook (İsteğe Bağlı)

1. Facebook Sayfası oluştur (yoksa)
2. **developers.facebook.com** → Uygulaman → **Graph API Explorer**
3. İzinler: `pages_manage_posts`, `publish_video`
4. Sayfan için **Page Access Token** al → `FACEBOOK_ACCESS_TOKEN`
5. Sayfanın ID'si → `FACEBOOK_PAGE_ID`
   - Sayfanın URL'sinde yazar: `facebook.com/pages/SAYFAADIN/123456789` → `123456789`

---

## GitHub Secrets Ayarlama

Tüm anahtarları GitHub repo'na "Secret" olarak ekliyoruz.
Secrets şifreli saklanır, hiç kimse göremez.

### Nasıl Eklenir?

1. GitHub repo sayfana git
2. **Settings** → **Secrets and variables** → **Actions**
3. **"New repository secret"** tıkla
4. Name ve Value gir → **"Add secret"**

### Zorunlu Secrets

| Secret Adı | Değer | Nereden Alındı |
|------------|-------|----------------|
| `GEMINI_API_KEY` | `AIzaSy...` | aistudio.google.com |
| `PEXELS_API_KEY` | `xxxxx...` | pexels.com/api |
| `YOUTUBE_TOKEN_JSON` | `token.json` dosyasının **tüm içeriği** | Adım 4.6 |
| `TELEGRAM_BOT_TOKEN` | `7123456:AAE...` | BotFather |
| `TELEGRAM_CHAT_ID` | `-100123456789` veya `123456789` | Adım 5.2 |

### İsteğe Bağlı Secrets

| Secret Adı | Açıklama |
|------------|---------|
| `DISCORD_WEBHOOK_URL` | Discord bildirim URL'si |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram token |
| `INSTAGRAM_USER_ID` | Instagram kullanıcı ID'si |
| `TIKTOK_ACCESS_TOKEN` | TikTok token |
| `TWITTER_API_KEY` | Twitter API key |
| `TWITTER_API_SECRET` | Twitter API secret |
| `TWITTER_ACCESS_TOKEN` | Twitter access token |
| `TWITTER_ACCESS_TOKEN_SECRET` | Twitter access token secret |
| `FACEBOOK_PAGE_ID` | Facebook sayfa ID |
| `FACEBOOK_ACCESS_TOKEN` | Facebook page token |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive yedek klasör ID'si |

### Variables (Secrets Değil)

**Settings** → **Secrets and variables** → **Actions** → **Variables** sekmesi:

| Variable Adı | Varsayılan | Açıklama |
|-------------|-----------|---------|
| `LANGUAGE` | `en` | `en` veya `tr` — video dili |
| `USE_QUEUE` | `false` | `true` = haftalık batch kuyruğunu kullan |
| `GOOGLE_DRIVE_BACKUP` | `false` | `true` = Drive'a yedekle |
| `TRANSLATE_LANGUAGES` | `es,fr,pt` | Altyazı çeviri dilleri |
| `COMPETITOR_CHANNEL_IDS` | boş | İzlenecek rakip kanal ID'leri (virgülle) |

---

## İlk Çalıştırma

### Test (Dry Run) — Upload Yapmadan

Repo Actions sekmesinde:
1. **WAR SHORTS — Daily Pipeline** workflow'unu tıkla
2. **"Run workflow"** → dropdown aç
3. `--dry-run` checkboxını işaretle
4. **"Run workflow"** tıkla

Log ekranında şunları görmeni bekliyoruz:
```
✅  DRY RUN TAMAMLANDI (upload atlandı)
   Script    → output/script.json
   Ses       → output/narration.mp3
   Video     → output/short.mp4
   Thumbnail → output/thumbnail.png
```

Hata yoksa gerçek çalıştırmaya geçebilirsin.

### Gerçek İlk Çalıştırma

1. **WAR SHORTS — Daily Pipeline** → **"Run workflow"**
2. Dry run işaretleme, direkt **"Run workflow"**
3. ~10-15 dakika sürer
4. Tamamlanınca Telegram'dan bildirim gelir:
   ```
   ✅ Yeni Short YAYINDA!
   https://youtube.com/shorts/VIDEO_ID
   ```

---

## Otomatik Zamanlama

Hiçbir şey yapmana gerek yok — GitHub Actions her gün otomatik çalışır.

### Varsayılan Program

| Workflow | Zaman (UTC) | Ne Yapar |
|---------|-------------|----------|
| Daily Pipeline | Her gün 09:00 | Video üret + yükle |
| Title Optimizer | Her gün 09:15 | 24 saat sonra başlık A/B testi |
| A/B Thumbnail | Her gün 11:00 | Thumbnail CTR karşılaştırması |
| Competitor Tracker | Pazartesi 07:00 | Rakip kanal analizi |
| Weekly Report | Pazartesi 08:00 | Analytics raporu + dashboard |
| Batch Producer | Pazar 06:00 | Haftanın 7 videosunu önceden üret |
| Auto Reply | Her gün 12:00 ve 18:00 | Yorumlara otomatik yanıt |

### Saat Değiştirmek

Repo'da `.github/workflows/daily.yml` dosyasını aç:
```yaml
on:
  schedule:
    - cron: '0 9 * * *'   # ← Bunu değiştir
```

Cron formatı: `dakika saat gün ay haftanın_günü`
Örnek: Her gün 12:00 UTC → `0 12 * * *`

> 🌍 UTC saatini yerel saatine çevirmek için: `utctime.net`

---

## Tüm Modüller

Projede 36 Python modülü bulunur:

### Çekirdek Pipeline

| Dosya | Görev |
|-------|-------|
| `main.py` | Tüm adımları sırayla çalıştıran ana orkestratör |
| `script_gen.py` | Gemini AI ile 60 saniyelik script üretimi |
| `tts.py` | Edge TTS ile MP3 ses + VTT altyazı dosyası |
| `video_builder.py` | Pexels klip + altyazı + müzik + efekt + montaj |
| `thumbnail.py` | 1280×720 kapak resmi |
| `uploader.py` | YouTube'a OAuth2 ile yükleme |

### Konu Yönetimi

| Dosya | Görev |
|-------|-------|
| `topic_selector.py` | Google Trends ile en popüler konuyu seç |
| `topic_expander.py` | Konu havuzu azalınca Gemini ile genişlet |
| `rss_monitor.py` | BBC/WorldHistory/Wikipedia RSS beslemelerinden konu çek |
| `competitor_tracker.py` | Rakip kanalları tara, viral konuları tespit et |

### Optimizasyon

| Dosya | Görev |
|-------|-------|
| `script_scorer.py` | Script kalite skoru (100 üzerinden) |
| `title_optimizer.py` | 24 saat sonra düşük performanslı başlığı değiştir |
| `ab_thumbnail.py` | A ve B thumbnail varyantı üret, CTR karşılaştır |
| `hashtag_optimizer.py` | Trend hashtag araştırması + SEO açıklama |
| `retention_analyzer.py` | İzleyici bırakma noktalarını analiz et |
| `upload_time_optimizer.py` | En iyi yükleme saatini bul |
| `video_validator.py` | Upload öncesi kalite kontrolü |

### Dağıtım (Cross-posting)

| Dosya | Görev |
|-------|-------|
| `poster_instagram.py` | Instagram Reels |
| `poster_tiktok.py` | TikTok |
| `poster_twitter.py` | Twitter/X tweet |
| `poster_facebook.py` | Facebook Reels |

### YouTube Özellikler

| Dosya | Görev |
|-------|-------|
| `end_screen.py` | Bitiş kartı (abone butonu + son video) |
| `captions_uploader.py` | Resmi YouTube altyazısı yükleme (SEO) |
| `subtitle_translator.py` | İspanyolca/Fransızca/Portekizce altyazı çevirisi |
| `playlist_manager.py` | Otomatik tematik playlist yönetimi |
| `community_post.py` | YouTube Community sekmesi duyurusu |
| `auto_reply.py` | Yorumlara Gemini ile otomatik yanıt |

### Raporlama ve Yedek

| Dosya | Görev |
|-------|-------|
| `analytics.py` | Haftalık YouTube Analytics raporu |
| `performance_dashboard.py` | HTML analytics dashboard |
| `notifier.py` | Telegram bildirimleri |
| `discord_notify.py` | Discord bildirimleri |
| `drive_backup.py` | Google Drive yedekleme |

### Toplu Üretim

| Dosya | Görev |
|-------|-------|
| `batch_producer.py` | Haftanın 7 videosunu Pazar günü önceden üret |
| `weekly_compilation.py` | 7 videoyu tek uzun videoya derle + yükle |

### Kurulum Yardımcıları

| Dosya | Görev |
|-------|-------|
| `get_youtube_token.py` | Tek seferlik YouTube OAuth token alma |
| `setup_assets.py` | SFX ve müzik dosyalarını otomatik indir |

---

## Tüm Workflow'lar

| Dosya | Çalışma Zamanı | Tetikleyici |
|-------|---------------|------------|
| `daily.yml` | Her gün 09:00 UTC | Otomatik + Manuel |
| `batch.yml` | Pazar 06:00 UTC | Otomatik + Manuel |
| `weekly_report.yml` | Pazartesi 08:00 UTC | Otomatik + Manuel |
| `title_optimizer.yml` | Her gün 09:15 UTC | Otomatik + Manuel |
| `ab_test.yml` | Her gün 11:00 UTC | Otomatik + Manuel |
| `tracker.yml` | Pazartesi 07:00 UTC | Otomatik + Manuel |
| `auto_reply.yml` | Her gün 12:00 + 18:00 UTC | Otomatik + Manuel |

---

## Sorun Giderme

### ❌ "GEMINI_API_KEY bulunamadı"
→ GitHub Secrets'ta `GEMINI_API_KEY`'i ekledin mi kontrol et.
→ Secret adında büyük/küçük harf farkına dikkat et.

### ❌ "YouTube token bulunamadı"
→ `YOUTUBE_TOKEN_JSON` secret'ına `token.json` dosyasının **tüm içeriğini** yapıştırdın mı?
→ JSON formatı bozuk olabilir. `token.json` içeriğini `jsonlint.com`'da doğrula.
→ Token süresi dolmuş olabilir. `get_youtube_token.py`'yi tekrar çalıştır.

### ❌ Video yüklendi ama thumbnail yok
→ YouTube'un thumbnail işlemesi birkaç dakika sürebilir.
→ Thumbnail boyutu 2 MB'dan büyük olabilir — `video_validator.py` kontrol eder.

### ❌ Instagram/TikTok atlandı
→ Bu platformlar isteğe bağlı. Secrets eksikse otomatik atlanır, hata değil.
→ Log'da `"INSTAGRAM_ACCESS_TOKEN yok, Instagram atlandı"` görüyorsan normal.

### ❌ "Video çok kısa" veya "Video çok uzun" hatası
→ TTS sesin ürettiği ses 60 saniyeden uzun olabilir.
→ `script_gen.py`'deki max_tokens değerini düşür veya
→ `tts.py`'deki hız parametresini artır: `rate="+10%"`

### ❌ Pexels'tan klip indirilemiyor
→ `PEXELS_API_KEY` doğru mu?
→ Pexels ücretsiz API'si günde 200 video izin verir. Limitini aştın olabilir.

### ❌ Script skoru çok düşük (< 60)
→ Pipeline yine de devam eder, sadece uyarı verir.
→ `topic_pool.json`'a daha özgün ve ilgi çekici konular ekle.

### ❌ GitHub Actions "Permission denied"
→ **Settings** → **Actions** → **General** → **Workflow permissions**
→ **"Read and write permissions"** seç → **Save**

### Logları Nasıl Okursun?

1. GitHub → **Actions** sekmesi
2. Hatalı çalışmayı tıkla (kırmızı X)
3. **"run-pipeline"** job'ına tıkla
4. Hangi adımda durduğunu gör (kırmızı adım)
5. Adımı genişlet, hata mesajını oku

---

## Sık Sorulan Sorular

**S: Bu pipeline aylık ne kadar maliyeti var?**
C: Sıfır. Gemini 1.5 Flash'ın ücretsiz tieri günlük 1 video için fazlasıyla yeterli (1500 istek/gün limit). GitHub Actions ücretsiz hesapla aylık 2000 dakika sunar, tüm workflow'lar ~500 dakika kullanır.

**S: YouTube'da kanalı sıfırdan mı açmam gerekiyor?**
C: Evet. Mevcut bir kanalin varsa onu da kullanabilirsin. OAuth token alırken o hesapla giriş yap.

**S: Video dili İngilizce mi olmalı?**
C: Hayır. `LANGUAGE` variable'ını `tr` yaparak Türkçe video da üretebilirsin. Pipeline otomatik olarak Türkçe TTS sesini (`tr-TR-AhmetNeural`) kullanır.

**S: Günde birden fazla video yükleyebilir miyim?**
C: Evet. `daily.yml`'e birden fazla cron satırı ekleyebilirsin:
```yaml
- cron: '0 9 * * *'
- cron: '0 15 * * *'
```

**S: Kendi konularımı ekleyebilir miyim?**
C: Evet. `topic_pool.json` dosyasını düzenle, yeni "What if..." soruları ekle. Pipeline bunları otomatik seçer.

**S: Video başlığını kendim yazabilir miyim?**
C: Manuel çalıştırırken `--topic` parametresi verirsin:
```
GitHub Actions → Run workflow → Topic alanına yaz → Çalıştır
```

**S: Batch modu ne işe yarar?**
C: Pazar günü 7 video önceden üretilir, her gün birer biri otomatik yayınlanır. Böylece pipeline hata alsa bile yedekte hazır video olur. `USE_QUEUE=true` yaparak aktif edilir.

**S: YouTube Analytics verilerine erişmek için ne gerekiyor?**
C: Aynı OAuth token yeterli. `analytics.py` her Pazartesi otomatik rapor gönderir.

**S: A/B thumbnail testi nasıl çalışıyor?**
C: Upload sonrası iki farklı thumbnail üretilir (A: kırmızı, B: mavi). 24 saat A gösterilir, 26. saatte B'ye geçilir. 48. saatte CTR karşılaştırılır, kazanan kalır.

**S: Competitor tracker hangi kanalları takip ediyor?**
C: `COMPETITOR_CHANNEL_IDS` variable'ına YouTube kanal ID'lerini virgülle ekle. Kanal ID'sini bulmak için: kanalın **About** sekmesi → **Share** → **Copy channel ID**.

---

## Tebrikler! 🎉

Pipeline tamamen kuruluysa her sabah uyandığında yeni bir video yayında olacak.
Herhangi bir sorun yaşarsan GitHub Issues'dan bildirebilirsin.

---

*Oluşturulma tarihi: 2026-03-16 — WAR SHORTS Pipeline v2.0*
