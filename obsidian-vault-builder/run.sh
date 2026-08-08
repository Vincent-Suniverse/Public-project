#!/bin/bash
# ============================================================
# Chat-to-Obsidian Vault Builder
# ============================================================
# Verwendung:
#   1. Lege deine ZIP-Dateien in den input/ Ordner:
#      - input/claude_chats.zip
#      - input/deepseek_chats.zip
#   2. Setze deinen DeepSeek API Key:
#      export DEEPSEEK_API_KEY="sk-..."
#   3. Starte: ./run.sh
#
# Optionen:
#   --dry-run     Kein API-Call, nur lokale Analyse
#   --skip-api    DeepSeek-API ueberspringen
#   --limit N     Nur N Chats verarbeiten (zum Testen)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Pruefe Python ---
if ! command -v python3 &>/dev/null; then
    echo "Python3 nicht gefunden. Bitte installieren."
    exit 1
fi

# --- Installiere Abhaengigkeiten ---
echo "Installiere Abhaengigkeiten..."
pip3 install -q -r requirements.txt

# --- Pruefe API Key ---
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo ""
    echo "WARNUNG: DEEPSEEK_API_KEY nicht gesetzt."
    echo "  Setze ihn mit: export DEEPSEEK_API_KEY='sk-...'"
    echo "  Oder starte mit --dry-run fuer lokale Analyse."
    echo ""
fi

# --- Pruefe Input ---
CLAUDE_ZIP="input/claude_chats.zip"
DEEPSEEK_ZIP="input/deepseek_chats.zip"

if [ ! -f "$CLAUDE_ZIP" ] && [ ! -f "$DEEPSEEK_ZIP" ]; then
    echo ""
    echo "Keine ZIP-Dateien gefunden in input/"
    echo "  Erwartet: $CLAUDE_ZIP"
    echo "  Erwartet: $DEEPSEEK_ZIP"
    echo ""

    # Suche nach alternativen Dateinamen
    FOUND=$(find input/ -name "*.zip" 2>/dev/null || true)
    if [ -n "$FOUND" ]; then
        echo "Gefundene ZIP-Dateien:"
        echo "$FOUND"
        echo ""
        echo "Bitte umbenenne sie zu den erwarteten Namen oder nutze --claude-zip / --deepseek-zip"
    fi
    exit 1
fi

echo ""
echo "============================================"
echo "  Chat-to-Obsidian Vault Builder"
echo "============================================"
echo ""

python3 process_chats.py "$@"

echo ""
echo "Vault bereit: $(realpath ../369Framework)"
echo "Oeffne diesen Ordner als Vault in Obsidian."
