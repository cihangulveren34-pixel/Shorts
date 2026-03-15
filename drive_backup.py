"""
drive_backup.py — Üretilen video ve thumbnail'i Google Drive'a yedekler.

Aynı YouTube OAuth2 token'ı kullanır (Drive scope eklenmesi gerekir).
GOOGLE_DRIVE_FOLDER_ID: yedeklerin kaydedileceği Drive klasörü ID'si.
Ayarlanmazsa root'a yükler.

Gerekli scope (token yeniden alınırken ekle):
  https://www.googleapis.com/auth/drive.file
"""

import json
import os
import tempfile
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_credentials() -> Credentials:
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_json:
        data = json.loads(token_json)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        creds = Credentials.from_authorized_user_file(tmp.name, SCOPES)
        os.unlink(tmp.name)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        raise FileNotFoundError("YouTube token bulunamadı.")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _ensure_folder(service, title: str, parent_id: str = None) -> str:
    """
    Drive'da klasör varsa ID'sini döndürür, yoksa oluşturur.
    """
    query = f"name='{title}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": title,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]

    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def backup_to_drive(
    video_path: str,
    thumbnail_path: str = None,
    script: dict = None,
    folder_name: str = "WAR SHORTS Backups",
) -> dict:
    """
    Video (ve isteğe bağlı thumbnail + script) dosyalarını Drive'a yükler.
    Döndürür: {video_id, thumbnail_id, folder_id}
    """
    result = {}

    try:
        creds = _get_credentials()
        drive = build("drive", "v3", credentials=creds)

        root_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

        # Ana yedek klasörü
        backup_folder_id = _ensure_folder(drive, folder_name, root_folder_id)

        # Tarihe göre alt klasör (örn: "2026-03-15")
        from datetime import date
        date_folder_id = _ensure_folder(drive, str(date.today()), backup_folder_id)

        # Video yükle
        if video_path and os.path.exists(video_path):
            print(f"[drive] Video yükleniyor: {video_path}")
            video_meta = {
                "name": os.path.basename(video_path),
                "parents": [date_folder_id],
            }
            video_media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
            req = drive.files().create(body=video_meta, media_body=video_media, fields="id")
            resp = None
            while resp is None:
                status, resp = req.next_chunk()
                if status:
                    print(f"[drive] Yükleme: %{int(status.progress()*100)}")
            result["video_id"] = resp["id"]
            print(f"[drive] Video yüklendi: {resp['id']}")

        # Thumbnail yükle
        if thumbnail_path and os.path.exists(thumbnail_path):
            print(f"[drive] Thumbnail yükleniyor...")
            thumb_meta = {
                "name": os.path.basename(thumbnail_path),
                "parents": [date_folder_id],
            }
            thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/png")
            resp = drive.files().create(
                body=thumb_meta, media_body=thumb_media, fields="id"
            ).execute()
            result["thumbnail_id"] = resp["id"]
            print(f"[drive] Thumbnail yüklendi: {resp['id']}")

        # Script JSON yükle
        if script:
            script_bytes = json.dumps(script, indent=2, ensure_ascii=False).encode("utf-8")
            tmp = tempfile.NamedTemporaryFile(
                mode="wb", suffix=".json", delete=False
            )
            tmp.write(script_bytes)
            tmp.close()
            script_meta = {
                "name": f"script_{date.today()}.json",
                "parents": [date_folder_id],
            }
            script_media = MediaFileUpload(tmp.name, mimetype="application/json")
            resp = drive.files().create(
                body=script_meta, media_body=script_media, fields="id"
            ).execute()
            result["script_id"] = resp["id"]
            os.unlink(tmp.name)
            print(f"[drive] Script yüklendi: {resp['id']}")

        result["folder_id"] = date_folder_id
        print(f"[drive] Yedek tamamlandı → klasör: {date_folder_id}")

    except Exception as e:
        print(f"[drive] Yedekleme hatası (kritik değil): {e}")

    return result


if __name__ == "__main__":
    import sys

    video = sys.argv[1] if len(sys.argv) > 1 else "output/short.mp4"
    thumb = sys.argv[2] if len(sys.argv) > 2 else "output/thumbnail.png"

    result = backup_to_drive(video, thumb)
    print(result)
