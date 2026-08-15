"""Sicherheitsfilter - laeuft VOR der KI und NACH der KI.

Zweck: Es gibt Nachrichten, auf die kein Automat antworten darf. Wenn jemand
nach Minderjaehrigen fragt, unter Druck setzt, nach Bezahlung ohne Schutz
fragt oder offensichtlich eine Betrugsmasche fahren will, erzeugt der Bot
keinen Entwurf, sondern legt den Thread still und meldet ihn an dich.

Die Muster sind bewusst grob und melden lieber einmal zu viel. Fehlalarme
kosten dich einen Blick ins Telegram, ein uebersehener Fall kann teuer werden.
"""

from __future__ import annotations

import logging
import re

from ..models import SafetyVerdict

log = logging.getLogger(__name__)


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# --------------------------------------------------------------------------
# Eingehende Nachrichten: Themen, bei denen ein Mensch entscheiden muss.
# --------------------------------------------------------------------------

# Sofort blockieren und eskalieren. Kein Entwurf, keine Antwort.
HARD_BLOCK = {
    "Hinweis auf Minderjaehrige": _compile([
        r"\b(minderj[aä]hrig|unter\s?18|nicht\s?volljährig|nicht\s?volljaehrig)\b",
        r"\b(1[0-7])\s?-?\s?(j\.|jahre\w*|j[aä]hrig\w*)",
        r"\b(sch[uü]lerin|schueler|teen(ie)?s?|jungfrau\s+\d{1,2})\b",
        r"\b(loli|jung\s*und\s*unschuldig)\b",
    ]),
    "Zwang, Noetigung, Menschenhandel": _compile([
        r"\b(zwang|gezwungen|erpress\w*|n[oö]tig\w*|drohe|drohung)\b",
        r"\b(pass\s*abgenommen|ausweis\s*einbehalten|schulden\s*abarbeiten)\b",
        r"\b(vermittl\w*\s+m[aä]dchen|f[uü]r\s+mich\s+arbeiten)\b",
    ]),
    "Ungeschuetzt / gesundheitsgefaehrdend": _compile([
        r"\b(ohne\s*(gummi|kondom|schutz)|bareback|\bao\b|a\.o\.)\b",
    ]),
    "Betrug / Geldwaesche": _compile([
        r"\b(western\s*union|moneygram|paysafe|gutschein\s*code|amazon\s*gutschein)\b",
        r"\b(vorkasse|anzahlung\s+per|kaution\s+[uü]berweis\w*)\b",
        # Krypto plus Zahlungskontext - in beide Leserichtungen, weil
        # "Bitcoin senden" und "ich ueberweise dir Bitcoin" beide vorkommen.
        r"\b(bitcoin|btc|krypto)\b.{0,40}\b(send\w*|[uü]berweis\w*|zahl\w*)\b",
        r"\b(send\w*|[uü]berweis\w*|zahl\w*)\b.{0,40}\b(bitcoin|btc|krypto)\b",
        r"\b(ich\s+schicke\s+(dir\s+)?(mehr|zu\s*viel)|[uü]berzahl\w*)\b",
    ]),
}

# Kein Block, aber die KI haelt sich raus - Mensch soll antworten.
HANDOVER = {
    "Geld und Preise": _compile([
        r"\b(preis|kostet|tarif|honorar|rabatt|handel\w*|verhandel\w*)\b",
        r"\b\d+\s?(euro|eur|€)\b",
        r"\b(iban|konto|paypal|[uü]berweisung|bar\s*zahlen)\b",
    ]),
    "Adresse und Treffen": _compile([
        r"\b(adresse|anschrift|wo\s+genau|wo\s+wohnst|anfahrt|hausnummer)\b",
        r"\b(treffen|termin)\b.{0,30}\b(heute|morgen|gleich|jetzt|um\s?\d{1,2})\b",
    ]),
    "Kontaktdaten": _compile([
        r"\b(whatsapp|telegram|signal|snapchat|handynummer|telefonnummer)\b",
        r"\b(\+49|0049|01[5-7]\d)[\s\-/]?\d{3,}",
        r"[\w.\-]+@[\w\-]+\.[a-z]{2,}",
    ]),
    "Verifizierung": _compile([
        r"\b(verifizier\w*|beweis\w*|ausweis|selfie\s+mit|echtheit)\b",
    ]),
}


# --------------------------------------------------------------------------
# Ausgehende Nachrichten: was der Bot nie von sich aus schreiben darf.
# --------------------------------------------------------------------------

OUTGOING_FORBIDDEN = {
    "Bankdaten im Text": _compile([
        r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}(\s?[\dA-Z]{4}){2,}",       # IBAN
        r"\b(iban|bic|kontonummer|bankleitzahl)\b",
    ]),
    "Telefonnummer im Text": _compile([
        r"(\+49|0049|\b0)[\s\-/]?1[5-7]\d[\s\-/]?\d{6,}",
    ]),
    "E-Mail im Text": _compile([
        r"[\w.\-]+@[\w\-]+\.[a-z]{2,}",
    ]),
    "Konkrete Adresse im Text": _compile([
        r"\b[A-ZÄÖÜ][a-zäöüß]+(str(aße|asse)?|weg|platz|allee|gasse)\.?\s+\d{1,4}\b",
        r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+\b",
    ]),
}


def _scan(text: str, groups: dict[str, list[re.Pattern[str]]]) -> tuple[str, list[str]] | None:
    for label, patterns in groups.items():
        hits = [match.group(0) for pattern in patterns if (match := pattern.search(text))]
        if hits:
            return label, hits
    return None


class SafetyFilter:
    def __init__(self, enabled: bool = True, extra_blocklist: list[str] | None = None) -> None:
        self.enabled = enabled
        self._extra = _compile(extra_blocklist or [])

    # -- Eingehend ----------------------------------------------------------

    def check_incoming(self, text: str) -> SafetyVerdict:
        """Darf die KI auf diese Nachricht ueberhaupt antworten?"""
        if not self.enabled or not text.strip():
            return SafetyVerdict.ok()

        hit = _scan(text, HARD_BLOCK)
        if hit:
            label, matched = hit
            log.warning("Sicherheitsfilter blockiert eingehende Nachricht: %s", label)
            return SafetyVerdict.block(
                f"Nicht automatisch beantwortet - Thema '{label}'. Bitte selbst ansehen.",
                matched,
            )

        for pattern in self._extra:
            match = pattern.search(text)
            if match:
                return SafetyVerdict.block(
                    "Nicht automatisch beantwortet - eigenes Blocklist-Muster getroffen.",
                    [match.group(0)],
                )

        hit = _scan(text, HANDOVER)
        if hit:
            label, matched = hit
            return SafetyVerdict.block(
                f"Uebergabe an dich - hier geht es um '{label}'. "
                "Das sollte kein Automat beantworten.",
                matched,
            )

        return SafetyVerdict.ok()

    # -- Ausgehend ----------------------------------------------------------

    def check_outgoing(self, text: str) -> SafetyVerdict:
        """Letzte Kontrolle, bevor Text das Haus verlaesst."""
        if not self.enabled or not text.strip():
            return SafetyVerdict.ok()

        hit = _scan(text, OUTGOING_FORBIDDEN)
        if hit:
            label, matched = hit
            log.warning("Sicherheitsfilter stoppt ausgehende Nachricht: %s", label)
            return SafetyVerdict.block(
                f"Entwurf enthaelt '{label}'. Automatisches Senden gestoppt.",
                matched,
            )

        # Auch der Bot selbst darf die harten Themen nicht anfassen.
        hit = _scan(text, HARD_BLOCK)
        if hit:
            label, matched = hit
            return SafetyVerdict.block(
                f"Entwurf beruehrt das gesperrte Thema '{label}'. Senden gestoppt.",
                matched,
            )

        return SafetyVerdict.ok()
