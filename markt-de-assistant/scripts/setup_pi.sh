#!/usr/bin/env bash
# Einrichtung auf einem Raspberry Pi (64 Bit, Raspberry Pi OS Bookworm).
#
#   chmod +x scripts/setup_pi.sh && ./scripts/setup_pi.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== markt.de Assistent - Einrichtung Raspberry Pi ==="

# --- Architektur pruefen ----------------------------------------------------
ARCH="$(uname -m)"
if [ "$ARCH" != "aarch64" ]; then
    echo "WARNUNG: Architektur ist $ARCH, erwartet wurde aarch64 (64-Bit-System)."
    echo "Auf einem 32-Bit-System gibt es fuer Chromium und llama.cpp keine"
    echo "brauchbaren Pakete. Bitte Raspberry Pi OS 64 Bit installieren."
    read -rp "Trotzdem weitermachen? [j/N] " answer
    [ "$answer" = "j" ] || exit 1
fi

TOTAL_MB="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)"
echo "Arbeitsspeicher: ${TOTAL_MB} MB"
if [ "$TOTAL_MB" -lt 3500 ]; then
    echo "HINWEIS: Unter 4 GB RAM laeuft hoechstens ein 1B-Modell sinnvoll."
    echo "         Siehe README, Abschnitt 'Modellwahl'."
fi

# --- Systempakete -----------------------------------------------------------
echo -e "\n--- Systempakete ---"
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    build-essential cmake git \
    chromium chromium-driver \
    libnss3 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2

# --- Auslagerungsdatei vergroessern ----------------------------------------
# Ohne mehr Swap bricht das Kompilieren von llama-cpp-python gerne ab.
CURRENT_SWAP="$(awk '/CONF_SWAPSIZE/ {print $0}' /etc/dphys-swapfile 2>/dev/null || true)"
if [ -f /etc/dphys-swapfile ] && [ "$CURRENT_SWAP" != "CONF_SWAPSIZE=2048" ]; then
    echo -e "\n--- Vergroessere Swap auf 2 GB (fuer den Build) ---"
    sudo dphys-swapfile swapoff
    sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
fi

# --- Virtuelle Umgebung -----------------------------------------------------
echo -e "\n--- Python-Umgebung ---"
[ -d .venv ] || python3 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
pip install --upgrade pip --quiet

echo "Installiere Pakete. llama-cpp-python wird kompiliert - das dauert 10-25 Minuten."
pip install -r requirements.txt

# --- Playwright --------------------------------------------------------------
# Auf ARM gibt es keine fertigen Playwright-Browser. Deshalb wird das
# Chromium aus den Paketquellen benutzt.
echo -e "\n--- Browser ---"
CHROMIUM_PATH="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "$CHROMIUM_PATH" ]; then
    echo "FEHLER: chromium wurde nicht gefunden." >&2
    exit 1
fi
echo "Benutze System-Chromium: $CHROMIUM_PATH"

if ! grep -q PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH .env 2>/dev/null; then
    echo "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=$CHROMIUM_PATH" >> .env
fi

# --- Konfigurationsdateien --------------------------------------------------
[ -f config.yaml ] || { cp config.example.yaml config.yaml; echo "config.yaml angelegt."; }
[ -f .env ] || { cp .env.example .env; echo ".env angelegt."; }

# Auf dem Pi laeuft der Browser ohne Fenster.
sed -i 's/^  headless: false/  headless: true/' config.yaml

cat <<'EOF'

=== Fertig ===

Naechste Schritte:

  1. .env ausfuellen:
       nano .env

  2. Kleineres Modell eintragen (Pi hat weniger RAM als der PC):
       nano config.yaml
     Unter ai.llama_cpp:
       repo_id:  "bartowski/Qwen2.5-3B-Instruct-GGUF"
       filename: "Qwen2.5-3B-Instruct-Q4_K_M.gguf"

  3. Browser-Profil vom PC kopieren (empfohlen - erspart Captcha auf dem Pi):
       scp -r profiles/ pi@raspberrypi:~/markt-de-assistant/

  4. Testlauf:
       .venv/bin/python run.py check

  5. Als Dienst einrichten:
       sudo cp deploy/marktbot.service /etc/systemd/system/
       sudo nano /etc/systemd/system/marktbot.service   # Pfade pruefen
       sudo systemctl daemon-reload
       sudo systemctl enable --now marktbot
       journalctl -u marktbot -f

EOF
