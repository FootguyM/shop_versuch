@echo off
REM ===========================================================================
REM  Legt den Assistenten als Ordner auf dem Desktop an und richtet ihn ein.
REM  Einfach doppelklicken.
REM
REM  Diese Datei ist nur der Starter - die eigentliche Arbeit macht das
REM  PowerShell-Skript daneben. Der Umweg ist noetig, weil PowerShell-Dateien
REM  per Doppelklick standardmaessig nicht ausgefuehrt, sondern im Editor
REM  geoeffnet werden.
REM ===========================================================================

title markt.de Assistent - Einrichtung

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_desktop.ps1"

if errorlevel 1 (
    echo.
    echo Die Einrichtung wurde nicht abgeschlossen.
    echo.
    pause
)
