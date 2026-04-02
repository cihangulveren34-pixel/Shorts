#!/usr/bin/env python3
"""
setup_channel.py — WAR SHORTS Kanal Kurulum Sihirbazı

Yeni bir YouTube kanalı için tüm altyapıyı otomatik kurar:
  1. GitHub repo fork'lama
  2. Dil + konu keyword ayarı
  3. Gemini API key
  4. YouTube OAuth token
  5. YouTube cookies (tarayıcıdan otomatik)
  6. Telegram bildirimleri (opsiyonel)
  7. Tüm secrets/variables GitHub'a push
  8. Workflow aktivasyonu

Kullanım:
  python setup_channel.py
"""

import os
import sys
import json
import time
import base64
import shutil
import tempfile
import subprocess
import webbrowser

# ─── Bağımlılık kontrolü ──────────────────────────────────────────────────────
def _ensure(pkg, import_as=None):
    name = import_as or pkg
    try:
        __import__(name)
    except ImportError:
        print(f"  → {pkg} kuruluyor...")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"],
                       check=True)

_ensure("requests")
import requests  # noqa: E402

# ─── Renkler ──────────────────────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"
B = "\033[94m"; C = "\033[96m"; DIM = "\033[2m"
BOLD = "\033[1m"; RESET = "\033[0m"

SOURCE_REPO = "dehbkoclugu-afk/Shorts"
GH_API      = "https://api.github.com"
DEFAULT_KW  = ("Israel,Gaza,Hamas,Hezbollah,IDF,West Bank,Jerusalem,"
               "Iran,IRGC,Iran nuclear,Iran missile,Iran US,Iran Israel,Iranian")


# ─── UI yardımcıları ──────────────────────────────────────────────────────────

def hdr(n, title):
    print(f"\n{BOLD}{C}━━━ [{n}] {title} ━━━{RESET}")

def ok(msg):   print(f"  {G}✓{RESET}  {msg}")
def warn(msg): print(f"  {Y}⚠{RESET}  {msg}")
def err(msg):  print(f"  {R}✗{RESET}  {msg}")
def info(msg): print(f"  {B}→{RESET}  {msg}")

def ask(prompt, default=None, secret=False):
    tag = f" [{default}]" if default else ""
    suffix = f"{BOLD}{prompt}{tag}: {RESET}"
    if secret:
        import getpass
        val = getpass.getpass(f"  {suffix}")
    else:
        val = input(f"  {suffix}").strip()
    return val if val else (default or "")

def confirm(prompt, default=True):
    hint = "E/h" if default else "e/H"
    ans = input(f"  {BOLD}{Y}{prompt} ({hint}): {RESET}").strip().lower()
    if not ans:
        return default
    return ans in ("e", "evet", "y", "yes", "1")


# ─── GitHub API ───────────────────────────────────────────────────────────────

def _gh(method, path, token, data=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GH_API}{path}"
    return getattr(requests, method)(url, headers=headers, json=data, timeout=30)


def get_username(token):
    r = _gh("get", "/user", token)
    r.raise_for_status()
    return r.json()["login"]


def fork_repo(token):
    owner, repo = SOURCE_REPO.split("/")
    r = _gh("post", f"/repos/{SOURCE_REPO}/forks", token,
            {"default_branch_only": False})
    if r.status_code in (200, 202):
        fork_name = r.json()["full_name"]
        info(f"Fork oluşturuldu, hazırlanıyor...")
        # Fork'un GitHub'da oluşması için bekle
        for _ in range(15):
            time.sleep(3)
            check = _gh("get", f"/repos/{fork_name}", token)
            if check.status_code == 200:
                return fork_name
        return fork_name
    if r.status_code == 422:
        # Zaten fork'lanmış
        uname = get_username(token)
        return f"{uname}/{repo}"
    r.raise_for_status()


def get_pubkey(owner, repo, token):
    r = _gh("get", f"/repos/{owner}/{repo}/actions/secrets/public-key", token)
    r.raise_for_status()
    return r.json()


def _encrypt(value: str, public_key_b64: str) -> str:
    try:
        from nacl.encoding import Base64Encoder
        from nacl.public import PublicKey, SealedBox
    except ImportError:
        _ensure("PyNaCl", "nacl")
        from nacl.encoding import Base64Encoder
        from nacl.public import PublicKey, SealedBox
    pk  = PublicKey(public_key_b64.encode(), Base64Encoder)
    box = SealedBox(pk)
    return base64.b64encode(box.encrypt(value.encode())).decode()


def set_secret(owner, repo, token, name, value):
    pk   = get_pubkey(owner, repo, token)
    enc  = _encrypt(value, pk["key"])
    r    = _gh("put", f"/repos/{owner}/{repo}/actions/secrets/{name}", token,
               {"encrypted_value": enc, "key_id": pk["key_id"]})
    return r.status_code in (201, 204)


def set_variable(owner, repo, token, name, value):
    r = _gh("get", f"/repos/{owner}/{repo}/actions/variables/{name}", token)
    if r.status_code == 200:
        r = _gh("patch", f"/repos/{owner}/{repo}/actions/variables/{name}",
                token, {"name": name, "value": value})
    else:
        r = _gh("post", f"/repos/{owner}/{repo}/actions/variables",
                token, {"name": name, "value": value})
    return r.status_code in (200, 201, 204)


def enable_workflow(owner, repo, token, wf_file):
    r = _gh("put",
            f"/repos/{owner}/{repo}/actions/workflows/{wf_file}/enable",
            token)
    return r.status_code == 204


# ─── YouTube OAuth ────────────────────────────────────────────────────────────

def run_youtube_oauth(client_secrets_path: str) -> str:
    """OAuth akışını başlatır, token JSON döndürür."""
    for pkg in ["google-auth-oauthlib", "google-auth-httplib2", "google-api-python-client"]:
        _ensure(pkg, pkg.replace("-", "_").split("_")[0])

    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
    ]
    flow  = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True,
                                  success_message="Token alındı! Bu pencereyi kapatabilirsiniz.")
    return json.dumps({
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes),
    })


# ─── YT Cookies ───────────────────────────────────────────────────────────────

def extract_yt_cookies() -> str | None:
    """Tarayıcıdan YouTube cookies otomatik çıkarır."""
    if not shutil.which("yt-dlp"):
        warn("yt-dlp bulunamadı, cookies otomatik alınamıyor.")
        warn("  Kurulum: pip install yt-dlp  veya  winget install yt-dlp")
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, prefix="ytcookies_")
    tmp.close()

    for browser in ["chrome", "firefox", "edge", "brave", "chromium", "safari"]:
        try:
            r = subprocess.run(
                ["yt-dlp",
                 "--cookies-from-browser", browser,
                 "--cookies", tmp.name,
                 "--skip-download",
                 "https://www.youtube.com/watch?v=jNQXAC9IVRw"],
                capture_output=True, text=True, timeout=30
            )
            if (os.path.exists(tmp.name)
                    and os.path.getsize(tmp.name) > 200):
                with open(tmp.name, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if "youtube.com" in content:
                    ok(f"{browser} tarayıcısından cookies alındı.")
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    return content
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return None


# ─── Ana akış ─────────────────────────────────────────────────────────────────

def main():
    print(f"""
{BOLD}{C}╔══════════════════════════════════════════════════╗
║      WAR SHORTS — Kanal Kurulum Sihirbazı      ║
║  Yeni kanal için tüm altyapıyı otomatik kurar  ║
╚══════════════════════════════════════════════════╝{RESET}
Çıkmak için Ctrl+C
""")

    secrets   = {}   # GitHub'a yazılacak secrets
    variables = {}   # GitHub'a yazılacak variables

    # ─────────────────────────────────────────────────────────────────────────
    # 1) GitHub PAT
    # ─────────────────────────────────────────────────────────────────────────
    hdr(1, "GitHub Personal Access Token")
    info("Token oluşturmak için tarayıcı açılıyor...")
    info("Gerekli izinler: ✓ repo (full)  ✓ workflow")
    webbrowser.open(
        "https://github.com/settings/tokens/new"
        "?scopes=repo,workflow&description=WarShorts-Setup"
    )
    time.sleep(1)

    while True:
        gh_token = ask("GitHub PAT yapıştırın", secret=True)
        if not gh_token:
            err("Token boş olamaz.")
            continue
        try:
            username = get_username(gh_token)
            ok(f"Doğrulandı → @{username}")
            break
        except Exception as e:
            err(f"Token geçersiz: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 2) Repo fork
    # ─────────────────────────────────────────────────────────────────────────
    hdr(2, "Repo Fork")
    info(f"Kaynak: github.com/{SOURCE_REPO}")
    try:
        fork_full = fork_repo(gh_token)
        owner, repo = fork_full.split("/")
        ok(f"Fork hazır → github.com/{fork_full}")
    except Exception as e:
        err(f"Fork başarısız: {e}")
        sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────────
    # 3) Dil seçimi
    # ─────────────────────────────────────────────────────────────────────────
    hdr(3, "Kanal Dili")
    print(f"  {DIM}en = İngilizce  |  tr = Türkçe  |  ar = Arapça{RESET}")
    while True:
        lang = ask("Dil", default="en").lower()
        if lang in ("en", "tr", "ar"):
            break
        err("Geçersiz. en / tr / ar yazın.")
    variables["LANGUAGE"] = lang
    ok(f"Dil: {lang}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4) Konu filtreleri
    # ─────────────────────────────────────────────────────────────────────────
    hdr(4, "Konu Filtreleri (TOPIC_KEYWORDS)")
    info("Virgülle ayırın. Boş bırakırsanız askeri/jeopolitik varsayılan kullanılır.")
    info(f"{DIM}Örnek: Israel,Iran,Gaza,IRGC{RESET}")
    kw = ask("Keywords", default=DEFAULT_KW)
    variables["TOPIC_KEYWORDS"] = kw
    ok("TOPIC_KEYWORDS ayarlandı.")

    # ─────────────────────────────────────────────────────────────────────────
    # 5) Gemini API Key
    # ─────────────────────────────────────────────────────────────────────────
    hdr(5, "Gemini API Key")
    info("Tarayıcı açılıyor → aistudio.google.com/apikey")
    webbrowser.open("https://aistudio.google.com/apikey")
    time.sleep(1)
    gemini = ask("Gemini API Key (AIza...)", secret=True)
    if gemini:
        secrets["GEMINI_API_KEY"] = gemini
        ok("GEMINI_API_KEY alındı.")
    else:
        warn("Atlandı — daha sonra GitHub Secrets'tan ekleyin.")

    # ─────────────────────────────────────────────────────────────────────────
    # 6) YouTube OAuth
    # ─────────────────────────────────────────────────────────────────────────
    hdr(6, "YouTube API — OAuth Token")
    print(f"""
  {DIM}Google Cloud Console'dan client_secrets.json indirmeniz gerekiyor:

  1. console.cloud.google.com → New Project → isim verin
  2. APIs & Services → Library → "YouTube Data API v3" → Enable
  3. OAuth consent screen → External → App adı girin → Save & Continue
  4. Credentials → + Create Credentials → OAuth 2.0 Client ID
     → Application type: Desktop App → Create
  5. Sağdaki ↓ (Download) butonuna tıklayın → JSON olarak kaydedin{RESET}
""")
    webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
    time.sleep(1)

    while True:
        secrets_path = ask("client_secrets.json dosya yolu", default="client_secrets.json")
        # Dizin girilmişse içindeki client_secrets.json'ı dene
        if os.path.isdir(secrets_path):
            candidate = os.path.join(secrets_path, "client_secrets.json")
            if os.path.isfile(candidate):
                secrets_path = candidate
                ok(f"Dosya bulundu: {secrets_path}")
            else:
                err(f"'{secrets_path}' bir dizin. Lütfen doğrudan .json dosyasının yolunu girin.")
                err(f"  Örnek: C:\\Users\\kedi\\Downloads\\client_secrets.json")
                continue
        if os.path.isfile(secrets_path):
            break
        err(f"Dosya bulunamadı: {secrets_path}")
        if not confirm("Tekrar denemek ister misiniz?"):
            warn("YouTube token atlandı. Daha sonra GitHub Secrets'tan YOUTUBE_TOKEN_JSON ekleyin.")
            secrets_path = None
            break

    if secrets_path:
        info("OAuth akışı başlatılıyor (tarayıcı açılacak)...")
        try:
            yt_token = run_youtube_oauth(secrets_path)
            secrets["YOUTUBE_TOKEN_JSON"] = yt_token
            ok("YOUTUBE_TOKEN_JSON alındı.")
        except Exception as e:
            err(f"YouTube OAuth başarısız: {e}")
            warn("YOUTUBE_TOKEN_JSON'ı daha sonra GitHub Secrets'tan manuel ekleyin.")

    # ─────────────────────────────────────────────────────────────────────────
    # 7) YouTube Cookies
    # ─────────────────────────────────────────────────────────────────────────
    hdr(7, "YouTube Cookies")
    info("Bot tespitini azaltmak için tarayıcı oturumundan cookies alınır.")
    if confirm("Tarayıcıdan otomatik çıkarmayı deneyelim mi?"):
        cookies = extract_yt_cookies()
        if cookies:
            secrets["YT_COOKIES"] = cookies
            ok("YT_COOKIES alındı.")
        else:
            warn("Otomatik çıkarma başarısız.")
            info("Manuel yöntem:")
            info("  yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://youtube.com")
            info("  → cookies.txt içeriğini GitHub Secrets → YT_COOKIES'e yapıştırın")
    else:
        info("Atlandı.")

    # ─────────────────────────────────────────────────────────────────────────
    # 8) Telegram (opsiyonel)
    # ─────────────────────────────────────────────────────────────────────────
    hdr(8, "Telegram Bildirimleri (Opsiyonel)")
    info("Her video yüklenince Telegram'a bildirim gönderir.")
    if confirm("Telegram bot eklemek istiyor musunuz?", default=False):
        tg_token = ask("Bot Token (@BotFather'dan)", secret=True)
        tg_chat  = ask("Chat ID (@userinfobot'tan)")
        if tg_token and tg_chat:
            secrets["TELEGRAM_BOT_TOKEN"] = tg_token
            secrets["TELEGRAM_CHAT_ID"]   = tg_chat
            ok("Telegram ayarlandı.")
    else:
        info("Atlandı.")

    # ─────────────────────────────────────────────────────────────────────────
    # 9) GitHub'a yaz
    # ─────────────────────────────────────────────────────────────────────────
    hdr(9, "GitHub Secrets & Variables Kaydediliyor")

    # Variables
    for name, value in variables.items():
        try:
            if set_variable(owner, repo, gh_token, name, value):
                ok(f"Variable: {name}")
            else:
                warn(f"Variable yazılamadı: {name}")
        except Exception as e:
            err(f"Variable hatası ({name}): {e}")

    # Secrets
    for name, value in secrets.items():
        try:
            if set_secret(owner, repo, gh_token, name, value):
                ok(f"Secret:   {name}")
            else:
                warn(f"Secret yazılamadı: {name}")
        except Exception as e:
            err(f"Secret hatası ({name}): {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 10) Workflow aktif et
    # ─────────────────────────────────────────────────────────────────────────
    hdr(10, "Workflow Aktivasyonu")
    wf = "arabic_daily.yml" if lang == "ar" else "daily.yml"
    try:
        if enable_workflow(owner, repo, gh_token, wf):
            ok(f"{wf} aktif edildi.")
        else:
            info(f"{wf} zaten aktif.")
    except Exception as e:
        warn(f"Workflow aktivasyon hatası (kritik değil): {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Özet
    # ─────────────────────────────────────────────────────────────────────────
    missing = []
    if "GEMINI_API_KEY"     not in secrets: missing.append("GEMINI_API_KEY")
    if "YOUTUBE_TOKEN_JSON" not in secrets: missing.append("YOUTUBE_TOKEN_JSON")
    if "YT_COOKIES"         not in secrets: missing.append("YT_COOKIES")

    print(f"""
{BOLD}{G}╔══════════════════════════════════════════════════╗
║            KURULUM TAMAMLANDI! ✓               ║
╚══════════════════════════════════════════════════╝{RESET}

  {BOLD}Fork:    {RESET}https://github.com/{fork_full}
  {BOLD}Dil:     {RESET}{lang}
  {BOLD}Actions: {RESET}https://github.com/{fork_full}/actions
  {BOLD}Secrets: {RESET}https://github.com/{fork_full}/settings/secrets/actions
""")

    if missing:
        print(f"  {Y}{BOLD}Eksik (manuel ekleyin):{RESET}")
        for m in missing:
            print(f"  {Y}  • {m}{RESET}")
        print()

    print(f"  {BOLD}Sonraki adım:{RESET}")
    print(f"  → Actions sekmesinde '{wf}' workflow'unu Run Workflow ile test edin")
    print(f"  → https://github.com/{fork_full}/actions\n")

    if "YOUTUBE_TOKEN_JSON" in missing:
        print(f"  {R}⚠  YOUTUBE_TOKEN_JSON eksik — video upload olmaz!{RESET}")
        print(f"     YouTube OAuth için yt_oauth_setup.yml workflow'unu çalıştırın.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {Y}Kurulum iptal edildi.{RESET}\n")
        sys.exit(0)
