"""
main.py — WAR SHORTS pipeline orkestratörü.

Kullanım:
  python main.py                    # Normal çalıştırma
  python main.py --dry-run          # Upload olmadan test
  python main.py --topic "..."      # Belirli konu ile çalıştır

Yeni özellikler (v2):
  - Akıllı script yeniden üretimi (düşük puanlı scriptler otomatik iyileştirilir)
  - Viral trend tahmincisi (veri odaklı konu seçimi)
  - Etkileşim güçlendirici (akıllı pinned yorumlar, anketler)
  - İçerik serisi yönetimi (çok bölümlü videolar)
  - A/B başlık üretici (her video için en iyi başlık seçimi)
  - Duygu analizi (izleyici yorumlarından içerik stratejisi)
  - Akıllı zamanlama (en uygun yayın saati hesabı)
"""

import argparse
import json
import os
import sys
import traceback
from datetime import date  # noqa: F401 (used by topic_selector)

from script_gen import save_script
from tts import generate_audio
from video_builder import build_video
from thumbnail import generate_thumbnail
from uploader import upload_video, build_description, post_pinned_comment
from notifier import send_notification, send_error_notification
from topic_selector import pick_trending_topic
from poster_instagram import post_reel, build_caption as ig_caption
from poster_tiktok import post_video as tiktok_post, build_title as tt_title
from drive_backup import backup_to_drive
from batch_producer import get_next_queued, mark_published
from discord_notify import send_video_live as discord_video_live, send_error as discord_error
from end_screen import add_end_screen
from hashtag_optimizer import optimize_video_hashtags
from ab_thumbnail import generate_thumbnails as ab_generate, save_ab_state
from captions_uploader import upload_captions
from playlist_manager import add_to_playlist
from poster_twitter import post_tweet as twitter_post
from community_post import post_community_update
from video_validator import validate_or_raise
from subtitle_translator import translate_and_upload_captions
from auto_reply import reply_to_comments
from topic_expander import expand_if_low
from rss_monitor import monitor_and_update as rss_update
from poster_facebook import post_reel as facebook_post

# ─── Yeni v2 modülleri ──────────────────────────────────────────────────────
from smart_regenerator import smart_generate
from trend_predictor import predict_viral_score
from engagement_booster import generate_engagement_pack
from series_manager import (
    has_series_potential, detect_and_plan_series, start_series,
    get_active_series, get_series_topic_override, advance_series,
    enrich_script_with_series, get_series_cta,
)
from ab_title_generator import pick_best_title
from sentiment_analyzer import load_content_suggestions
from smart_scheduler import should_upload_now


OUTPUT_DIR = "output"
USED_TOPICS_PATH = "used_topics.json"
LAST_VIDEO_PATH = os.path.join(OUTPUT_DIR, "last_video.json")

# Dil ayarı: "en" veya "tr"
LANGUAGE = os.environ.get("LANGUAGE", "en")
# Kuyruk modu: True ise batch_producer kuyruğundan yayınlar
USE_QUEUE = os.environ.get("USE_QUEUE", "false").lower() == "true"

# Adım adları — hata bildirimlerinde kullanılır
STEP_NAMES = {
    "script":      "Script üretimi (Gemini)",
    "tts":         "Ses üretimi (Edge TTS)",
    "video":       "Video montajı (MoviePy)",
    "thumbnail":   "Thumbnail (Pillow)",
    "validate":    "Kalite kontrolü",
    "upload":      "YouTube upload",
    "notify":      "Telegram bildirimi",
    "trend":       "Viral trend analizi",
    "engagement":  "Etkileşim paketi üretimi",
    "series":      "Seri yönetimi",
    "ab_title":    "A/B başlık üretimi",
    "sentiment":   "Duygu analizi",
}


def save_used(used_data: dict) -> None:
    with open(USED_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(used_data, f, indent=2, ensure_ascii=False)


def cleanup_outputs() -> None:
    for fname in ["script.json", "narration.mp3", "narration.vtt", "short.mp4", "thumbnail.png"]:
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path):
            os.remove(path)


def save_last_video(video_id: str, script: dict) -> None:
    """title_optimizer.py için video bilgisini kaydeder."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(LAST_VIDEO_PATH, "w") as f:
        json.dump({
            "video_id": video_id,
            "title": script["title"],
            "hook": script["hook"],
        }, f, indent=2)
    print(f"[main] last_video.json kaydedildi: {video_id}")


def _step(name: str, fn, topic: str = ""):
    """
    Bir pipeline adımını çalıştırır.
    Hata olursa Telegram'a bildirir ve hatayı yeniden fırlatır.
    """
    try:
        return fn()
    except Exception as e:
        label = STEP_NAMES.get(name, name)
        print(f"\n[main] ❌ HATA — {label}: {e}", file=sys.stderr)
        traceback.print_exc()
        send_error_notification(label, e, topic)
        try:
            discord_error(label, str(e), topic)
        except Exception:
            pass
        raise


def run(dry_run: bool = False, topic_override: str = None) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_outputs()

    print("=" * 52)
    print("⚔️   WAR SHORTS v2 — Pipeline Başlatıldı")
    print("=" * 52)

    # 0) Akıllı zamanlama kontrolü
    if not dry_run and not topic_override:
        if should_upload_now():
            print("[main] ✅ Yayın zamanı uygun — devam ediliyor.")
        else:
            print("[main] ⏰ Yayın zamanı optimal değil — yine de devam ediliyor.")

    # Güncel savaş/jeopolitik haberlerinden konu üret
    print("\n[main] RSS haberleri taranıyor...")
    try:
        rss_result = rss_update(max_topics=8)
        added = rss_result.get("topics_added", 0)
        if added:
            print(f"[main] {added} güncel analiz konusu eklendi")
        if added > 0:
            print(f"[main] {added} yeni konu havuza eklendi, topic_selector'a bırakılıyor.")
    except Exception as e:
        print(f"[main] RSS tarama hatası (kritik değil): {e}")

    # Pool düşükse Gemini ile otomatik genişlet
    expand_if_low()

    # İzleyici duygu analizinden içerik önerileri al
    try:
        suggestions = load_content_suggestions()
        if suggestions and not topic_override:
            print(f"[main] 💡 İzleyici talepleri: {', '.join(suggestions[:3])}")
    except Exception:
        pass

    # Kuyruk modu: batch_producer'dan önceden üretilmiş video kullan
    queued = get_next_queued() if USE_QUEUE and not topic_override else None

    if queued:
        print(f"\n[main] Kuyruk modu — video: {queued['scheduled_date']}")
        topic = queued["topic"]
        with open(queued["script_path"], encoding="utf-8") as f:
            script = json.load(f)
        audio_path = queued["audio_path"]
        vtt_path = audio_path.replace(".mp3", ".vtt") if audio_path else None
        video_path = queued["video_path"]
        thumb_path = queued["thumbnail_path"]

        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(audio_path)
        duration_sec = clip.duration
        clip.close()
    else:
        # 0) Aktif seri varsa, sıradaki bölümü override olarak kullan
        if not topic_override:
            series_topic = get_series_topic_override()
            if series_topic:
                topic_override = series_topic
                print(f"[main] 📺 Seri modu — {series_topic[:60]}...")

        # 1) Trending konu seç
        topic, used_data = pick_trending_topic(topic_override)
        save_used(used_data)

        # [NEWS] prefix varsa kaldır
        if topic.startswith("[NEWS] "):
            topic = topic[7:]
            print(f"\n[main] Konu (GÜNCEL HABER): {topic}")
        else:
            print(f"\n[main] Konu: {topic}")

        # 1b) Viral trend skoru hesapla
        print("\n[main] Viral trend skoru hesaplanıyor...")
        try:
            viral_score = predict_viral_score(topic)
            print(f"[main] 📊 Viral skor: {viral_score.total}/100 ({viral_score.tier})")
            for reason in viral_score.reasons[:3]:
                print(f"[main]   {reason}")
        except Exception as e:
            print(f"[main] Trend tahmini hatası (kritik değil): {e}")

        # 1c) Seri sistemi devre dışı — başlıklara "Part X/Y" eklenmesini önler
        # active_series = get_active_series()
        # if not active_series and has_series_potential(topic): ...

        # 2) Script — akıllı yeniden üretim ile (düşük puanlı scriptler otomatik iyileştirilir)
        print(f"\n[main] Script üretiliyor (akıllı mod, dil: {LANGUAGE})...")
        script, score_bd = _step("script", lambda: smart_generate(topic, LANGUAGE), topic)
        save_script(script)
        print(f"[main] Başlık: {script['title']} (skor: {score_bd.total}/100)")

        # 2b) Seri enrichment devre dışı — "Part X/Y" başlık eklenmez

        # 2c) A/B başlık optimizasyonu — en iyi başlığı seç
        print("\n[main] A/B başlık varyantları üretiliyor...")
        try:
            best_title = pick_best_title(script)
            save_script(script)  # güncellenmiş başlıkla kaydet
        except Exception as e:
            print(f"[main] A/B başlık üretilemedi (kritik değil): {e}")

        # 3) TTS + VTT
        print("\n[main] Ses üretiliyor...")
        tts_voice = script.get("tts_voice")
        audio_path, vtt_path = _step(
            "tts",
            lambda: generate_audio(
                script.get("hook", "") + " ... " + script["narration"],
                voice=tts_voice,
            ),
            topic,
        )

        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(audio_path)
        duration_sec = clip.duration
        clip.close()

        # 4) Video
        print("\n[main] Video üretiliyor (3 klip + CTA + crossfade)...")
        video_path = _step("video", lambda: build_video(script, audio_path, vtt_path), topic)

        # 5) Thumbnail
        print("\n[main] Thumbnail üretiliyor...")
        thumb_path = _step(
            "thumbnail",
            lambda: generate_thumbnail(script["title"], script["thumbnail_text"]),
            topic,
        )

    # 5b) Kalite kontrolü (upload öncesi)
    print("\n[main] Kalite kontrolü yapılıyor...")
    _step(
        "validate",
        lambda: validate_or_raise(video_path, thumb_path, script, vtt_path),
        topic,
    )

    if dry_run:  # noqa — shared between queue and fresh modes
        print("\n" + "=" * 52)
        print("✅  DRY RUN TAMAMLANDI (upload atlandı)")
        print(f"   Script    → {OUTPUT_DIR}/script.json")
        print(f"   Ses       → {audio_path}")
        print(f"   Video     → {video_path}")
        print(f"   Thumbnail → {thumb_path}")
        print("=" * 52)
        return

    # Upload tag'ları: script tags (Gemini) + sabit base tags
    # NOT: search_keywords tag olarak kullanılmaz — footage sorguları, tag değil
    _base_tags = ["Shorts", "Military", "Breaking News", "Geopolitics", "War News", "Military News"]
    upload_tags = list(dict.fromkeys(script["tags"] + _base_tags))  # dedup, boşluklar korunur

    # 6) YouTube upload
    print("\n[main] YouTube'a yükleniyor...")
    video_id = _step(
        "upload",
        lambda: upload_video(
            video_path=video_path,
            title=script["title"],
            description=build_description(script),
            tags=upload_tags,
            thumbnail_path=thumb_path,
        ),
        topic,
    )

    # 7) Video bilgisini kaydet + kuyruk güncelle
    save_last_video(video_id, script)
    if queued:
        mark_published(queued["scheduled_date"])
        print(f"[main] Kuyruk güncellendi: {queued['scheduled_date']} → yayınlandı")

    # 7b) End screen ekle
    print("\n[main] End screen ekleniyor...")
    add_end_screen(video_id, duration_sec)

    # 7c) Hashtag optimizasyonu
    print("\n[main] Hashtag optimizasyonu yapılıyor...")
    try:
        optimize_video_hashtags(video_id, script)
    except Exception as e:
        print(f"[main] Hashtag optimizasyonu başarısız (kritik değil): {e}")

    # 7d) A/B thumbnail üret ve state kaydet
    print("\n[main] A/B thumbnail varyantları üretiliyor...")
    try:
        a_path, b_path = ab_generate(script["thumbnail_text"], script["title"])
        save_ab_state(video_id, a_path, b_path)
        print(f"[main] A/B thumbnails hazır → ab_test.yml 24 saat sonra karşılaştıracak")
    except Exception as e:
        print(f"[main] A/B thumbnail üretilemedi (kritik değil): {e}")

    # 7e) Resmi YouTube altyazısı yükle (SEO) + çok dilli çeviri
    print("\n[main] Altyazı (caption) yükleniyor...")
    try:
        upload_captions(video_id, vtt_path, language=script.get("language", "en"))
    except Exception as e:
        print(f"[main] Altyazı yüklenemedi (kritik değil): {e}")

    print("\n[main] Çok dilli altyazı çevriliyor...")
    try:
        translate_and_upload_captions(
            video_id, vtt_path,
            source_language=script.get("language", "en"),
        )
    except Exception as e:
        print(f"[main] Altyazı çevirisi başarısız (kritik değil): {e}")

    # 7f) Playlist'e ekle
    print("\n[main] Playlist'e ekleniyor...")
    try:
        add_to_playlist(video_id, script)
    except Exception as e:
        print(f"[main] Playlist eklenemedi (kritik değil): {e}")

    # 8) Etkileşim paketi üret ve uygula (akıllı pinned yorum + anket + tartışma)
    print("\n[main] Etkileşim paketi üretiliyor...")
    engagement_pack = None
    try:
        engagement_pack = generate_engagement_pack(script)
    except Exception as e:
        print(f"[main] Etkileşim paketi üretilemedi (kritik değil): {e}")

    # 8a) Akıllı pinned yorum gönder
    print("\n[main] Akıllı pinned yorum gönderiliyor...")
    try:
        from uploader import _get_credentials
        from googleapiclient.discovery import build as yt_build
        creds = _get_credentials()
        yt = yt_build("youtube", "v3", credentials=creds)

        # Seri CTA devre dışı — engagement pack veya default kullan
        if False and False:  # seri sistemi kapalı
            pinned_text = ""
        elif engagement_pack:
            pinned_text = engagement_pack["pinned_comment"]
        else:
            pinned_text = "What do you think happens next? 👇 Drop your prediction below!"

        post_pinned_comment(yt, video_id, pinned_text)
    except Exception as e:
        print(f"[main] Yorum gönderilemedi (kritik değil): {e}")

    # 8b) Community tab duyurusu (anket formatında)
    print("\n[main] YouTube Community gönderisi yapılıyor...")
    try:
        post_community_update(video_id, script)
    except Exception as e:
        print(f"[main] Community gönderisi yapılamadı (kritik değil): {e}")

    # 8c) Seri sistemi devre dışı

    # 9) Instagram Reels cross-post
    if os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        print("\n[main] Instagram Reels'e yükleniyor...")
        try:
            post_reel(video_path, ig_caption(script))
        except Exception as e:
            print(f"[main] Instagram hatası (kritik değil): {e}")
    else:
        print("\n[main] INSTAGRAM_ACCESS_TOKEN yok, Instagram atlandı.")

    # 10) Facebook cross-post
    if os.environ.get("FACEBOOK_ACCESS_TOKEN"):
        print("\n[main] Facebook'a yükleniyor...")
        try:
            facebook_post(video_path, script, video_id)
        except Exception as e:
            print(f"[main] Facebook hatası (kritik değil): {e}")
    else:
        print("\n[main] FACEBOOK_ACCESS_TOKEN yok, Facebook atlandı.")

    # 10b) Twitter/X cross-post
    if os.environ.get("TWITTER_API_KEY"):
        print("\n[main] Twitter/X'e tweet atılıyor...")
        try:
            twitter_post(script["title"], video_id, script["tags"])
        except Exception as e:
            print(f"[main] Twitter hatası (kritik değil): {e}")
    else:
        print("\n[main] TWITTER_API_KEY yok, Twitter atlandı.")

    # 11) TikTok cross-post
    if os.environ.get("TIKTOK_ACCESS_TOKEN"):
        print("\n[main] TikTok'a yükleniyor...")
        try:
            tiktok_post(video_path, tt_title(script))
        except Exception as e:
            print(f"[main] TikTok hatası (kritik değil): {e}")
    else:
        print("\n[main] TIKTOK_ACCESS_TOKEN yok, TikTok atlandı.")

    # 12) Google Drive yedek
    if os.environ.get("GOOGLE_DRIVE_BACKUP", "false").lower() == "true":
        print("\n[main] Google Drive'a yedekleniyor...")
        try:
            backup_to_drive(video_path, thumb_path, script)
        except Exception as e:
            print(f"[main] Drive yedek hatası (kritik değil): {e}")

    # 13) Telegram başarı bildirimi
    print("\n[main] Telegram bildirimi gönderiliyor...")
    try:
        send_notification(
            title=script["title"],
            video_id=video_id,
            duration_sec=duration_sec,
            tags=script["tags"],
        )
    except Exception as e:
        print(f"[main] Telegram bildirimi gönderilemedi (kritik değil): {e}")

    # 14) Otomatik yorum yanıtı (ilk yorumlar için)
    print("\n[main] Otomatik yorum yanıtları kontrol ediliyor...")
    try:
        reply_to_comments(video_id, script["title"])
    except Exception as e:
        print(f"[main] Otomatik yorum yanıtı başarısız (kritik değil): {e}")

    # 15) Discord başarı bildirimi
    print("\n[main] Discord bildirimi gönderiliyor...")
    try:
        discord_video_live(
            title=script["title"],
            video_id=video_id,
            duration_sec=duration_sec,
            tags=script["tags"],
        )
    except Exception as e:
        print(f"[main] Discord bildirimi gönderilemedi (kritik değil): {e}")

    print("\n" + "=" * 52)
    print(f"✅  TAMAMLANDI! (WAR SHORTS v2)")
    print(f"   https://youtube.com/shorts/{video_id}")
    print("=" * 52)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WAR SHORTS Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Upload olmadan test et")
    parser.add_argument("--topic", type=str, default=None, help="Belirli bir konu belirt")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, topic_override=args.topic)
    except Exception as e:
        print(f"\n❌ Pipeline başarısız: {e}", file=sys.stderr)
        sys.exit(1)
