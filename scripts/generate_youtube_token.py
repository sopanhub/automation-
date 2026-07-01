import argparse
import os
import re
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    parser = argparse.ArgumentParser(description="Generate YouTube token")
    parser.add_argument("--channel", default="minecraft", help="Channel prefix (minecraft or mrbeast)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    prefix = args.channel.upper() + "_"
    client_id = os.getenv(f"{prefix}YOUTUBE_CLIENT_ID") or os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv(f"{prefix}YOUTUBE_CLIENT_SECRET") or os.getenv("YOUTUBE_CLIENT_SECRET")

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
        # Force account selection menu
        credentials = flow.run_local_server(port=0, prompt="select_account")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    refresh_token = credentials.refresh_token

    if not refresh_token:
        print("No refresh token received.")
        return

    print("\nSuccessfully obtained new refresh token!")
    
    # Update .env file
    try:
        with open(env_path, 'r') as f:
            env_content = f.read()

        if f'{prefix}YOUTUBE_REFRESH_TOKEN=' in env_content:
            env_content = re.sub(
                rf'{prefix}YOUTUBE_REFRESH_TOKEN=.*',
                f'{prefix}YOUTUBE_REFRESH_TOKEN="{refresh_token}"',
                env_content
            )
        else:
            if not env_content.endswith('\n'):
                env_content += '\n'
            env_content += f'{prefix}YOUTUBE_REFRESH_TOKEN="{refresh_token}"\n'

        with open(env_path, 'w') as f:
            f.write(env_content)
        
        print(f"Successfully updated {prefix}YOUTUBE_REFRESH_TOKEN in your .env file.")

    except Exception as e:
        print(f"Failed to update .env file: {e}")
        print(f"Token:\n{refresh_token}")

if __name__ == '__main__':
    main()