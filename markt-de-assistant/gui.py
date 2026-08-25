#!/usr/bin/env python3
"""Startet die Desktop-Steuerung.

Doppelklick auf "MarktBot starten" ruft am Ende diese Datei auf. Sie kommt mit
der blanken Python-Installation aus - Tkinter liegt bei, alles Weitere kann
aus dem Fenster heraus nachinstalliert werden.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "Tkinter fehlt in dieser Python-Installation.\n\n"
            "Windows: Python von python.org neu installieren und dabei\n"
            "         'tcl/tk and IDLE' angehakt lassen.\n"
            "Linux:   sudo apt install python3-tk\n\n"
            "Ohne Tkinter geht es weiter ueber die Kommandozeile:\n"
            "  python run.py --help",
            file=sys.stderr,
        )
        return 1

    from marktbot.ui.desktop import main as run_gui

    return run_gui(ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
