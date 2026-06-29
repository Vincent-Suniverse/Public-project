#!/usr/bin/env python3
"""Fetch new UVB-76 transmissions from Telegram channel and update the database."""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@uvb76logs")
MSK = timezone(timedelta(hours=3))

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
STATE_FILE = DATA_DIR / ".last_update_id"
INGEST_LOG = DATA_DIR / "UVB76_TELEGRAM_INGEST.md"
JSON_OUT = DOCS_DIR / "transmissions.json"


def get_updates(offset: int | None = None) -> list[dict]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10, "allowed_updates": '["channel_post"]'}
    if offset:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        print(f"Telegram API error: {data}", file=sys.stderr)
        return []
    return data.get("result", [])


def parse_message_text(text: str, msg_date: datetime) -> list[dict]:
    """Parse one Telegram message into zero or more transmission dicts."""
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        tx = try_parse_line(line, msg_date)
        if tx:
            results.append(tx)
    return results


def try_parse_line(line: str, fallback_date: datetime) -> dict | None:
    """Try to parse a single line as a UVB-76 transmission."""
    original = line

    notes_match = re.search(r"\[([^\]]+)\]\s*$", line)
    notes = notes_match.group(1) if notes_match else ""
    if notes_match:
        line = line[: notes_match.start()].strip()

    date_str = None
    time_str = None

    # Format: "29.6. 10:31 ..." or "29.06. 10:31 ..."
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.\s+(\d{2}:\d{2})\s+", line)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = fallback_date.year
        date_str = f"{year}-{month:02d}-{day:02d}"
        time_str = m.group(3)
        line = line[m.end():].strip()
    else:
        # Format: "10:31 MSK ..." or "10:31 ..."
        m = re.match(r"^(\d{2}:\d{2})\s+(?:MSK\s+)?", line)
        if m:
            time_str = m.group(1)
            date_str = fallback_date.strftime("%Y-%m-%d")
            line = line[m.end():].strip()

    if not time_str:
        return None

    # Callsign(s)
    m = re.match(r"^([\wЀ-ӿ]+(?:\+[\wЀ-ӿ]+)*)\s+", line)
    if not m:
        return None
    callsigns = m.group(1).split("+")
    line = line[m.end():].strip()

    # 5-digit command block(s)
    m = re.match(r"^(\d{5}(?:\+\d{5})*)\s+", line)
    if not m:
        return None
    command_blocks = m.group(1).split("+")
    line = line[m.end():].strip()

    # Remaining: words and 4-digit target blocks
    words = []
    target_blocks = []
    tokens = line.replace("/", " ").split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"^\d{4}$", token):
            if i + 1 < len(tokens) and re.match(r"^\d{4}$", tokens[i + 1]):
                target_blocks.append(f"{token} {tokens[i + 1]}")
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


def load_existing() -> dict:
    if JSON_OUT.exists():
        return json.loads(JSON_OUT.read_text(encoding="utf-8"))
    return {"meta": {}, "transmissions": []}


def make_dedup_key(tx: dict) -> tuple:
    return (tx["date"], tx["time_msk"], tuple(tx["words"]))


def append_to_log(transmissions: list[dict]):
    """Append new transmissions to the markdown ingest log."""
    lines = []
    if not INGEST_LOG.exists():
        lines.append("# UVB-76 Telegram Ingest Log\n")
        lines.append("Automatisch erfasste Übertragungen aus @uvb76logs.\n\n---\n")

    for tx in transmissions:
        parts = [tx["date"], tx["time_msk"]]
        parts.extend(tx["callsigns"])
        parts.extend(tx["command_blocks"])
        parts.extend(tx["words"])
        parts.extend(tx["target_blocks"])
        if tx["notes"]:
            parts.append(f"[{tx['notes']}]")
        lines.append(" ".join(parts))

    with open(INGEST_LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def save_state(update_id: int):
    STATE_FILE.write_text(str(update_id), encoding="utf-8")


def load_state() -> int | None:
    if STATE_FILE.exists():
        text = STATE_FILE.read_text().strip()
        return int(text) if text else None
    return None


def main():
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    offset = load_state()
    if offset:
        offset += 1

    updates = get_updates(offset)
    if not updates:
        print("No new updates.")
        return

    existing = load_existing()
    seen = {make_dedup_key(tx) for tx in existing["transmissions"]}
    new_transmissions = []
    last_update_id = offset or 0

    for update in updates:
        last_update_id = max(last_update_id, update["update_id"])
        post = update.get("channel_post") or update.get("message")
        if not post:
            continue
        text = post.get("text", "")
        if not text:
            continue

        msg_ts = datetime.fromtimestamp(post["date"], tz=MSK)
        parsed = parse_message_text(text, msg_ts)
        for tx in parsed:
            key = make_dedup_key(tx)
            if key not in seen:
                seen.add(key)
                new_transmissions.append(tx)

    save_state(last_update_id)

    if not new_transmissions:
        print("No new transmissions found in updates.")
        return

    print(f"Found {len(new_transmissions)} new transmission(s).")

    existing["transmissions"].extend(new_transmissions)
    existing["transmissions"].sort(key=lambda t: (t["date"], t["time_msk"]))
    existing["meta"]["total_transmissions"] = len(existing["transmissions"])
    if existing["transmissions"]:
        existing["meta"]["date_range"] = {
            "start": existing["transmissions"][0]["date"],
            "end": existing["transmissions"][-1]["date"],
        }

    JSON_OUT.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    append_to_log(new_transmissions)

    for tx in new_transmissions:
        print(f"  + {tx['date']} {tx['time_msk']} {' '.join(tx['words'])}")


if __name__ == "__main__":
    main()
