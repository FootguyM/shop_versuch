"""Benachrichtigungskanal.

Der Orchestrator kennt Telegram nicht direkt. Er redet gegen dieses Interface,
damit sich Telegram, Web-UI und Tests gleichermassen anhaengen koennen.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class Notifier(Protocol):
    async def notify(self, text: str) -> None: ...

    async def notify_photo(self, path: str | Path, caption: str = "") -> None: ...

    async def ask_approval(self, draft_id: int, thread_title: str, text: str) -> None: ...


class NullNotifier:
    """Fallback, wenn kein Kanal konfiguriert ist."""

    async def notify(self, text: str) -> None:
        log.info("[Notify] %s", text)

    async def notify_photo(self, path: str | Path, caption: str = "") -> None:
        log.info("[Notify-Foto] %s (%s)", path, caption)

    async def ask_approval(self, draft_id: int, thread_title: str, text: str) -> None:
        log.info("[Freigabe #%d] %s -> %s", draft_id, thread_title, text)


class FanoutNotifier:
    """Mehrere Kanaele gleichzeitig bedienen, ohne dass einer den anderen killt."""

    def __init__(self, *targets: Notifier) -> None:
        self.targets: list[Notifier] = [t for t in targets if t is not None]

    def add(self, target: Notifier) -> None:
        self.targets.append(target)

    async def _fanout(self, method: str, *args: object, **kwargs: object) -> None:
        if not self.targets:
            return
        results = await asyncio.gather(
            *(getattr(target, method)(*args, **kwargs) for target in self.targets),
            return_exceptions=True,
        )
        for target, result in zip(self.targets, results, strict=True):
            if isinstance(result, Exception):
                log.warning("Benachrichtigung ueber %s fehlgeschlagen: %s",
                            type(target).__name__, result)

    async def notify(self, text: str) -> None:
        await self._fanout("notify", text)

    async def notify_photo(self, path: str | Path, caption: str = "") -> None:
        await self._fanout("notify_photo", path, caption)

    async def ask_approval(self, draft_id: int, thread_title: str, text: str) -> None:
        await self._fanout("ask_approval", draft_id, thread_title, text)
