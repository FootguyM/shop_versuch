"""Menschliches Tempo statt Maschinentakt.

Der Zweck ist doppelt: die Seite wird nicht mit Requests ueberfahren, und der
Bot erzeugt kein Muster wie "exakt alle 60 Sekunden ein Klick". Hier wird
nichts an der Browser-Identitaet manipuliert - es geht nur um Timing.
"""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Locator, Page

from ..config import HumanizeConfig


class Humanizer:
    def __init__(self, config: HumanizeConfig, rng: random.Random | None = None) -> None:
        self.config = config
        self._rng = rng or random.Random()

    # -- Pausen -------------------------------------------------------------

    def _uniform(self, span: tuple[float, float]) -> float:
        return self._rng.uniform(*span)

    async def pause(self, span: tuple[float, float] | None = None) -> None:
        """Kurze Denkpause zwischen zwei Aktionen."""
        await asyncio.sleep(self._uniform(span or self.config.action_delay))

    async def pause_before_submit(self) -> None:
        await asyncio.sleep(self._uniform(self.config.pause_before_submit))

    async def read(self, text: str) -> None:
        """So lange warten, wie ein Mensch zum Lesen braeuchte (gedeckelt)."""
        chunks = max(len(text), 1) / 100
        seconds = chunks * self._uniform(self.config.reading_speed)
        await asyncio.sleep(min(seconds, 45.0))

    def next_interval(self, low: float, high: float) -> float:
        """Abrufintervall mit leichtem Hang zu kuerzeren Werten.

        Gleichverteilung ueber ein 11-Minuten-Fenster sieht auf Dauer
        maschinell aus; ein Beta-artiger Zug wirkt natuerlicher.
        """
        weight = self._rng.betavariate(2.0, 3.0)
        return low + (high - low) * weight

    # -- Eingabe ------------------------------------------------------------

    async def type_text(self, locator: Locator, text: str, clear_first: bool = True) -> None:
        """Zeichenweise tippen, mit variabler Geschwindigkeit und Denkpausen."""
        await locator.click()
        await self.pause((0.2, 0.6))
        if clear_first:
            await locator.fill("")
            await self.pause((0.15, 0.4))

        cpm = self._rng.uniform(self.config.typing_cpm_min, self.config.typing_cpm_max)
        base_delay = 60.0 / max(cpm, 1.0)

        for index, char in enumerate(text):
            await locator.press_sequentially(char, delay=0)
            delay = base_delay * self._rng.uniform(0.55, 1.75)
            # Nach Satzzeichen und an Zeilenumbruechen kurz innehalten.
            if char in ".!?\n":
                delay += self._rng.uniform(0.25, 0.9)
            elif char == " " and self._rng.random() < 0.06:
                delay += self._rng.uniform(0.2, 0.7)
            # Gelegentlich laenger nachdenken.
            if index > 0 and index % self._rng.randint(45, 90) == 0:
                delay += self._rng.uniform(0.6, 2.2)
            await asyncio.sleep(delay)

    async def click(self, locator: Locator) -> None:
        """Klick mit kurzer Vorlaufzeit und Mausbewegung zum Ziel."""
        try:
            await locator.scroll_into_view_if_needed(timeout=5000)
        except Exception:  # noqa: BLE001 - Element ist evtl. schon sichtbar
            pass
        await self.pause((0.3, 1.1))
        await locator.hover()
        await asyncio.sleep(self._rng.uniform(0.08, 0.35))
        await locator.click()

    # -- Seitenverhalten ----------------------------------------------------

    async def browse_page(self, page: Page) -> None:
        """Ein bisschen scrollen, wie beim Ueberfliegen einer Liste."""
        if not self.config.random_scroll:
            return
        for _ in range(self._rng.randint(1, 3)):
            distance = self._rng.randint(200, 700)
            await page.mouse.wheel(0, distance)
            await asyncio.sleep(self._rng.uniform(0.4, 1.6))
        if self._rng.random() < 0.4:
            await page.mouse.wheel(0, -self._rng.randint(100, 400))
            await asyncio.sleep(self._rng.uniform(0.3, 0.9))
