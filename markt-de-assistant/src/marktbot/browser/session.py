"""Persistente Browser-Sitzung.

Gearbeitet wird mit einem echten, dauerhaften Chromium-Profil im Ordner
`profiles/`. Das ist der entscheidende Punkt: Cookies, LocalStorage und der
Login-Zustand bleiben zwischen Laeufen erhalten, genau wie bei einem Menschen,
der seinen Browser schliesst und wieder oeffnet. Ein frisch erzeugtes Profil
pro Start waere das auffaelligste Verhalten ueberhaupt.

Hier wird bewusst nichts an der Browser-Identitaet gefaelscht - kein Patchen
von navigator-Eigenschaften, kein Canvas-Rauschen, keine Captcha-Umgehung.
Konfiguriert werden nur Dinge, die ein echter deutscher Nutzer ohnehin haette:
Sprache, Zeitzone, Fenstergroesse und der eigene Internetanschluss.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import TracebackType

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ..config import BrowserConfig
from ..models import utcnow
from .blocking import ResourceBlocker

log = logging.getLogger(__name__)


class BrowserSession:
    """Kapselt Playwright-Start, Kontext und die aktive Seite."""

    def __init__(self, config: BrowserConfig, screenshot_dir: Path) -> None:
        self.config = config
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.blocker = ResourceBlocker(
            blocked_types=config.blocked_resource_types,
            blocked_domains=config.blocked_domains,
            enabled=config.block_resources,
        )

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    # -- Lebenszyklus -------------------------------------------------------

    @property
    def started(self) -> bool:
        return self._context is not None

    @property
    def lock(self) -> asyncio.Lock:
        """Serialisiert Browser-Zugriffe.

        Postfach-Schleife, Telegram-Kommandos und Web-UI laufen im selben
        Event-Loop und greifen auf dieselbe Seite zu. Ohne Lock wuerden sich
        zwei Navigationen gegenseitig zerlegen.
        """
        return self._lock

    async def start(self) -> Page:
        if self._context is not None:
            return await self.page()

        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        launch_kwargs: dict[str, object] = {
            "user_data_dir": str(self.config.profile_dir),
            "headless": self.config.headless,
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "accept_downloads": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                f"--lang={self.config.locale}",
            ],
        }

        if self.config.executable_path:
            launch_kwargs["executable_path"] = self.config.executable_path
            log.info("Nutze System-Chromium: %s", self.config.executable_path)

        if self.config.use_proxy:
            proxy = self.config.proxy.as_playwright()
            if proxy:
                launch_kwargs["proxy"] = proxy
                log.info("Proxy aktiv: %s", self.config.proxy.server)

        log.info(
            "Starte Chromium (headless=%s, profil=%s)",
            self.config.headless,
            self.config.profile_dir,
        )
        self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._context.set_default_timeout(self.config.nav_timeout * 1000)
        self._context.set_default_navigation_timeout(self.config.nav_timeout * 1000)

        if self.config.block_resources:
            await self._context.route("**/*", self.blocker.handle)
            log.info(
                "Bandbreitenfilter aktiv: %s geblockt, dazu %d Tracker-Domains.",
                ", ".join(sorted(self.blocker.blocked_types)) or "(nichts)",
                len(self.blocker.blocked_domains),
            )

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        return self._page

    async def stop(self) -> None:
        if self.config.block_resources and self.blocker.stats.total:
            log.info("Bandbreitenfilter: %s", self.blocker.stats.summary())
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            self._context = None
            self._page = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
            log.info("Browser beendet.")

    async def __aenter__(self) -> BrowserSession:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.stop()

    # -- Seite --------------------------------------------------------------

    async def page(self) -> Page:
        if self._context is None:
            return await self.start()
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        page = await self.page()
        await page.goto(url, wait_until=wait_until)
        return page

    async def screenshot(self, name: str = "", full_page: bool = False) -> Path:
        """Screenshot ablegen und Pfad zurueckgeben (fuer Telegram/UI)."""
        page = await self.page()
        stamp = utcnow().strftime("%Y%m%d-%H%M%S")
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_") or "screen"
        target = self.screenshot_dir / f"{stamp}-{safe_name}.png"
        await page.screenshot(path=str(target), full_page=full_page)
        return target

    async def current_url(self) -> str:
        page = await self.page()
        return page.url

    async def dump_html(self, name: str = "dump") -> Path:
        """Aktuelles DOM sichern - unverzichtbar, wenn Selektoren brechen."""
        page = await self.page()
        stamp = utcnow().strftime("%Y%m%d-%H%M%S")
        target = self.screenshot_dir / f"{stamp}-{name}.html"
        target.write_text(await page.content(), encoding="utf-8")
        return target
