""".env lesen und schreiben.

Bewusst getrennt von desktop.py: hier haengt nichts an Tkinter, dadurch ist
der Teil testbar, an dem tatsaechlich etwas schiefgehen kann. Und schiefgehen
kann hier einiges - die Datei enthaelt Zugangsdaten, und ein Schreibvorgang,
der Kommentare oder unbekannte Schluessel verschluckt, faellt erst auf, wenn
etwas nicht mehr funktioniert.
"""

from __future__ import annotations

from pathlib import Path


def read_env(path: str | Path) -> dict[str, str]:
    """Schluessel/Wert-Paare aus einer .env lesen."""
    path = Path(path)
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def write_env(path: str | Path, updates: dict[str, str]) -> None:
    """Werte setzen und dabei Kommentare, Reihenfolge und fremde Zeilen erhalten.

    Bekannte Schluessel werden an Ort und Stelle ersetzt, neue hinten
    angehaengt. Ein simples Neuschreiben der ganzen Datei wuerde die
    Erklaerungen aus .env.example vernichten - und die sind der Grund, warum
    man dort spaeter noch durchblickt.
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                result.append(f"{key}={remaining.pop(key)}")
                continue
        result.append(line)

    if remaining:
        if result and result[-1].strip():
            result.append("")
        result += [f"{key}={value}" for key, value in remaining.items()]

    path.write_text("\n".join(result) + "\n", encoding="utf-8")
