"""Logging einrichten: Konsole plus rotierende Datei."""

from __future__ import annotations

import logging
import logging.handlers
import re

from .config import LoggingConfig

# Muster, die niemals im Log landen duerfen.
_REDACTIONS = [
    (re.compile(r"(\d{8,10}:[A-Za-z0-9_-]{30,})"), "<TELEGRAM-TOKEN>"),
    (re.compile(r"(hf_[A-Za-z0-9]{20,})"), "<HF-TOKEN>"),
    (re.compile(r"(password[\"'=:\s]+)(\S+)", re.I), r"\1<REDACTED>"),
    (re.compile(r"(passwort[\"'=:\s]+)(\S+)", re.I), r"\1<REDACTED>"),
]


class RedactingFilter(logging.Filter):
    """Zugangsdaten aus Log-Zeilen entfernen.

    Ein Log mit Token darin ist eine Zeitbombe - besonders wenn jemand es zur
    Fehlersuche irgendwo hinschickt.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            message = record.msg
            for pattern, replacement in _REDACTIONS:
                message = pattern.sub(replacement, message)
            record.msg = message
        return True


def setup_logging(config: LoggingConfig) -> None:
    config.file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%d.%m. %H:%M:%S",
    )
    redactor = RedactingFilter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redactor)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        config.file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    # Fremdbibliotheken sind sonst zu geschwaetzig.
    for noisy in ("httpx", "httpcore", "telegram", "urllib3", "asyncio", "uvicorn"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
