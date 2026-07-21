#!/usr/bin/env python3
"""One-time: generate the Telethon StringSession for the UVB-76 ingest.

Run this ONCE on any machine you control (local PC, Hetzner — egal):

    pip install telethon
    python scripts/generate_session.py

It asks for your API ID + API HASH (from my.telegram.org), then logs into YOUR
Telegram (phone number + the code Telegram sends you). It prints one long string.

That string is the value for the GitHub secret  TELEGRAM_SESSION.

⚠  The string = full access to your Telegram account. Paste it ONLY into the
   GitHub secret. Never share it, never commit it, never send it in a chat.
"""

import os

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    api_id = os.environ.get("TELEGRAM_API_ID") or input("API ID: ").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH") or input("API HASH: ").strip()

    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session_string = client.session.save()
        print("\n" + "=" * 60)
        print("TELEGRAM_SESSION  — copy the whole line below into the GitHub secret:")
        print("=" * 60 + "\n")
        print(session_string)
        print("\n(Keep it secret. It is full access to your account.)")


if __name__ == "__main__":
    main()
