import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

def test_token(client_id, client_secret, refresh_token, name):
    print(f"Testing {name} credentials...")
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.channels().list(part="snippet", mine=True)
        response = request.execute()
        print(f"✅ SUCCESS! Token belongs to channel: {response['items'][0]['snippet']['title']}")
    except RefreshError as e:
        print(f"❌ RefreshError: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

from dotenv import load_dotenv

load_dotenv()

mc_client_id = os.environ.get("MINECRAFT_YOUTUBE_CLIENT_ID")
mc_client_secret = os.environ.get("MINECRAFT_YOUTUBE_CLIENT_SECRET")
mc_refresh_token = os.environ.get("MINECRAFT_YOUTUBE_REFRESH_TOKEN")

mb_client_id = os.environ.get("MRBEAST_YOUTUBE_CLIENT_ID")
mb_client_secret = os.environ.get("MRBEAST_YOUTUBE_CLIENT_SECRET")
mb_refresh_token = os.environ.get("MRBEAST_YOUTUBE_REFRESH_TOKEN")

if mc_client_id and mc_client_secret and mc_refresh_token:
    test_token(mc_client_id, mc_client_secret, mc_refresh_token, "MINECRAFT Channel")
else:
    print("MINECRAFT environment variables missing.")

if mb_client_id and mb_client_secret and mb_refresh_token:
    test_token(mb_client_id, mb_client_secret, mb_refresh_token, "MRBEAST Channel")
else:
    print("MRBEAST environment variables missing.")
