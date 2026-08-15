"""Zusammenbau: Orchestrator + Telegram + Web-UI in einem Event-Loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from .config import Config
from .core.orchestrator import Orchestrator
from .telegrambot.bot import TelegramInterface
from .ui.server import WebUI

log = logging.getLogger(__name__)


class Application:
    def __init__(self, config: Config, with_ui: bool = True, with_telegram: bool = True) -> None:
        self.config = config
        self.orchestrator = Orchestrator(config)
        self.telegram: TelegramInterface | None = None
        self.ui: WebUI | None = None
        self._shutdown = asyncio.Event()

        if with_telegram and config.telegram.enabled:
            if config.telegram.configured:
                self.telegram = TelegramInterface(config, self.orchestrator)
                self.orchestrator.add_notifier(self.telegram)
            else:
                log.warning(
                    "Telegram ist eingeschaltet, aber TELEGRAM_BOT_TOKEN oder "
                    "TELEGRAM_CHAT_ID fehlen in .env - laeuft ohne Telegram weiter."
                )

        if with_ui and config.ui.enabled:
            self.ui = WebUI(config, self.orchestrator)

    async def run(self) -> None:
        self._install_signal_handlers()

        if self.telegram is not None:
            await self.telegram.start()
            await self.telegram.notify(
                "🤖 Assistent gestartet.\n"
                f"Modus: {'Freigabe erforderlich' if self.config.replies.require_approval else 'Vollautomatik'}\n"
                f"KI-Backend: {self.config.ai.backend}\n"
                "/hilfe zeigt alle Befehle."
            )

        if self.ui is not None:
            await self.ui.start()

        await self.orchestrator.start()

        if self.ui is not None:
            print(
                f"\n  Web-UI: http://{self.config.ui.host}:{self.config.ui.port}\n"
                "  Beenden mit Strg+C\n"
            )

        try:
            await self._shutdown.wait()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        log.info("Fahre herunter ...")
        if self.telegram is not None:
            with contextlib.suppress(Exception):
                await self.telegram.notify("🛑 Assistent wird beendet.")
            await self.telegram.stop()
        if self.ui is not None:
            await self.ui.stop()
        await self.orchestrator.stop()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.request_shutdown)
            except (NotImplementedError, AttributeError):
                # Windows kennt add_signal_handler nicht - dort greift
                # KeyboardInterrupt in run_app().
                pass


async def run_app(config: Config, with_ui: bool = True, with_telegram: bool = True) -> None:
    application = Application(config, with_ui=with_ui, with_telegram=with_telegram)
    try:
        await application.run()
    except KeyboardInterrupt:
        application.request_shutdown()
        await application.shutdown()


def configure_event_loop() -> None:
    """Auf Windows braucht Playwright den Proactor-Loop fuer Subprozesse."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
