"""Bindeglied: Verlauf rein, geprueftes Antwort-Textstueck raus."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..models import Direction, Message, SafetyVerdict, Thread
from .base import GenerationError, ReplyBackend
from .huggingface import create_backend
from .prompt import build_turns, clean_reply
from .safety import SafetyFilter

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplyResult:
    text: str = ""
    ok: bool = False
    blocked: bool = False
    reason: str = ""
    model_name: str = ""

    @classmethod
    def block(cls, reason: str, model_name: str = "") -> ReplyResult:
        return cls(ok=False, blocked=True, reason=reason, model_name=model_name)

    @classmethod
    def error(cls, reason: str, model_name: str = "") -> ReplyResult:
        return cls(ok=False, blocked=False, reason=reason, model_name=model_name)


class Responder:
    def __init__(self, config: Config, backend: ReplyBackend | None = None) -> None:
        self.config = config
        self.backend = backend or create_backend(
            config.ai, Path(config.root) / "models"
        )
        self.safety = SafetyFilter(
            enabled=config.safety.enabled,
            extra_blocklist=config.safety.extra_blocklist,
        )

    @property
    def ready(self) -> bool:
        return self.backend.ready

    @property
    def model_name(self) -> str:
        if self.config.ai.backend == "llama_cpp":
            return self.config.ai.llama_filename
        if self.config.ai.backend == "transformers":
            return self.config.ai.transformers_model_id
        if self.config.ai.backend == "hf_inference":
            return self.config.ai.hf_model_id
        return "template"

    async def warmup(self) -> None:
        """Modell vorab laden, damit die erste echte Antwort nicht ewig braucht."""
        await self.backend.ensure_loaded()

    async def close(self) -> None:
        await self.backend.close()

    # -- Hauptweg -----------------------------------------------------------

    def precheck(self, history: list[Message]) -> SafetyVerdict:
        """Sicherheitspruefung der letzten eingehenden Nachricht."""
        last_incoming = next(
            (m for m in reversed(history) if m.direction is Direction.INCOMING), None
        )
        if last_incoming is None:
            return SafetyVerdict.block("Keine eingehende Nachricht zu beantworten.")
        return self.safety.check_incoming(last_incoming.body)

    async def draft_reply(self, thread: Thread, history: list[Message]) -> ReplyResult:
        """Entwurf erzeugen - inklusive Filter davor und danach."""
        verdict = self.precheck(history)
        if not verdict.allowed:
            return ReplyResult.block(verdict.reason, self.model_name)

        turns = build_turns(self.config.persona, thread, history)

        try:
            raw = await self.backend.generate(turns)
        except GenerationError as exc:
            log.error("Textgenerierung fehlgeschlagen: %s", exc)
            return ReplyResult.error(str(exc), self.model_name)

        text = clean_reply(raw, self.config.replies)
        if not text:
            return ReplyResult.error("Das Modell hat einen leeren Text geliefert.", self.model_name)

        outgoing = self.safety.check_outgoing(text)
        if not outgoing.allowed:
            log.warning("Erzeugter Entwurf wurde vom Filter gestoppt: %s", outgoing.reason)
            return ReplyResult.block(outgoing.reason, self.model_name)

        return ReplyResult(text=text, ok=True, model_name=self.model_name)

    def check_manual_text(self, text: str) -> SafetyVerdict:
        """Auch von Hand getippte Antworten laufen durch den Ausgangsfilter."""
        return self.safety.check_outgoing(text)
