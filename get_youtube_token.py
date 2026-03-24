"""
get_youtube_token.py — YouTube OAuth2 token almak için tek seferlik çalıştırılan script.

Kullanım:
  1. Google Cloud Console'dan OAuth2 client_secret.json indirin
  2. python get_youtube_token.py
  3. Tarayıcıda yetkilendirme yapın
  4. Oluşan token.json içeriğini YOUTUBE_TOKEN_JSON secret'ına yapıştırın
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = json.loads(creds.to_json())
    with open("token.json", "w") as f:
        json.dump(token_data, f, indent=2)

    print("\n✅ token.json oluşturuldu!")
    print("\nBu içeriği GitHub Secret'a ekleyin (YOUTUBE_TOKEN_JSON):")
    print(json.dumps(token_data, indent=2))
