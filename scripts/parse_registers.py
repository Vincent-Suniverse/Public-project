#!/usr/bin/env python3
"""Parse UVB-76 register markdown files into a structured JSON file for the website."""

import json
import re
import sys
from pathlib import Path


def parse_chronological_list(text: str) -> list[dict]:
    transmissions = []
    current_year = None
    current_month = None

    lines = text.split("\n")
    in_code_block = False

    for line in lines:
        header_match = re.match(r"^## (\d{4})-(\d{2})", line)
        if header_match:
            current_year = int(header_match.group(1))
            current_month = int(header_match.group(2))
            in_code_block = False
            continue

        if line.strip() == "```":
            in_code_block = not in_code_block
            continue

        if not in_code_block or not current_year:
            continue

        line = line.strip()
        if not line or line.startswith("#"):
            continue

        tx = parse_transmission_line(line, current_year, current_month)
        if tx:
            transmissions.append(tx)

    return transmissions


def parse_transmission_line(line: str, year: int, month: int) -> dict | None:
    notes_match = re.search(r"\[([^\]]+)\]\s*$", line)
    notes = notes_match.group(1) if notes_match else ""
    if notes_match:
        line = line[: notes_match.start()].strip()

    date_time_match = re.match(
        r"^(\d{1,2})\.(\d{1,2})\.\s+(\d{2}:\d{2}(?:\+\d{2}:\d{2})?)\s+", line
    )
    if not date_time_match:
        return None

    day = int(date_time_match.group(1))
    parsed_month = int(date_time_match.group(2))
    time_str = date_time_match.group(3)

    if parsed_month != month:
        month = parsed_month

    remainder = line[date_time_match.end() :].strip()

    if remainder.startswith("-") or remainder.startswith("TEST"):
        return {
            "date": f"{year}-{month:02d}-{day:02d}",
            "time_msk": time_str,
            "callsigns": [],
            "command_blocks": [],
            "words": [],
            "target_blocks": [],
            "notes": notes or remainder,
            "type": "anomaly",
        }

    callsign_match = re.match(
        r"^([\wЀ-ӿ]+(?:\+[\wЀ-ӿ]+)*)\s+", remainder
    )
    if not callsign_match:
        return None

    callsigns_str = callsign_match.group(1)
    callsigns = callsigns_str.split("+")
    remainder = remainder[callsign_match.end() :].strip()

    command_blocks = []
    cmd_match = re.match(r"^(\d{5}(?:\+\d{5})*)\s+", remainder)
    if cmd_match:
        command_blocks = cmd_match.group(1).split("+")
        remainder = remainder[cmd_match.end() :].strip()

    if not command_blocks:
        single_match = re.match(r"^(\d{5})\s+", remainder)
        if single_match:
            command_blocks = [single_match.group(1)]
            remainder = remainder[single_match.end() :].strip()

    if not command_blocks:
        return None

    words = []
    target_blocks = []

    tokens = remainder.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"^\d{4}$", token):
            if i + 1 < len(tokens) and re.match(r"^\d{4}$", tokens[i + 1]):
                target_blocks.append(f"{token} {tokens[i+1]}")
                i += 2
            else:
                target_blocks.append(token)
                i += 1
        elif re.match(r"^[A-ZА-ЯЁa-zа-яё]", token):
            words.append(token)
            i += 1
        else:
            i += 1

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
        "date": f"{year}-{month:02d}-{day:02d}",
        "time_msk": time_str,
        "callsigns": callsigns,
        "command_blocks": command_blocks,
        "words": words,
        "target_blocks": target_blocks,
        "notes": notes,
        "type": tx_type,
    }


def parse_nachtrag(text: str) -> list[dict]:
    transmissions = []
    lines = text.split("\n")
    in_code_block = False

    current_date_section = None

    for line in lines:
        header_match = re.match(r"^## (\d+\.\d+\.(\d{4})?)", line)
        if header_match:
            raw = header_match.group(1)
            current_date_section = raw
            continue

        if line.strip() == "```":
            in_code_block = not in_code_block
            continue

        if not in_code_block:
            continue

        line = line.strip()
        if not line:
            continue

        time_match = re.match(r"^(\d{2}:\d{2})\s+MSK\s+", line)
        if not time_match:
            continue

        time_str = time_match.group(1)
        remainder = line[time_match.end() :].strip()

        notes_match = re.search(r"\[([^\]]+)\]\s*$", remainder)
        notes = notes_match.group(1) if notes_match else ""
        if notes_match:
            remainder = remainder[: notes_match.start()].strip()

        callsign_match = re.match(r"^([A-ZА-ЯЁ0-9+]+)\s+", remainder)
        if not callsign_match:
            continue

        callsigns = callsign_match.group(1).split("+")
        remainder = remainder[callsign_match.end() :].strip()

        command_blocks = []
        cmd_match = re.match(r"^(\d{5})\s+", remainder)
        if cmd_match:
            command_blocks.append(cmd_match.group(1))
            remainder = remainder[cmd_match.end() :].strip()

        words = []
        target_blocks = []
        tokens = remainder.split()
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if re.match(r"^\d{4}$", token):
                if i + 1 < len(tokens) and re.match(r"^\d{4}$", tokens[i + 1]):
                    target_blocks.append(f"{token} {tokens[i+1]}")
                    i += 2
                else:
                    i += 1
            elif re.match(r"^[A-ZА-ЯЁ]", token):
                words.append(token)
                i += 1
            else:
                i += 1

        year = 2026
        if current_date_section:
            parts = current_date_section.rstrip(".").split(".")
            if len(parts) >= 2:
                day = int(parts[0])
                month = int(parts[1])
                if len(parts) >= 3:
                    year = int(parts[2])
            else:
                continue
        else:
            continue

        tx_type = "single"
        if len(words) >= 4:
            tx_type = "quadruple"
        elif len(words) == 3:
            tx_type = "triple"
        elif len(words) == 2:
            tx_type = "double"

        transmissions.append({
            "date": f"{year}-{month:02d}-{day:02d}",
            "time_msk": time_str,
            "callsigns": callsigns,
            "command_blocks": command_blocks,
            "words": words,
            "target_blocks": target_blocks,
            "notes": notes,
            "type": tx_type,
        })

    return transmissions


def parse_juni_2224(text: str) -> list[dict]:
    transmissions = []
    lines = text.split("\n")

    current_date = None
    in_table = False

    for line in lines:
        if "22. JUNI 2026" in line:
            current_date = "2026-06-22"
        elif "24. JUNI 2026" in line:
            current_date = "2026-06-24"

        if not current_date:
            continue

        if line.strip().startswith("| #"):
            in_table = True
            continue
        if line.strip().startswith("|---"):
            continue

        if in_table and line.strip().startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 6:
                try:
                    time_str = cols[1]
                    tx_type_raw = cols[2]
                    word_raw = cols[3]
                    cmd_block = cols[4]
                    target1 = cols[6] if len(cols) > 6 else ""
                    target2 = cols[8] if len(cols) > 8 else ""

                    words = [w.strip() for w in word_raw.split("/") if w.strip()]
                    targets = []
                    for t1_raw in [target1, target2]:
                        parts = t1_raw.split("/")
                        for p in parts:
                            p = p.strip().replace(" ", "")
                            if re.match(r"^\d{4}$", p):
                                pass
                            elif re.match(r"^\d{8}$", p):
                                targets.append(f"{p[:4]} {p[4:]}")

                    tx_type = "double" if tx_type_raw.lower().startswith("doppel") else "single"

                    transmissions.append({
                        "date": current_date,
                        "time_msk": time_str,
                        "callsigns": ["НЖТИ"],
                        "command_blocks": [cmd_block] if cmd_block else [],
                        "words": words,
                        "target_blocks": targets,
                        "notes": "",
                        "type": tx_type,
                    })
                except (IndexError, ValueError):
                    continue
        elif in_table and not line.strip().startswith("|"):
            in_table = False

    return transmissions


def main():
    data_dir = Path(__file__).parent.parent / "data"
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    all_transmissions = []

    master_file = data_dir / "UVB76_MASTER_REGISTER_V4.md"
    if master_file.exists():
        text = master_file.read_text(encoding="utf-8")
        section_match = re.search(
            r"# 15\. CHRONOLOGISCHE KOMPLETTLISTE", text
        )
        if section_match:
            chrono_text = text[section_match.start() :]
            end_match = re.search(r"\n# 16\.", chrono_text)
            if end_match:
                chrono_text = chrono_text[: end_match.start()]
            txs = parse_chronological_list(chrono_text)
            all_transmissions.extend(txs)
            print(f"Master register: {len(txs)} transmissions parsed")

    nachtrag_file = data_dir / "UVB76_NACHTRAG_28MAI_11JUNI_2026.md"
    if nachtrag_file.exists():
        text = nachtrag_file.read_text(encoding="utf-8")
        txs = parse_nachtrag(text)
        all_transmissions.extend(txs)
        print(f"Nachtrag (28.5-11.6): {len(txs)} transmissions parsed")

    juni_file = data_dir / "UVB76_22_24_JUNI_2026.md"
    if juni_file.exists():
        text = juni_file.read_text(encoding="utf-8")
        txs = parse_juni_2224(text)
        all_transmissions.extend(txs)
        print(f"Juni 22/24: {len(txs)} transmissions parsed")

    all_transmissions.sort(key=lambda t: (t["date"], t["time_msk"]))

    seen = set()
    deduped = []
    for tx in all_transmissions:
        key = (tx["date"], tx["time_msk"], tuple(tx["words"]))
        if key not in seen:
            seen.add(key)
            deduped.append(tx)

    output = {
        "meta": {
            "title": "UVB-76 Transmission Database",
            "description": "Documented UVB-76 voice transmissions (2020-2026)",
            "total_transmissions": len(deduped),
            "date_range": {
                "start": deduped[0]["date"] if deduped else None,
                "end": deduped[-1]["date"] if deduped else None,
            },
            "sources": [
                "Priyom.org Archive (2020-2024)",
                "Vincent Weber Telegram @uvb76logs (Sept 2025 - June 2026)",
            ],
        },
        "transmissions": deduped,
    }

    out_path = docs_dir / "transmissions.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTotal unique transmissions: {len(deduped)}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
