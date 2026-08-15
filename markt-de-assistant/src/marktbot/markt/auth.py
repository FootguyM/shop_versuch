"""Login und Sitzungspflege.

Der Normalfall ist, dass gar kein Login noetig ist: das persistente Profil hat
das Cookie noch. Erst wenn markt.de wirklich abgemeldet hat, wird das Formular
ausgefuellt. Captcha und 2FA werden nicht umgangen, sondern an den Menschen
weitergereicht - per Telegram-Screenshot und Wartefenster.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from playwright.async_api import Page

from ..browser.humanize import Humanizer
from ..browser.session import BrowserSession
from ..config import Credentials
from .selectors import Selectors

log = logging.getLogger(__name__)

BASE_URL = "https://www.markt.de"
LOGIN_URL = f"{BASE_URL}/login.htm"
ACCOUNT_URL = f"{BASE_URL}/meins/"

# Callback fuer "Mensch bitte uebernehmen" (Screenshot-Pfad, Grund) -> None
InterventionCallback = Callable[[str, str], Awaitable[None]]


class LoginError(RuntimeError):
    pass


class InterventionRequired(LoginError):
    """Captcha oder 2FA - hier muss ein Mensch ran."""


@dataclass(slots=True)
class LoginResult:
    logged_in: bool
    used_existing_session: bool = False
    detail: str = ""


class Authenticator:
    def __init__(
        self,
        session: BrowserSession,
        selectors: Selectors,
        humanizer: Humanizer,
        credentials: Credentials,
        on_intervention: InterventionCallback | None = None,
    ) -> None:
        self.session = session
        self.selectors = selectors
        self.humanizer = humanizer
        self.credentials = credentials
        self.on_intervention = on_intervention

    # -- Oeffentlich --------------------------------------------------------

    async def ensure_logged_in(self, force: bool = False) -> LoginResult:
        """Sicherstellen, dass eine gueltige Sitzung besteht."""
        page = await self.session.page()

        if not force and await self.is_logged_in(page):
            log.info("Bestehende Sitzung aus dem Browser-Profil wird weiterverwendet.")
            return LoginResult(logged_in=True, used_existing_session=True)

        if not self.credentials.configured:
            raise LoginError(
                "Nicht eingeloggt und keine Zugangsdaten hinterlegt. "
                "MARKT_USERNAME und MARKT_PASSWORD in .env setzen - oder einmalig "
                "mit 'python run.py login' im sichtbaren Browser von Hand anmelden."
            )

        return await self._perform_login(page)

    async def is_logged_in(self, page: Page | None = None) -> bool:
        page = page or await self.session.page()
        try:
            if not page.url.startswith(BASE_URL):
                await page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
                await self.dismiss_cookie_banner(page)
            return await self.selectors.exists(page, "logged_in_marker", timeout=4000)
        except Exception as exc:  # noqa: BLE001
            log.debug("Login-Pruefung fehlgeschlagen: %s", exc)
            return False

    async def dismiss_cookie_banner(self, page: Page | None = None) -> bool:
        """Cookie-Dialog wegklicken, falls vorhanden."""
        page = page or await self.session.page()
        button = await self.selectors.find(page, "cookie_accept", timeout=3000, required=False)
        if button is None:
            return False
        await self.humanizer.pause((0.6, 1.8))
        await self.humanizer.click(button)
        await self.humanizer.pause((0.4, 1.2))
        log.info("Cookie-Hinweis bestaetigt.")
        return True

    # -- Intern -------------------------------------------------------------

    async def _perform_login(self, page: Page) -> LoginResult:
        log.info("Melde bei markt.de an ...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self.dismiss_cookie_banner(page)
        await self.humanizer.pause()

        if await self._needs_human(page):
            raise InterventionRequired(
                "Auf der Login-Seite ist eine Sicherheitsabfrage aktiv."
            )

        username_field = await self.selectors.find(page, "login_username")
        password_field = await self.selectors.find(page, "login_password")

        await self.humanizer.type_text(username_field, self.credentials.username)
        await self.humanizer.pause((0.4, 1.3))
        await self.humanizer.type_text(password_field, self.credentials.password)
        await self.humanizer.pause_before_submit()

        submit = await self.selectors.find(page, "login_submit")
        await self.humanizer.click(submit)

        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:  # noqa: BLE001 - manche Seiten werden nie "idle"
            await asyncio.sleep(3)

        # 2FA?
        otp_field = await self.selectors.find(page, "twofa_input", timeout=3000, required=False)
        if otp_field is not None:
            raise InterventionRequired(
                "markt.de verlangt einen Bestaetigungscode (2FA). "
                "Code per Telegram mit '/code 123456' schicken."
            )

        if await self._needs_human(page):
            raise InterventionRequired("Nach dem Absenden erschien eine Sicherheitsabfrage.")

        if await self.is_logged_in(page):
            log.info("Login erfolgreich.")
            return LoginResult(logged_in=True, detail="Frisch angemeldet.")

        error_text = await self.selectors.text_of(page, "login_error")
        dump = await self.session.dump_html("login-fehlgeschlagen")
        raise LoginError(
            f"Login fehlgeschlagen. Seitenmeldung: {error_text or '(keine)'}. "
            f"HTML-Dump: {dump}"
        )

    async def _needs_human(self, page: Page) -> bool:
        """Captcha erkannt? Dann Screenshot raus und Mensch informieren."""
        if not await self.selectors.exists(page, "captcha_marker", timeout=2000):
            return False
        shot = await self.session.screenshot("captcha")
        log.warning("Sicherheitsabfrage erkannt. Screenshot: %s", shot)
        if self.on_intervention:
            await self.on_intervention(
                str(shot),
                "markt.de zeigt eine Sicherheitsabfrage. Bitte im Browser loesen "
                "(oder Profil auf dem PC neu anmelden und auf den Pi kopieren).",
            )
        return True

    async def submit_2fa_code(self, code: str) -> bool:
        """Von Telegram gelieferten 2FA-Code eintragen."""
        page = await self.session.page()
        field = await self.selectors.find(page, "twofa_input", timeout=5000, required=False)
        if field is None:
            raise LoginError("Aktuell wird kein Bestaetigungscode abgefragt.")
        await self.humanizer.type_text(field, code.strip())
        await self.humanizer.pause_before_submit()
        submit = await self.selectors.find(page, "login_submit", required=False)
        if submit is not None:
            await self.humanizer.click(submit)
        else:
            await field.press("Enter")
        await asyncio.sleep(4)
        return await self.is_logged_in(page)
