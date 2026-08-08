#!/usr/bin/env python3
"""
Chat-to-Obsidian Vault Processor
=================================
Verarbeitet Claude- und DeepSeek-Chat-Exporte in einen Obsidian-Vault
mit YAML-Frontmatter, Tags, Konzepten und Querverweisen.

Nutzt DeepSeek-API fuer die Inhaltsanalyse (guenstig & effektiv).

Usage:
    export DEEPSEEK_API_KEY="sk-..."
    python process_chats.py [--config config.yaml] [--dry-run] [--skip-api]
"""

import json
import os
import re
import sys
import zipfile
import hashlib
import argparse
import time
import traceback
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import yaml
import requests
from dateutil import parser as dateparser

ANALYSIS_PROMPT_DE = """Analysiere den folgenden Chat-Verlauf und extrahiere strukturierte Informationen.

CHAT-INHALT:
{content}

Antworte NUR als valides JSON (kein Markdown, keine Erklaerung):
{{
  "title": "Kurzer, aussagekraeftiger Titel auf Deutsch",
  "topics": ["Hauptthema1", "Unterthema2"],
  "concepts": ["Konzept1", "Konzept2", "Konzept3"],
  "tags": ["tag-eins", "tag-zwei"],
  "summary": "2-3 Saetze Zusammenfassung auf Deutsch",
  "related_topics": ["Verwandtes-Thema1", "Verwandtes-Thema2"],
  "category": "eine von: theorie|experiment|projekt|code|forschung|diskussion|idee"
}}"""


def load_config(config_path):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_progress(progress_file):
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            return json.load(f)
    return {"processed": [], "failed": [], "stats": {"total": 0, "done": 0, "skipped": 0}}


def save_progress(progress_file, progress):
    os.makedirs(os.path.dirname(progress_file), exist_ok=True)
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


# ---------------------------------------------------------------------------
# Chat export parsers
# ---------------------------------------------------------------------------

def extract_zip(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_to)
    return extract_to


def find_json_files(directory):
    jsons = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".json"):
                jsons.append(os.path.join(root, f))
    return sorted(jsons)


def parse_message_content(content):
    """Normalize message content from various formats to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(p.get("text", p.get("value", "")))
        return " ".join(parts)
    if isinstance(content, dict):
        return content.get("text", content.get("value", str(content)))
    return str(content)


def parse_claude_conversations(json_path):
    """Parse a Claude export JSON file. Handles multiple known formats."""
    with open(json_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    conversations = []

    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        conv = _parse_single_claude_conv(item)
        if conv and conv["messages"]:
            conversations.append(conv)

    return conversations


def _parse_single_claude_conv(item):
    title = item.get("name", item.get("title", "Untitled"))
    uuid = item.get("uuid", item.get("id", hashlib.md5(json.dumps(item, default=str)[:200].encode()).hexdigest()))
    created = item.get("created_at", item.get("create_time", ""))
    updated = item.get("updated_at", item.get("update_time", ""))

    messages = []
    raw = item.get("chat_messages", item.get("messages", []))

    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, dict) and "message" in val and val["message"]:
                msg = val["message"]
                content = parse_message_content(msg.get("content", ""))
                role = msg.get("role", "unknown")
                if isinstance(msg.get("author"), dict):
                    role = msg["author"].get("role", role)
                if content.strip():
                    messages.append({"role": role, "content": content.strip()})
    elif isinstance(raw, list):
        for msg in raw:
            if not isinstance(msg, dict):
                continue
            content = parse_message_content(msg.get("content", msg.get("text", "")))
            role = msg.get("role", msg.get("sender", "unknown"))
            if content.strip():
                messages.append({"role": role, "content": content.strip()})

    return {
        "source": "claude",
        "title": title,
        "uuid": str(uuid),
        "created_at": str(created),
        "updated_at": str(updated),
        "messages": messages,
    }


def parse_deepseek_conversations(json_path):
    """Parse a DeepSeek export JSON file."""
    with open(json_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    conversations = []
    items = data if isinstance(data, list) else [data]

    for item in items:
        if not isinstance(item, dict):
            continue

        title = item.get("title", item.get("name", "Untitled"))
        uuid = item.get("id", item.get("uuid", hashlib.md5(json.dumps(item, default=str)[:200].encode()).hexdigest()))
        created = item.get("created_at", item.get("create_time", item.get("createdAt", "")))
        updated = item.get("updated_at", item.get("update_time", item.get("updatedAt", "")))

        messages = []
        raw = item.get("messages", item.get("chat_messages", item.get("items", [])))

        if isinstance(raw, list):
            for msg in raw:
                if not isinstance(msg, dict):
                    continue
                content = parse_message_content(msg.get("content", msg.get("text", "")))
                role = msg.get("role", msg.get("sender", "unknown"))
                if content.strip():
                    messages.append({"role": role, "content": content.strip()})

        if messages:
            conversations.append({
                "source": "deepseek",
                "title": title,
                "uuid": str(uuid),
                "created_at": str(created),
                "updated_at": str(updated),
                "messages": messages,
            })

    return conversations


# ---------------------------------------------------------------------------
# DeepSeek API analysis
# ---------------------------------------------------------------------------

def analyze_with_deepseek(conversation, config, dry_run=False):
    """Send conversation to DeepSeek API for theme/concept extraction."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("  [WARN] DEEPSEEK_API_KEY nicht gesetzt, ueberspringe API-Analyse")
        return fallback_analysis(conversation)

    if dry_run:
        return fallback_analysis(conversation)

    content_parts = []
    for msg in conversation["messages"]:
        role_label = "User" if msg["role"] in ("user", "human") else "Assistant"
        text = msg["content"][:2000]
        content_parts.append(f"[{role_label}]: {text}")

    max_len = config.get("processing", {}).get("max_content_for_analysis", 8000)
    chat_text = "\n\n".join(content_parts)[:max_len]
    prompt = ANALYSIS_PROMPT_DE.format(content=chat_text)

    ds_cfg = config.get("deepseek", {})
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ds_cfg.get("model", "deepseek-chat"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": ds_cfg.get("max_tokens", 1024),
        "temperature": ds_cfg.get("temperature", 0.3),
    }

    retries = ds_cfg.get("max_retries", 3)
    for attempt in range(retries):
        try:
            resp = requests.post(
                ds_cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions"),
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            result_text = resp.json()["choices"][0]["message"]["content"]
            result_text = re.sub(r"```(?:json)?\s*", "", result_text).strip().rstrip("`")
            return json.loads(result_text)
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            wait = 2 ** (attempt + 1)
            print(f"  [RETRY {attempt+1}/{retries}] {e} — warte {wait}s")
            time.sleep(wait)

    print("  [FALLBACK] API fehlgeschlagen, nutze lokale Analyse")
    return fallback_analysis(conversation)


def fallback_analysis(conversation):
    """Basic local analysis when API is unavailable."""
    all_text = " ".join(m["content"] for m in conversation["messages"])
    words = re.findall(r"\b[A-Za-zÄÖÜäöüß]{4,}\b", all_text)
    freq = defaultdict(int)
    for w in words:
        freq[w.lower()] += 1

    stopwords = {
        "dass", "wird", "werden", "haben", "sein", "eine", "einen", "einem",
        "einer", "nicht", "auch", "sich", "kann", "sind", "dies", "diese",
        "dieser", "diesem", "diesen", "aber", "oder", "wenn", "dann", "noch",
        "schon", "hier", "dort", "weil", "nach", "ueber", "unter", "with",
        "that", "this", "from", "have", "your", "they", "their", "would",
        "could", "should", "about", "which", "there", "been", "more", "some",
        "into", "than", "other", "what", "just", "like", "will", "each",
    }
    top = sorted(
        [(w, c) for w, c in freq.items() if w not in stopwords and c > 1],
        key=lambda x: -x[1],
    )[:10]

    return {
        "title": conversation.get("title", "Untitled"),
        "topics": [w for w, _ in top[:3]],
        "concepts": [w for w, _ in top[:8]],
        "tags": [re.sub(r"[^a-z0-9-]", "", w.lower()) for w, _ in top[:5]],
        "summary": f"Chat mit {len(conversation['messages'])} Nachrichten.",
        "related_topics": [],
        "category": "diskussion",
    }


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = name[:120]
    return name or "Untitled"


def parse_date(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, (int, float)):
            return datetime.fromtimestamp(date_str)
        return dateparser.parse(str(date_str))
    except (ValueError, TypeError):
        return None


def generate_chat_markdown(conversation, analysis):
    """Generate an Obsidian-compatible markdown file from a conversation."""
    date = parse_date(conversation["created_at"])
    date_str = date.strftime("%Y-%m-%d") if date else "unknown"
    date_full = date.strftime("%Y-%m-%d %H:%M") if date else "unknown"

    tags = analysis.get("tags", [])
    concepts = analysis.get("concepts", [])
    topics = analysis.get("topics", [])
    related = analysis.get("related_topics", [])
    category = analysis.get("category", "diskussion")

    concept_links = " ".join([f"[[{c}]]" for c in concepts[:8]])
    related_links = " ".join([f"[[{r}]]" for r in related[:5]])

    tag_list = "\n".join([f"  - {t}" for t in tags]) if tags else "  - untagged"

    lines = [
        "---",
        f'title: "{analysis.get("title", conversation.get("title", "Untitled"))}"',
        f"date: {date_str}",
        f'source: {conversation["source"]}',
        f"category: {category}",
        f'uuid: "{conversation["uuid"]}"',
        "tags:",
        tag_list,
        "concepts:",
    ]
    for c in concepts[:8]:
        lines.append(f"  - {c}")
    lines += [
        "---",
        "",
        f"# {analysis.get('title', conversation.get('title', 'Untitled'))}",
        "",
        f"**Datum:** {date_full}",
        f"**Quelle:** {conversation['source'].capitalize()}",
        f"**Kategorie:** {category}",
        f"**Nachrichten:** {len(conversation['messages'])}",
        "",
        "## Zusammenfassung",
        "",
        analysis.get("summary", "Keine Zusammenfassung verfuegbar."),
        "",
        "## Konzepte",
        "",
        concept_links if concept_links else "Keine Konzepte extrahiert.",
        "",
        "## Verwandte Themen",
        "",
        related_links if related_links else "Keine Verknuepfungen.",
        "",
        "## Chat-Verlauf",
        "",
    ]

    for msg in conversation["messages"]:
        role = msg["role"]
        if role in ("user", "human"):
            prefix = "**User:**"
        elif role in ("assistant", "bot"):
            prefix = "**Assistant:**"
        else:
            prefix = f"**{role}:**"
        lines.append(f"> {prefix}")
        content = msg["content"]
        if len(content) > 3000:
            content = content[:3000] + "\n\n[... gekuerzt ...]"
        for cline in content.split("\n"):
            lines.append(f"> {cline}")
        lines.append("")

    return "\n".join(lines)


def generate_concept_note(concept_name, referencing_files):
    """Generate a MOC (Map of Content) note for a concept."""
    refs = "\n".join([f"- [[{f}]]" for f in referencing_files])
    return f"""---
title: "{concept_name}"
type: concept
aliases:
  - {concept_name.lower()}
---

# {concept_name}

## Referenzen

{refs}

## Notizen

"""


def generate_theme_note(theme_name, referencing_files, subconcepts):
    """Generate a theme index note."""
    refs = "\n".join([f"- [[{f}]]" for f in referencing_files])
    concepts = " ".join([f"[[{c}]]" for c in subconcepts])
    return f"""---
title: "{theme_name}"
type: theme
---

# {theme_name}

## Konzepte

{concepts}

## Chats

{refs}

## Analyse

"""


def generate_master_index(stats, themes, concepts):
    """Generate the 00_Master_index.md file."""
    theme_links = "\n".join([f"- [[{t}]]" for t in sorted(themes)])
    concept_links = "\n".join([f"- [[{c}]]" for c in sorted(concepts)[:50]])

    return f"""---
title: "Master Index"
type: index
date: {datetime.now().strftime('%Y-%m-%d')}
---

# 369Framework — Master Index

## Statistiken

| Metrik | Wert |
|--------|------|
| Chats gesamt | {stats['total']} |
| Claude-Chats | {stats.get('claude', 0)} |
| DeepSeek-Chats | {stats.get('deepseek', 0)} |
| Konzepte extrahiert | {len(concepts)} |
| Themen identifiziert | {len(themes)} |
| Verarbeitet am | {datetime.now().strftime('%Y-%m-%d %H:%M')} |

## Themen

{theme_links}

## Top-Konzepte

{concept_links}

## Ordnerstruktur

- **Archive-Analysen/** — Alle verarbeiteten Chats
  - **Claude/** — Claude-Chat-Verlaeufe
  - **DeepSeek/** — DeepSeek-Chat-Verlaeufe
- **Konzepte/** — Map of Content (MOC) fuer Schluesselkonzepte
- **Themen/** — Thematische Uebersichten
- **Projekte/** — Projektbezogene Sammlungen
- **Experimente-Bestaetigungssuche/** — Experimentelle Analysen
- **Theorienentwicklung-Ideen/** — Theoretische Entwicklungen

## Navigation

Nutze die Obsidian-Graph-Ansicht um Verbindungen zu visualisieren.
Alle Chats sind ueber Konzepte und Themen verknuepft.
"""


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Chat-to-Obsidian Vault Processor")
    parser.add_argument("--config", default="config.yaml", help="Pfad zur Konfiguration")
    parser.add_argument("--dry-run", action="store_true", help="Kein API-Call, nur lokale Analyse")
    parser.add_argument("--skip-api", action="store_true", help="Ueberspringe DeepSeek-API")
    parser.add_argument("--claude-zip", help="Pfad zur Claude-ZIP")
    parser.add_argument("--deepseek-zip", help="Pfad zur DeepSeek-ZIP")
    parser.add_argument("--limit", type=int, default=0, help="Max Chats verarbeiten (0 = alle)")
    args = parser.parse_args()

    config = load_config(args.config)
    vault_root = Path(config["vault"]["root"])
    progress_file = config["processing"]["progress_file"]
    progress = load_progress(progress_file)

    claude_zip = args.claude_zip or config["input"]["claude_zip"]
    deepseek_zip = args.deepseek_zip or config["input"]["deepseek_zip"]

    all_conversations = []

    # --- Extract and parse ---
    for zip_path, source, parser_fn in [
        (claude_zip, "claude", parse_claude_conversations),
        (deepseek_zip, "deepseek", parse_deepseek_conversations),
    ]:
        if not os.path.exists(zip_path):
            print(f"[SKIP] {zip_path} nicht gefunden")
            continue

        print(f"\n{'='*60}")
        print(f"Entpacke {zip_path}...")
        extract_dir = zip_path.replace(".zip", "_extracted")
        extract_zip(zip_path, extract_dir)

        json_files = find_json_files(extract_dir)
        print(f"  {len(json_files)} JSON-Datei(en) gefunden")

        for jf in json_files:
            try:
                convs = parser_fn(jf)
                print(f"  {jf}: {len(convs)} Konversation(en)")
                all_conversations.extend(convs)
            except Exception as e:
                print(f"  [ERROR] {jf}: {e}")
                traceback.print_exc()

    if not all_conversations:
        print("\nKeine Konversationen gefunden. Bitte ZIP-Dateien bereitstellen.")
        print(f"  Erwartet: {claude_zip}")
        print(f"  Erwartet: {deepseek_zip}")
        sys.exit(1)

    # Filter short/empty conversations
    min_msgs = config["processing"]["min_messages_per_chat"]
    min_len = config["processing"]["min_message_length"]
    filtered = []
    for conv in all_conversations:
        substantial = [m for m in conv["messages"] if len(m["content"]) >= min_len]
        if len(substantial) >= min_msgs:
            filtered.append(conv)

    print(f"\n{len(all_conversations)} Chats geladen, {len(filtered)} nach Filter")

    if args.limit > 0:
        filtered = filtered[:args.limit]
        print(f"  Limitiert auf {args.limit} Chats")

    # --- Analyze and generate ---
    concept_index = defaultdict(list)
    theme_index = defaultdict(list)
    stats = {"total": len(filtered), "claude": 0, "deepseek": 0}

    ds_cfg = config.get("deepseek", {})
    rate_pause = ds_cfg.get("rate_limit_pause", 1.5)

    for i, conv in enumerate(filtered):
        uid = conv["uuid"]
        source = conv["source"]
        stats[source] = stats.get(source, 0) + 1

        if config["processing"]["skip_analyzed"] and uid in progress["processed"]:
            print(f"  [{i+1}/{len(filtered)}] SKIP (bereits verarbeitet): {conv['title'][:60]}")
            continue

        print(f"\n  [{i+1}/{len(filtered)}] {source.upper()}: {conv['title'][:60]}")

        # Analyze
        if args.skip_api or args.dry_run:
            analysis = fallback_analysis(conv)
        else:
            analysis = analyze_with_deepseek(conv, config, dry_run=args.dry_run)
            time.sleep(rate_pause)

        # Generate markdown
        md_content = generate_chat_markdown(conv, analysis)
        safe_title = sanitize_filename(analysis.get("title", conv["title"]))
        date = parse_date(conv["created_at"])
        date_prefix = date.strftime("%Y-%m-%d") if date else "undated"
        filename = f"{date_prefix}_{safe_title}.md"

        subdir = config["vault"]["structure"][f"chats_{source}"]
        out_path = vault_root / subdir / filename
        os.makedirs(out_path.parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # Track concepts and themes
        file_ref = f"{subdir}/{filename}".replace(".md", "")
        for concept in analysis.get("concepts", []):
            concept_index[concept].append(file_ref)
        for topic in analysis.get("topics", []):
            theme_index[topic].append(file_ref)
        for related in analysis.get("related_topics", []):
            theme_index[related].append(file_ref)

        progress["processed"].append(uid)
        progress["stats"]["done"] = len(progress["processed"])
        if (i + 1) % 10 == 0:
            save_progress(progress_file, progress)

    # --- Generate concept MOCs ---
    print(f"\n{'='*60}")
    print(f"Generiere {len(concept_index)} Konzept-Notizen...")
    concepts_dir = vault_root / config["vault"]["structure"]["concepts"]
    os.makedirs(concepts_dir, exist_ok=True)
    for concept, refs in concept_index.items():
        safe = sanitize_filename(concept)
        note = generate_concept_note(concept, refs)
        with open(concepts_dir / f"{safe}.md", "w", encoding="utf-8") as f:
            f.write(note)

    # --- Generate theme indexes ---
    print(f"Generiere {len(theme_index)} Themen-Notizen...")
    themes_dir = vault_root / config["vault"]["structure"]["themes"]
    os.makedirs(themes_dir, exist_ok=True)
    for theme, refs in theme_index.items():
        safe = sanitize_filename(theme)
        subconcepts = []
        for ref in refs:
            for c in concept_index:
                if ref in concept_index[c]:
                    subconcepts.append(c)
        note = generate_theme_note(theme, refs, list(set(subconcepts))[:10])
        with open(themes_dir / f"{safe}.md", "w", encoding="utf-8") as f:
            f.write(note)

    # --- Generate master index ---
    print("Generiere Master-Index...")
    master = generate_master_index(stats, list(theme_index.keys()), list(concept_index.keys()))
    with open(vault_root / "00_Master_index.md", "w", encoding="utf-8") as f:
        f.write(master)

    # --- Save final progress ---
    progress["stats"] = stats
    save_progress(progress_file, progress)

    print(f"\n{'='*60}")
    print(f"FERTIG!")
    print(f"  Chats verarbeitet: {stats['total']}")
    print(f"  Claude: {stats.get('claude', 0)}")
    print(f"  DeepSeek: {stats.get('deepseek', 0)}")
    print(f"  Konzepte: {len(concept_index)}")
    print(f"  Themen: {len(theme_index)}")
    print(f"  Vault: {vault_root.resolve()}")
    print(f"\nOeffne den Ordner '{vault_root.resolve()}' als Vault in Obsidian.")


if __name__ == "__main__":
    main()
