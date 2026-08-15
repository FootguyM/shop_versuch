"""Zentrale Selektor-Verwaltung.

Wichtig und ehrlich gesagt: markt.de aendert sein Markup ohne Vorwarnung, und
die exakten CSS-Klassen sind nicht stabil. Deshalb ist hier NICHT ein einziger
harter Selektor hinterlegt, sondern pro Element eine Liste von Kandidaten, die
der Reihe nach probiert werden - von "sehr spezifisch" bis "generischer
Fallback ueber Text oder ARIA-Rolle".

Die Liste laesst sich ohne Code-Aenderung in `selectors.yaml` ueberschreiben.
Wenn etwas nicht mehr gefunden wird, meldet der Bot per Telegram, welches
Element fehlt, und legt Screenshot + HTML-Dump ab. Mit `python run.py doctor`
laesst sich pruefen, welche Kandidaten aktuell greifen.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import yaml
from playwright.async_api import Locator, Page

log = logging.getLogger(__name__)


class SelectorNotFound(RuntimeError):
    """Kein Kandidat hat gegriffen."""

    def __init__(self, key: str, candidates: list[str]) -> None:
        self.key = key
        self.candidates = candidates
        super().__init__(
            f"Element '{key}' nicht gefunden. Probiert wurden {len(candidates)} Kandidaten: "
            + ", ".join(candidates[:5])
            + (" ..." if len(candidates) > 5 else "")
        )


# Kandidaten in absteigender Spezifitaet. Playwright-Syntax:
#   "css=..."  CSS
#   "text=..." Textinhalt
#   "role=..." ARIA-Rolle
DEFAULT_SELECTORS: dict[str, list[str]] = {
    # --- Cookie-Banner ---------------------------------------------------
    "cookie_accept": [
        "css=#cmpwelcomebtnyes",
        "css=button#onetrust-accept-btn-handler",
        "css=[data-testid='uc-accept-all-button']",
        "css=button[id*='accept' i]",
        "role=button[name=/alle akzeptieren|akzeptieren|zustimmen|einverstanden/i]",
    ],
    # --- Login -----------------------------------------------------------
    "login_link": [
        "css=a[href*='login']",
        "role=link[name=/anmelden|einloggen|login/i]",
    ],
    "login_username": [
        "css=input[name='username']",
        "css=input[name='email']",
        "css=input[name*='user' i]",
        "css=input[type='email']",
        "css=form input[type='text']",
    ],
    "login_password": [
        "css=input[name='password']",
        "css=input[type='password']",
    ],
    "login_submit": [
        "css=button[type='submit']",
        "css=input[type='submit']",
        "role=button[name=/anmelden|einloggen|login/i]",
    ],
    "login_error": [
        "css=.error, .alert-danger, [class*='error' i]",
        "role=alert",
    ],
    # Zeigt an, dass wir eingeloggt sind.
    "logged_in_marker": [
        "css=a[href*='logout']",
        "css=a[href*='/meins']",
        "css=[class*='usermenu' i]",
        "role=link[name=/mein konto|meine anzeigen|abmelden|logout/i]",
    ],
    # --- Postfach --------------------------------------------------------
    "inbox_thread_list": [
        "css=[class*='conversationList' i]",
        "css=[class*='messageList' i]",
        "css=[data-testid*='conversation' i]",
        "css=main ul",
    ],
    "inbox_thread_item": [
        "css=[class*='conversationList' i] li",
        "css=[class*='conversationItem' i]",
        "css=a[href*='/postfach/']",
        "css=a[href*='conversation']",
    ],
    "inbox_unread_marker": [
        "css=[class*='unread' i]",
        "css=[class*='ungelesen' i]",
        "css=[data-unread='true']",
    ],
    "thread_partner_name": [
        "css=[class*='partnerName' i]",
        "css=[class*='conversationHeader' i] h1, [class*='conversationHeader' i] h2",
        "css=header h1, header h2",
    ],
    "thread_message_item": [
        "css=[class*='messageBubble' i]",
        "css=[class*='chatMessage' i]",
        "css=[class*='message' i][class*='item' i]",
        "css=li[class*='message' i]",
    ],
    # Unterscheidung eigene vs. fremde Nachricht.
    "thread_message_own_marker": [
        "css=[class*='own' i]",
        "css=[class*='self' i]",
        "css=[class*='outgoing' i]",
        "css=[class*='sent' i]",
        "css=[class*='right' i]",
    ],
    "thread_message_text": [
        "css=[class*='messageText' i]",
        "css=[class*='text' i]",
        "css=p",
    ],
    "thread_message_time": [
        "css=time",
        "css=[class*='timestamp' i]",
        "css=[class*='date' i]",
    ],
    "reply_input": [
        "css=textarea[name*='message' i]",
        "css=textarea[placeholder*='nachricht' i]",
        "css=[contenteditable='true']",
        "css=textarea",
    ],
    "reply_submit": [
        "css=button[type='submit']",
        "role=button[name=/senden|absenden|abschicken/i]",
    ],
    # --- Anzeigen --------------------------------------------------------
    "ads_list_item": [
        "css=[class*='adItem' i]",
        "css=[class*='myAds' i] li",
        "css=article[class*='ad' i]",
        "css=a[href*='/anzeige/']",
    ],
    "ad_title": [
        "css=[class*='adTitle' i]",
        "css=h2 a, h3 a",
    ],
    "ad_status": [
        "css=[class*='status' i]",
        "css=[class*='state' i]",
    ],
    "ad_views": [
        "css=[class*='views' i]",
        "css=[class*='aufrufe' i]",
    ],
    "ad_edit_button": [
        "role=link[name=/bearbeiten|aendern/i]",
        "css=a[href*='edit' i]",
    ],
    "ad_renew_button": [
        "role=button[name=/hochschieben|erneuern|aktualisieren|nach oben/i]",
        "css=[class*='bump' i], [class*='renew' i]",
    ],
    "ad_delete_button": [
        "role=button[name=/loeschen|löschen|entfernen/i]",
        "css=[class*='delete' i]",
    ],
    "ad_deactivate_button": [
        "role=button[name=/deaktivieren|pausieren/i]",
        "css=[class*='deactivate' i], [class*='pause' i]",
    ],
    "confirm_button": [
        "role=button[name=/ja|bestaetigen|bestätigen|ok|weiter|fortfahren/i]",
        "css=button[class*='confirm' i]",
    ],
    # --- Anzeige erstellen ----------------------------------------------
    "new_ad_title": [
        "css=input[name*='title' i]",
        "css=input[name*='ueberschrift' i]",
        "css=input[id*='title' i]",
    ],
    "new_ad_description": [
        "css=textarea[name*='description' i]",
        "css=textarea[name*='beschreibung' i]",
        "css=textarea[id*='description' i]",
        "css=textarea",
    ],
    "new_ad_price": [
        "css=input[name*='price' i]",
        "css=input[name*='preis' i]",
    ],
    "new_ad_postal_code": [
        "css=input[name*='zip' i]",
        "css=input[name*='plz' i]",
        "css=input[name*='postal' i]",
    ],
    "new_ad_image_input": [
        "css=input[type='file']",
    ],
    "new_ad_submit": [
        "role=button[name=/anzeige aufgeben|veroeffentlichen|veröffentlichen|aufgeben|weiter/i]",
        "css=button[type='submit']",
    ],
    # --- Captcha / Verifikation ------------------------------------------
    "captcha_marker": [
        "css=iframe[src*='recaptcha']",
        "css=iframe[src*='hcaptcha']",
        "css=[class*='captcha' i]",
        "text=/sicherheitsabfrage|bestaetige.*mensch|bestätige.*mensch/i",
    ],
    "twofa_input": [
        "css=input[name*='code' i]",
        "css=input[name*='otp' i]",
        "css=input[autocomplete='one-time-code']",
    ],
}


class Selectors:
    """Nachschlagewerk mit Fallback-Kette."""

    def __init__(self, overrides: dict[str, list[str]] | None = None) -> None:
        self._map: dict[str, list[str]] = {k: list(v) for k, v in DEFAULT_SELECTORS.items()}
        if overrides:
            for key, value in overrides.items():
                if isinstance(value, str):
                    value = [value]
                # Eigene Kandidaten kommen nach vorne, Defaults bleiben als Netz.
                self._map[key] = list(value) + [
                    c for c in self._map.get(key, []) if c not in value
                ]

    @classmethod
    def load(cls, path: str | Path | None) -> Selectors:
        if path is None:
            return cls()
        path = Path(path)
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        log.info("Selektor-Overrides geladen aus %s (%d Eintraege)", path, len(data))
        return cls(data)

    def candidates(self, key: str) -> list[str]:
        if key not in self._map:
            raise KeyError(f"Unbekannter Selektor-Schluessel: {key}")
        return self._map[key]

    def keys(self) -> Iterable[str]:
        return self._map.keys()

    # -- Auflösung ----------------------------------------------------------

    async def find(
        self,
        page: Page,
        key: str,
        *,
        scope: Locator | None = None,
        timeout: float = 4000,
        required: bool = True,
    ) -> Locator | None:
        """Ersten Kandidaten zurueckgeben, der sichtbar existiert."""
        root = scope if scope is not None else page
        for candidate in self.candidates(key):
            locator = root.locator(candidate).first
            try:
                await locator.wait_for(state="visible", timeout=timeout)
            except Exception:  # noqa: BLE001 - naechster Kandidat
                continue
            log.debug("Selektor '%s' -> %s", key, candidate)
            return locator
        if required:
            raise SelectorNotFound(key, self.candidates(key))
        return None

    async def find_all(
        self,
        page: Page,
        key: str,
        *,
        scope: Locator | None = None,
        min_count: int = 1,
    ) -> list[Locator]:
        """Alle Treffer des ersten Kandidaten, der genug Elemente liefert."""
        root = scope if scope is not None else page
        best: list[Locator] = []
        for candidate in self.candidates(key):
            locator = root.locator(candidate)
            try:
                count = await locator.count()
            except Exception:  # noqa: BLE001
                continue
            if count >= min_count:
                log.debug("Selektor '%s' -> %s (%d Treffer)", key, candidate, count)
                return [locator.nth(i) for i in range(count)]
            if count > len(best):
                best = [locator.nth(i) for i in range(count)]
        return best

    async def exists(self, page: Page, key: str, timeout: float = 1500) -> bool:
        return await self.find(page, key, timeout=timeout, required=False) is not None

    async def text_of(
        self,
        page: Page,
        key: str,
        *,
        scope: Locator | None = None,
        default: str = "",
    ) -> str:
        locator = await self.find(page, key, scope=scope, timeout=2000, required=False)
        if locator is None:
            return default
        try:
            return (await locator.inner_text()).strip()
        except Exception:  # noqa: BLE001
            return default

    async def diagnose(self, page: Page) -> dict[str, str]:
        """Fuer `run.py doctor`: welcher Kandidat greift gerade wo?"""
        report: dict[str, str] = {}
        for key in self._map:
            hit = "-- nicht gefunden --"
            for candidate in self.candidates(key):
                try:
                    if await page.locator(candidate).count() > 0:
                        hit = candidate
                        break
                except Exception:  # noqa: BLE001
                    continue
            report[key] = hit
        return report
