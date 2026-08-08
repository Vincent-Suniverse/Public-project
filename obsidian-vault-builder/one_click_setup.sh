#!/bin/bash
# ============================================================
# ONE-CLICK Obsidian Vault Builder
# ============================================================
# Fuehre dieses Skript auf deinem PC oder Hetzner-Server aus.
# Es macht ALLES automatisch:
#   1. Findet deine ZIP-Dateien
#   2. Klont die Repos
#   3. Installiert Abhaengigkeiten
#   4. Verarbeitet alle Chats mit DeepSeek-API
#   5. Pusht den fertigen Vault in cexo-engine (privat)
#
# USAGE:
#   curl -sL https://raw.githubusercontent.com/Vincent-Suniverse/Public-project/claude/chat-obsidian-vault-deepseek-j12ga0/obsidian-vault-builder/one_click_setup.sh | bash
#
#   ODER lokal:
#   chmod +x one_click_setup.sh
#   ./one_click_setup.sh
# ============================================================

set -euo pipefail

echo ""
echo "============================================"
echo "  369Framework Obsidian Vault Builder"
echo "  One-Click Setup"
echo "============================================"
echo ""

# --- Konfiguration ---
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-f0ab9972f88e49748d1640d7d78e7977}"
WORK_DIR="${WORK_DIR:-$HOME/vault-builder-workspace}"
BRANCH="claude/chat-obsidian-vault-deepseek-j12ga0"

# --- Arbeitsverzeichnis ---
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
echo "[1/7] Arbeitsverzeichnis: $WORK_DIR"

# --- ZIP-Dateien finden ---
echo "[2/7] Suche ZIP-Dateien..."
CLAUDE_ZIP=""
DEEPSEEK_ZIP=""

SEARCH_DIRS=("$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" "$HOME" "/tmp" "$(pwd)")
for dir in "${SEARCH_DIRS[@]}"; do
    [ -d "$dir" ] || continue

    if [ -z "$CLAUDE_ZIP" ]; then
        found=$(find "$dir" -maxdepth 3 -name "data-91cdc680*batch*.zip" -o -name "claude_chats.zip" -o -name "claude*.zip" 2>/dev/null | head -1 || true)
        [ -n "$found" ] && CLAUDE_ZIP="$found"
    fi

    if [ -z "$DEEPSEEK_ZIP" ]; then
        found=$(find "$dir" -maxdepth 3 -name "deepseek_data*.zip" -o -name "deepseek_chats.zip" -o -name "deepseek*.zip" 2>/dev/null | head -1 || true)
        [ -n "$found" ] && DEEPSEEK_ZIP="$found"
    fi
done

echo "  Claude ZIP:   ${CLAUDE_ZIP:-NICHT GEFUNDEN}"
echo "  DeepSeek ZIP: ${DEEPSEEK_ZIP:-NICHT GEFUNDEN}"

if [ -z "$CLAUDE_ZIP" ] && [ -z "$DEEPSEEK_ZIP" ]; then
    echo ""
    echo "FEHLER: Keine ZIP-Dateien gefunden!"
    echo "Lege sie in ~/Downloads oder starte mit:"
    echo "  CLAUDE_ZIP=/pfad/zur/datei.zip DEEPSEEK_ZIP=/pfad/zur/datei.zip ./one_click_setup.sh"
    exit 1
fi

# --- Repos klonen ---
echo "[3/7] Klone Repositories..."
if [ ! -d "Public-project" ]; then
    git clone -b "$BRANCH" https://github.com/Vincent-Suniverse/Public-project.git
else
    cd Public-project && git fetch origin && git checkout "$BRANCH" && git pull origin "$BRANCH" && cd ..
fi

if [ ! -d "cexo-engine" ]; then
    git clone https://github.com/Vincent-Suniverse/cexo-engine.git
else
    cd cexo-engine && git fetch origin && cd ..
fi

# --- Branch in cexo-engine vorbereiten ---
cd cexo-engine
git checkout -B "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
cd ..

# --- Abhaengigkeiten installieren ---
echo "[4/7] Installiere Python-Abhaengigkeiten..."
pip3 install -q requests pyyaml python-dateutil 2>/dev/null || pip install -q requests pyyaml python-dateutil

# --- ZIPs kopieren ---
echo "[5/7] Kopiere ZIP-Dateien..."
mkdir -p Public-project/obsidian-vault-builder/input
[ -n "$CLAUDE_ZIP" ] && cp "$CLAUDE_ZIP" Public-project/obsidian-vault-builder/input/claude_chats.zip
[ -n "$DEEPSEEK_ZIP" ] && cp "$DEEPSEEK_ZIP" Public-project/obsidian-vault-builder/input/deepseek_chats.zip

# --- Vault-Ziel auf cexo-engine setzen ---
cd Public-project/obsidian-vault-builder

# Patch config to output to cexo-engine
cat > config_local.yaml << 'YAMLEOF'
deepseek:
  api_url: "https://api.deepseek.com/v1/chat/completions"
  model: "deepseek-chat"
  max_tokens: 1024
  temperature: 0.3
  batch_size: 5
  rate_limit_pause: 1.5
  max_retries: 3

vault:
  root: "../../cexo-engine/369Framework"
  structure:
    chats_claude: "Archive-Analysen/Claude"
    chats_deepseek: "Archive-Analysen/DeepSeek"
    concepts: "Konzepte"
    themes: "Themen"
    projects: "Projekte"
    experiments: "Experimente-Bestätigungssuche"
    theories: "Theorienentwicklung-Ideen"
    templates: "Templates"

input:
  claude_zip: "input/claude_chats.zip"
  deepseek_zip: "input/deepseek_chats.zip"

processing:
  min_message_length: 50
  min_messages_per_chat: 2
  max_content_for_analysis: 8000
  progress_file: "input/.progress.json"
  skip_analyzed: true
YAMLEOF

# --- Vault-Struktur im cexo-engine anlegen ---
echo "[6/7] Erstelle Vault-Struktur und verarbeite Chats..."
VAULT_DIR="../../cexo-engine/369Framework"
mkdir -p "$VAULT_DIR"/{Archive-Analysen/{Claude,DeepSeek},Konzepte,Themen,Projekte,Experimente-Bestätigungssuche,Theorienentwicklung-Ideen,Templates,.obsidian}

# Kopiere Vault-Templates
cp -r ../369Framework/.obsidian/* "$VAULT_DIR/.obsidian/" 2>/dev/null || true
cp ../369Framework/Welcome.md "$VAULT_DIR/" 2>/dev/null || true
cp ../369Framework/Templates/* "$VAULT_DIR/Templates/" 2>/dev/null || true

# --- VERARBEITUNG STARTEN ---
export DEEPSEEK_API_KEY
python3 process_chats.py --config config_local.yaml

# --- Git Push ---
echo "[7/7] Pushe Vault in cexo-engine..."
cd ../../cexo-engine
git add 369Framework/
git commit -m "Add 369Framework Obsidian Vault - processed chat archives

Automated processing of Claude and DeepSeek chat exports into
a linked Obsidian vault with YAML frontmatter, concept MOCs,
and theme indexes."
git push -u origin "$BRANCH"

echo ""
echo "============================================"
echo "  FERTIG!"
echo "============================================"
echo ""
echo "Dein Vault liegt in: $(realpath 369Framework)"
echo "Oeffne diesen Ordner als Vault in Obsidian."
echo ""
echo "Gepusht nach: github.com/Vincent-Suniverse/cexo-engine"
echo "Branch: $BRANCH"
echo ""
