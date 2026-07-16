#!/usr/bin/env python3
"""Fetch new UVB-76 transmissions from Telegram channel and update the database."""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
STATE_FILE = DATA_DIR / ".last_message_id"
INGEST_LOG = DATA_DIR / "UVB76_TELEGRAM_INGEST.md"
JSON_OUT = DOCS_DIR / "transmissions.json"

API_ID = os.environ.get("TELEGRAM_API_ID", "")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION = os.environ.get("TELEGRAM_SESSION", "")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "UVB_76_radio")

MSK = timezone(timedelta(hours=3))


def try_parse_line(line: str, fallback_date: datetime) -> dict | None:
    original = line

    notes_match = re.search(r"\[([^\]]+)\]\s*$", line)
    notes = notes_match.group(1) if notes_match else ""
    if notes_match:
        line = line[: notes_match.start()].strip()

    date_str = None
    time_str = None

    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.\s+(\d{2}:\d{2})\s+", line)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        date_str = f"{fallback_date.year}-{month:02d}-{day:02d}"
        time_str = m.group(3)
        line = line[m.end():].strip()
    else:
        m = re.match(r"^(\d{2}:\d{2})\s+(?:MSK\s+|по\s+МСК\s+)?", line)
        if m:
            time_str = m.group(1)
            date_str = fallback_date.strftime("%Y-%m-%d")
            line = line[m.end():].strip()

    if not time_str:
        return None

    m = re.match(r"^([\wЀ-ӿ]+(?:\+[\wЀ-ӿ]+)*)\s+", line)
    if not m:
        return None
    callsigns = m.group(1).split("+")
    line = line[m.end():].strip()

    m = re.match(r"^(\d{5}(?:\+\d{5})*)\s*", line)
    if not m:
        return None
    command_blocks = m.group(1).split("+")
    line = line[m.end():].strip()

    words = []
    target_blocks = []
    tokens = re.split(r"[\s/]+", line)
    i = 0
    while i < len(tokens):
        token = tokens[i].strip()
        if not token or token.startswith("#"):
            i += 1
            continue
        if re.match(r"^\d{4}$", token):
            if i + 1 < len(tokens) and re.match(r"^\d{4}$", tokens[i + 1].strip()):
                target_blocks.append(f"{token} {tokens[i + 1].strip()}")
                i += 2
            else:
                target_blocks.append(token)
                i += 1
        elif re.match(r"^[A-ZА-ЯЁa-zа-яё]", token):
            words.append(token)
            i += 1
        else:
            i += 1

    if not words:
        return None

    tx_type = "single"
    if len(words) == 2:
        tx_type = "double"
    elif len(words) == 3:
        tx_type = "triple"
    elif len(words) >= 4:
        tx_type = "quadruple"
    if len(callsigns) > 1:
        tx_type = f"multi-callsign-{tx_type}"

    return {
        "date": date_str,
        "time_msk": time_str,
        "callsigns": callsigns,
        "command_blocks": command_blocks,
        "words": words,
        "target_blocks": target_blocks,
        "notes": notes,
        "type": tx_type,
    }


def parse_message(text: str, msg_date: datetime) -> list[dict]:
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            tx = try_parse_line(line, msg_date)
            if tx:
                results.append(tx)
    return results


def load_existing() -> dict:
    if JSON_OUT.exists():
        return json.loads(JSON_OUT.read_text(encoding="utf-8"))
    return {"meta": {}, "transmissions": []}


def make_key(tx: dict) -> tuple:
    return (tx["date"], tx["time_msk"], tuple(tx["words"]))


def load_state() -> int:
    if STATE_FILE.exists():
        text = STATE_FILE.read_text().strip()
        return int(text) if text else 0
    return 0


def save_state(msg_id: int):
    STATE_FILE.write_text(str(msg_id), encoding="utf-8")


def append_log(transmissions: list[dict]):
    lines = []
    if not INGEST_LOG.exists():
        lines.append("# UVB-76 Telegram Ingest Log\n")
    for tx in transmissions:
        parts = [tx["date"], tx["time_msk"]] + tx["callsigns"] + tx["command_blocks"] + tx["words"] + tx["target_blocks"]
        if tx["notes"]:
            parts.append(f"[{tx['notes']}]")
        lines.append(" ".join(parts))
    with open(INGEST_LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def run():
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    last_id = load_state()
    existing = load_existing()
    seen = {make_key(tx) for tx in existing["transmissions"]}
    new_txs = []
    max_id = last_id

    async with TelegramClient(StringSession(SESSION), int(API_ID), API_HASH) as client:
        entity = await client.get_entity(CHANNEL)
        kwargs = {"limit": 100, "min_id": last_id} if last_id else {"limit": 50}
        async for msg in client.iter_messages(entity, **kwargs):
            if not msg.text:
                continue
            max_id = max(max_id, msg.id)
            msg_date = msg.date.astimezone(MSK)
            for tx in parse_message(msg.text, msg_date):
                key = make_key(tx)
                if key not in seen:
                    seen.add(key)
                    new_txs.append(tx)

    save_state(max_id)

    if not new_txs:
        print("Keine neuen Übertragungen.")
        return

    print(f"{len(new_txs)} neue Übertragung(en) gefunden.")
    existing["transmissions"].extend(new_txs)
    existing["transmissions"].sort(key=lambda t: (t["date"], t["time_msk"]))
    existing["meta"]["total_transmissions"] = len(existing["transmissions"])
    if existing["transmissions"]:
        existing["meta"]["date_range"] = {
            "start": existing["transmissions"][0]["date"],
            "end": existing["transmissions"][-1]["date"],
        }

    JSON_OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    append_log(new_txs)

    for tx in new_txs:
        print(f"  + {tx['date']} {tx['time_msk']} {' '.join(tx['words'])}")


def main():
    if not all([API_ID, API_HASH, SESSION]):
        print("Telegram-Zugangsdaten nicht gesetzt — überspringe Ingest.")
        sys.exit(0)
    asyncio.run(run())


if __name__ == "__main__":
    main()
