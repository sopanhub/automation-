import os
import re
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    # Load existing .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')

    if not client_id or not client_secret or client_id == 'your_client_id_here':
        print("Error: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are not set correctly in your .env file.")
        print("Please set them with real credentials from Google Cloud Console first.")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    print("Opening browser for authentication...")
    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        credentials = flow.run_local_server(port=0)
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    refresh_token = credentials.refresh_token

    if not refresh_token:
        print("No refresh token received. You might need to revoke the app access in your Google account and try again, or ensure you are requesting offline access.")
        return

    print("\nSuccessfully obtained new refresh token!")
    
    # Update .env file
    try:
        with open(env_path, 'r') as f:
            env_content = f.read()

        if 'YOUTUBE_REFRESH_TOKEN=' in env_content:
            # Replace existing token
            env_content = re.sub(
                r'YOUTUBE_REFRESH_TOKEN=.*',
                f'YOUTUBE_REFRESH_TOKEN="{refresh_token}"',
                env_content
            )
        else:
            # Append new token
            if not env_content.endswith('\n'):
                env_content += '\n'
            env_content += f'YOUTUBE_REFRESH_TOKEN="{refresh_token}"\n'

        with open(env_path, 'w') as f:
            f.write(env_content)
        
        print("Successfully updated YOUTUBE_REFRESH_TOKEN in your .env file.")
        print("You can now resume generating/uploading videos!")

    except Exception as e:
        print(f"Failed to update .env file automatically: {e}")
        print(f"Please manually copy this token to your .env file as YOUTUBE_REFRESH_TOKEN:\n{refresh_token}")

if __name__ == '__main__':
    main()
