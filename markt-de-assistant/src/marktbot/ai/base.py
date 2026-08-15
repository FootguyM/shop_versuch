"""Gemeinsame Schnittstelle aller KI-Backends."""

from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class ChatTurn:
    role: str   # "system" | "user" | "assistant"
    content: str


class GenerationError(RuntimeError):
    pass


class ReplyBackend(abc.ABC):
    """Ein Textgenerator.

    Backends laden potenziell mehrere GB Modell und rechnen sekundenlang auf
    der CPU. Deshalb laeuft beides ueber `asyncio.to_thread`, damit der
    Event-Loop (Telegram, Web-UI, Browser) nicht blockiert.
    """

    name: str = "base"

    def __init__(self) -> None:
        self._ready = False
        self._load_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._ready

    async def ensure_loaded(self) -> None:
        if self._ready:
            return
        async with self._load_lock:
            if self._ready:
                return
            await asyncio.to_thread(self._load)
            self._ready = True

    async def generate(self, turns: list[ChatTurn], **kwargs: object) -> str:
        await self.ensure_loaded()
        text = await asyncio.to_thread(self._generate, turns, kwargs)
        return text.strip()

    async def close(self) -> None:
        self._ready = False

    # -- Von Unterklassen zu implementieren ---------------------------------

    @abc.abstractmethod
    def _load(self) -> None:
        """Modell laden. Laeuft in einem Worker-Thread."""

    @abc.abstractmethod
    def _generate(self, turns: list[ChatTurn], options: dict[str, object]) -> str:
        """Antwort erzeugen. Laeuft in einem Worker-Thread."""
