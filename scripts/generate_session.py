#!/usr/bin/env python3
"""One-time script: generates a Telethon StringSession for use in GitHub Actions.

Run this locally once:
    pip install telethon
    python scripts/generate_session.py

Then save the printed session string as GitHub secret TELEGRAM_SESSION.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# Get these from https://my.telegram.org → API development tools
API_ID = input("API ID: ").strip()
API_HASH = input("API Hash: ").strip()


async def main():
    async with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
        session_string = client.session.save()
        print("\n--- TELEGRAM_SESSION (als GitHub Secret speichern) ---")
        print(session_string)
        print("------------------------------------------------------")


asyncio.run(main())
