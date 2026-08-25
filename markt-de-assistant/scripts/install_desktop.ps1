# ===========================================================================
#  Installiert den markt.de Assistenten in einen Ordner auf dem Desktop.
#
#  Wird von AUF-DESKTOP-INSTALLIEREN.bat aufgerufen. Direkter Aufruf geht auch:
#      powershell -ExecutionPolicy Bypass -File scripts\install_desktop.ps1
# ===========================================================================

$ErrorActionPreference = "Stop"
$Source = Split-Path $PSScriptRoot -Parent
$Name   = "markt-de-assistant"

function Write-Step($text)  { Write-Host "`n>> $text" -ForegroundColor Cyan }
function Write-Ok($text)    { Write-Host "   $text" -ForegroundColor Green }
function Write-Warn2($text) { Write-Host "   $text" -ForegroundColor Yellow }
function Write-Err($text)   { Write-Host "   $text" -ForegroundColor Red }

Write-Host ""
Write-Host "  markt.de Assistent - Einrichtung" -ForegroundColor White
Write-Host "  ================================="

# --- Python finden ---------------------------------------------------------
Write-Step "Suche Python"

$PythonExe = $null
foreach ($candidate in @("python", "py")) {
    try {
        $version = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $version -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 11) {
                $PythonExe = $candidate
                Write-Ok "$version gefunden"
                break
            }
            Write-Warn2 "$version ist zu alt (mindestens 3.11 noetig)"
        }
    } catch { }
}

if (-not $PythonExe) {
    Write-Err "Kein passendes Python gefunden."
    Write-Host ""
    Write-Host "  Bitte Python 3.11 oder neuer installieren:" -ForegroundColor White
    Write-Host "     https://www.python.org/downloads/"
    Write-Host ""
    Write-Host "  WICHTIG beim Installieren:" -ForegroundColor Yellow
    Write-Host "     - 'Add python.exe to PATH' ankreuzen"
    Write-Host "     - 'tcl/tk and IDLE' angehakt lassen (sonst fehlt die Oberflaeche)"
    Write-Host ""
    exit 1
}

# --- Zielordner ------------------------------------------------------------
# GetFolderPath statt "$HOME\Desktop": bei aktivem OneDrive liegt der Desktop
# woanders, und ein fest gebauter Pfad landet dann im Nichts.
$Desktop = [Environment]::GetFolderPath("Desktop")
$Target  = Join-Path $Desktop $Name

Write-Step "Zielordner: $Target"

if ($Source -eq $Target) {
    Write-Ok "Der Ordner liegt bereits an Ort und Stelle."
}
else {
    if (Test-Path $Target) {
        Write-Warn2 "Der Ordner existiert schon."
        $answer = Read-Host "   Inhalt aktualisieren? Konfiguration, Zugangsdaten und Login bleiben erhalten. [j/N]"
        if ($answer -ne "j") {
            Write-Host "`n  Abgebrochen." -ForegroundColor Yellow
            exit 1
        }
    }
    else {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
    }

    Write-Step "Kopiere Projektdateien"
    # /XD schliesst Ordner aus, die entweder riesig sind oder zum Zielrechner
    # gehoeren und nicht ueberschrieben werden duerfen.
    $robocopyArgs = @(
        $Source, $Target, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
        "/XD", ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
               "profiles", "data", "logs", "models",
        "/XF", ".env", "config.yaml", "config.assistant.yaml"
    )
    $null = robocopy @robocopyArgs
    # Robocopy meldet 0-7 als Erfolg, ab 8 liegt ein echter Fehler vor.
    if ($LASTEXITCODE -ge 8) {
        Write-Err "Kopieren fehlgeschlagen (Robocopy-Code $LASTEXITCODE)."
        exit 1
    }
    $global:LASTEXITCODE = 0
    Write-Ok "Dateien kopiert"
}

Set-Location $Target

# --- Virtuelle Umgebung ----------------------------------------------------
Write-Step "Richte Python-Umgebung ein"
if (-not (Test-Path "$Target\.venv")) {
    & $PythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Err "venv konnte nicht angelegt werden."; exit 1 }
    Write-Ok "Umgebung angelegt"
} else {
    Write-Ok "Umgebung vorhanden"
}

$VenvPython = Join-Path $Target ".venv\Scripts\python.exe"

# --- Pakete ----------------------------------------------------------------
Write-Step "Installiere Pakete (dauert einige Minuten)"
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "Nicht alle Pakete konnten installiert werden."
    Write-Warn2 "Das laesst sich spaeter im Fenster unter 'Einrichtung' nachholen."
} else {
    Write-Ok "Pakete installiert"
}

# --- Browser ---------------------------------------------------------------
Write-Step "Installiere Chromium fuer Playwright"
& $VenvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "Browser fehlt noch - im Fenster unter 'Einrichtung' nachholbar."
} else {
    Write-Ok "Browser bereit"
}

# --- Konfigurationsdateien -------------------------------------------------
Write-Step "Lege Konfiguration an"
foreach ($pair in @(@("config.example.yaml", "config.yaml"), @(".env.example", ".env"))) {
    if ((Test-Path $pair[0]) -and -not (Test-Path $pair[1])) {
        Copy-Item $pair[0] $pair[1]
        Write-Ok "$($pair[1]) erstellt"
    }
}

# --- Starter ---------------------------------------------------------------
Write-Step "Lege Starter an"

# pythonw.exe statt python.exe: sonst haengt an der Oberflaeche dauerhaft ein
# schwarzes Konsolenfenster.
@"
@echo off
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" gui.py
"@ | Set-Content -Path "$Target\MarktBot starten.bat" -Encoding ASCII

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $Desktop "markt.de Assistent.lnk"))
$shortcut.TargetPath       = Join-Path $Target "MarktBot starten.bat"
$shortcut.WorkingDirectory = $Target
$shortcut.IconLocation     = "$VenvPython,0"
$shortcut.Description      = "Steuerung fuer den markt.de Assistenten"
$shortcut.Save()
Write-Ok "Verknuepfung auf dem Desktop angelegt"

# --- Fertig ----------------------------------------------------------------
Write-Host ""
Write-Host "  Fertig." -ForegroundColor Green
Write-Host "  ======="
Write-Host ""
Write-Host "  Ordner:       $Target"
Write-Host "  Starten:      Verknuepfung 'markt.de Assistent' auf dem Desktop"
Write-Host ""
Write-Host "  Naechste Schritte im Fenster:" -ForegroundColor White
Write-Host "     1. Reiter 'Einrichtung' - Zugangsdaten eintragen und speichern"
Write-Host "     2. 'Bei markt.de anmelden' - Captcha einmalig von Hand loesen"
Write-Host "     3. Reiter 'Uebersicht' - Trockenlauf ankreuzen und starten"
Write-Host ""

$answer = Read-Host "  Jetzt oeffnen? [J/n]"
if ($answer -ne "n") {
    Start-Process -FilePath (Join-Path $Target "MarktBot starten.bat") -WorkingDirectory $Target
}
