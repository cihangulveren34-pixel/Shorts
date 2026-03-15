"""
poster_twitter.py — Twitter/X'e otomatik video tanıtım tweet'i atar.

Twitter API v2 (OAuth 1.0a kullanıcı kimlik doğrulaması) ile tweet gönderir.
Ücretsiz plan: 1500 tweet/ay yazma limiti — günlük 1 video için fazlasıyla yeterli.

Gereksinim (GitHub Secrets):
  TWITTER_API_KEY           — API Key (Consumer Key)
  TWITTER_API_SECRET        — API Secret (Consumer Secret)
  TWITTER_ACCESS_TOKEN      — Access Token
  TWITTER_ACCESS_TOKEN_SECRET — Access Token Secret

Twitter Developer Portal: developer.twitter.com → Free plan yeterli.
"""

import hashlib
import hmac
import os
import time
import urllib.parse
import base64
import secrets

import requests

TIMEOUT = 15
TWEET_MAX_LEN = 280


def _oauth1_header(method: str, url: str, params: dict) -> str:
    """
    OAuth 1.0a Authorization başlığı oluşturur.
    Harici kütüphane gerekmez — saf Python uygulaması.
    """
    api_key    = os.environ["TWITTER_API_KEY"]
    api_secret = os.environ["TWITTER_API_SECRET"]
    token      = os.environ["TWITTER_ACCESS_TOKEN"]
    token_secret = os.environ["TWITTER_ACCESS_TOKEN_SECRET"]

    oauth_params = {
        "oauth_consumer_key":     api_key,
        "oauth_nonce":            secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }

    # Tüm parametreleri birleştir (body params dahil)
    all_params = {**params, **oauth_params}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )

    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])

    signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature

    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return auth_header


def _check_credentials() -> bool:
    required = [
        "TWITTER_API_KEY", "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[twitter] Eksik env değişkeni: {missing}. Tweet atlandı.")
        return False
    return True


def _build_tweet_text(title: str, video_id: str, tags: list[str]) -> str:
    """Tweet metnini oluşturur. 280 karakter limitine uyar."""
    yt_url = f"https://youtube.com/shorts/{video_id}"
    hashtags = " ".join(f"#{t}" for t in tags[:4] if t.isalpha())

    # Başlık + URL + hashtag
    body = f"⚔️ {title}\n\n{hashtags}\n\n{yt_url}"

    if len(body) <= TWEET_MAX_LEN:
        return body

    # Başlığı kısalt
    max_title = TWEET_MAX_LEN - len(f"⚔️ \n\n{hashtags}\n\n{yt_url}") - 3
    short_title = title[:max_title] + "..."
    return f"⚔️ {short_title}\n\n{hashtags}\n\n{yt_url}"


def post_tweet(title: str, video_id: str, tags: list[str]) -> bool:
    """
    YouTube Shorts linkini içeren tanıtım tweet'i atar.

    Args:
        title: Video başlığı
        video_id: YouTube video ID
        tags: Hashtag listesi

    Returns:
        True if successful
    """
    if not _check_credentials():
        return False

    tweet_text = _build_tweet_text(title, video_id, tags)

    url = "https://api.twitter.com/2/tweets"
    body = {"text": tweet_text}

    try:
        auth_header = _oauth1_header("POST", url, {})
        resp = requests.post(
            url,
            json=body,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT,
        )

        if resp.status_code == 201:
            data = resp.json()
            tweet_id = data.get("data", {}).get("id", "?")
            print(f"[twitter] Tweet atıldı: https://x.com/i/web/status/{tweet_id}")
            return True

        print(f"[twitter] Hata: {resp.status_code} — {resp.text[:300]}")
        return False

    except Exception as e:
        print(f"[twitter] İstek hatası: {e}")
        return False


def post_thread(title: str, video_id: str, tags: list[str], hook: str = "") -> bool:
    """
    2 tweet'lik thread atar: ana tweet + hook/teaser.
    """
    if not _check_credentials():
        return False

    yt_url = f"https://youtube.com/shorts/{video_id}"
    hashtags = " ".join(f"#{t}" for t in tags[:4] if t.isalpha())

    # 1. tweet
    tweet1 = f"⚔️ {title}\n\n{hashtags}\n\n{yt_url}"
    if len(tweet1) > TWEET_MAX_LEN:
        tweet1 = _build_tweet_text(title, video_id, tags)

    url = "https://api.twitter.com/2/tweets"

    try:
        auth_header = _oauth1_header("POST", url, {})
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        # 1. tweet gönder
        resp1 = requests.post(url, json={"text": tweet1}, headers=headers, timeout=TIMEOUT)
        if resp1.status_code != 201:
            print(f"[twitter] 1. tweet hatası: {resp1.status_code}")
            return False

        tweet1_id = resp1.json()["data"]["id"]

        # 2. tweet (hook reply) — sadece hook varsa
        if hook:
            hook_text = f"💡 {hook[:220]}"
            auth_header2 = _oauth1_header("POST", url, {})
            headers["Authorization"] = auth_header2
            resp2 = requests.post(
                url,
                json={
                    "text": hook_text,
                    "reply": {"in_reply_to_tweet_id": tweet1_id},
                },
                headers=headers,
                timeout=TIMEOUT,
            )
            if resp2.status_code == 201:
                print(f"[twitter] Thread atıldı (2 tweet): {tweet1_id}")
            else:
                print(f"[twitter] 2. tweet hatası (kritik değil): {resp2.status_code}")

        return True

    except Exception as e:
        print(f"[twitter] Thread hatası: {e}")
        return False


if __name__ == "__main__":
    import sys
    vid = sys.argv[1] if len(sys.argv) > 1 else "test_id"
    post_tweet(
        title="What if Rome Never Fell?",
        video_id=vid,
        tags=["history", "whatif", "war", "shorts"],
    )
