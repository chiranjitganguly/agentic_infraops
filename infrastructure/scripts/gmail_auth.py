"""
Run once locally to generate a Gmail OAuth2 token.

Usage:
    python infrastructure/scripts/gmail_auth.py [--credentials PATH] [--token PATH]

Defaults match .env.example:
    credentials: ./secrets/gmail-credentials.json
    token:       ./secrets/gmail-token.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Gmail OAuth2 token")
    parser.add_argument(
        "--credentials",
        default=os.getenv("GMAIL_CREDENTIALS_PATH", "./secrets/gmail-credentials.json"),
        help="Path to OAuth2 credentials JSON downloaded from Google Cloud Console",
    )
    parser.add_argument(
        "--token",
        default="./secrets/gmail-token.json",
        help="Destination path for the generated token file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    credentials_path = Path(args.credentials)
    token_path = Path(args.token)

    if not credentials_path.exists():
        print(f"ERROR: credentials file not found: {credentials_path}", file=sys.stderr)
        print("Download it from Google Cloud Console → APIs & Services → Credentials", file=sys.stderr)
        sys.exit(1)

    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        print(f"Existing token is still valid: {token_path}")
        return

    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired token...")
        creds.refresh(Request())
    else:
        print("Starting OAuth2 flow — a browser window will open...")
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"Token saved to: {token_path}")
    print()
    print("Add this to your .env:")
    print(f"  GMAIL_TOKEN_PATH={token_path}")


if __name__ == "__main__":
    main()
