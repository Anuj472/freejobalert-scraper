"""
One-time script to re-authorize Google Drive with the 'drive' scope.
Run this ONCE from a terminal with a browser available:

    python3 reauth_drive.py

It will open a browser, ask you to sign in with your Google account,
and save a fresh token.json with the correct scope.
"""
import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = "token.json"


def main():
    # Load existing token to get client_id / client_secret
    if not os.path.exists(TOKEN_PATH):
        print(f"❌ {TOKEN_PATH} not found. Cannot proceed.")
        return

    with open(TOKEN_PATH) as f:
        existing = json.load(f)

    client_config = {
        "installed": {
            "client_id": existing["client_id"],
            "client_secret": existing["client_secret"],
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save new token
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"✓ token.json updated with 'drive' scope!")
    print(f"  Token saved to: {TOKEN_PATH}")
    print(f"  You can now run the scraper — Drive uploads will use your personal quota.")


if __name__ == "__main__":
    main()
