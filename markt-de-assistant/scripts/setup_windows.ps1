# Einrichtung auf einem Windows-PC (zum Testen).
#
# Ausfuehren in PowerShell im Projektverzeichnis:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== markt.de Assistent - Einrichtung Windows ===" -ForegroundColor Cyan

# --- Python pruefen ---------------------------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python nicht gefunden. Installiere Python 3.11 oder neuer von python.org" -ForegroundColor Red
    Write-Host "Wichtig: beim Installieren 'Add Python to PATH' ankreuzen." -ForegroundColor Yellow
    exit 1
}
$version = (python --version)
Write-Host "Gefunden: $version"

# --- Virtuelle Umgebung -----------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "`nLege virtuelle Umgebung an ..."
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

# --- Abhaengigkeiten --------------------------------------------------------
Write-Host "`nInstalliere Pakete (das dauert ein paar Minuten) ..."
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

# --- Browser ----------------------------------------------------------------
Write-Host "`nInstalliere Chromium fuer Playwright ..."
python -m playwright install chromium

# --- Konfigurationsdateien --------------------------------------------------
if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
    Write-Host "config.yaml angelegt." -ForegroundColor Green
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env angelegt." -ForegroundColor Green
}

Write-Host @"

=== Fertig ===

Naechste Schritte:

  1. .env oeffnen und ausfuellen:
       MARKT_USERNAME, MARKT_PASSWORD
       TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

  2. Erst ohne KI testen (kein Modell-Download):
       in config.yaml  ai.backend: "template"
       .\.venv\Scripts\python.exe run.py ai-test

  3. Einmal anmelden, damit das Browser-Profil steht:
       .\.venv\Scripts\python.exe run.py login

  4. Selektoren pruefen:
       .\.venv\Scripts\python.exe run.py doctor

  5. Alles starten:
       .\.venv\Scripts\python.exe run.py

     Web-UI dann unter http://127.0.0.1:8765

"@ -ForegroundColor Cyan
