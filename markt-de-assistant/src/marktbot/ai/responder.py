"""Bindeglied: Verlauf rein, geprueftes Antwort-Textstueck raus."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..models import Direction, Message, SafetyVerdict, Thread
from .base import GenerationError, ReplyBackend
from .disclosure import DisclosureEngine
from .huggingface import create_backend
from .prompt import build_turns, clean_reply
from .safety import SafetyAction, SafetyFilter

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplyResult:
    text: str = ""
    ok: bool = False
    blocked: bool = False
    reason: str = ""
    model_name: str = ""
    # Im Assistenzmodus: was die Offenlegungsschicht am Text geaendert hat.
    disclosure_note: str = ""
    # True, wenn statt einer Modellantwort die feste Weiterleitungsformel kam.
    deflected: bool = False
    # Gesetzt, wenn der Entwurf ein heikles Thema beruehrt und beim Freigeben
    # besonders genau gelesen werden sollte.
    warning: str = ""

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
        self.assistant_mode = config.assistant.enabled
        self.disclosure = (
            DisclosureEngine(
                identification=config.assistant.identification,
                signature=config.assistant.signature,
                identify_on_first_reply=config.assistant.identify_on_first_reply,
            )
            if self.assistant_mode
            else None
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

    @staticmethod
    def _last_incoming(history: list[Message]) -> Message | None:
        return next((m for m in reversed(history) if m.direction is Direction.INCOMING), None)

    @staticmethod
    def _is_first_reply(history: list[Message]) -> bool:
        """Hat der Assistent in dieser Konversation schon einmal geantwortet?"""
        return not any(m.direction is Direction.OUTGOING for m in history)

    async def draft_reply(self, thread: Thread, history: list[Message]) -> ReplyResult:
        """Entwurf erzeugen - inklusive Filter davor und danach."""
        incoming = self._last_incoming(history)
        if incoming is None:
            return ReplyResult.block("Keine eingehende Nachricht zu beantworten.", self.model_name)

        verdict = self.safety.classify_incoming(incoming.body)

        # Harte Blocker gelten in beiden Modi: hier geht nichts Automatisches raus.
        if verdict.is_block:
            return ReplyResult.block(verdict.reason, self.model_name)

        # Heikles Thema. Drei moegliche Wege, je nach Betriebsart.
        warning = ""
        if verdict.action is SafetyAction.HANDOVER:
            if self.assistant_mode and self.config.assistant.deflect_handover_topics:
                # Autonom: feste Weiterleitungsformel, damit der Absender nicht
                # ohne Rueckmeldung bleibt.
                text = self.disclosure.deflection(
                    verdict.label, self.config.assistant.operator_name
                )
                log.info("Assistenzmodus weicht aus (Thema: %s).", verdict.label)
                return ReplyResult(
                    text=text,
                    ok=True,
                    model_name=self.model_name,
                    deflected=True,
                    disclosure_note=(
                        f"Feste Weiterleitungsformel statt Modellantwort ({verdict.label})"
                    ),
                )
            if self.config.replies.require_approval and self.config.replies.draft_sensitive_topics:
                # Mit Freigabe: Entwurf erzeugen, aber deutlich markieren. Es
                # liest ohnehin ein Mensch drueber, bevor etwas rausgeht.
                warning = (
                    f"Heikles Thema: {verdict.label}. "
                    "Bitte genau lesen - hier erfindet das Modell besonders gern."
                )
                log.info("Entwurf zu heiklem Thema '%s' (Freigabe erforderlich).", verdict.label)
            else:
                return ReplyResult.block(
                    verdict.reason + " Das sollte kein Automat beantworten.", self.model_name
                )

        turns = build_turns(
            self.config.persona,
            thread,
            history,
            assistant=self.config.assistant if self.assistant_mode else None,
        )

        try:
            raw = await self.backend.generate(turns)
        except GenerationError as exc:
            log.error("Textgenerierung fehlgeschlagen: %s", exc)
            return ReplyResult.error(str(exc), self.model_name)

        text = clean_reply(raw, self.config.replies)
        if not text:
            return ReplyResult.error("Das Modell hat einen leeren Text geliefert.", self.model_name)

        disclosure_note = ""
        if self.disclosure is not None:
            result = self.disclosure.apply(
                text,
                incoming=incoming.body,
                is_first_reply=self._is_first_reply(history),
            )
            text = result.text
            disclosure_note = result.reason
            if not text:
                # Der ganze Text bestand aus einer Menschbehauptung.
                text = self.disclosure.identification
                disclosure_note = "Antwort war vollstaendig unzulaessig, durch Kennzeichnung ersetzt"

        outgoing = self.safety.check_outgoing(text)
        if not outgoing.allowed:
            log.warning("Erzeugter Entwurf wurde vom Filter gestoppt: %s", outgoing.reason)
            return ReplyResult.block(outgoing.reason, self.model_name)

        return ReplyResult(
            text=text,
            ok=True,
            model_name=self.model_name,
            disclosure_note=disclosure_note,
            warning=warning,
        )

    def check_manual_text(self, text: str) -> SafetyVerdict:
        """Letzte Kontrolle vor dem Senden - auch fuer von Hand getippte Texte."""
        verdict = self.safety.check_outgoing(text)
        if not verdict.allowed:
            return verdict
        if self.disclosure is not None:
            ok, reason = self.disclosure.verify(text)
            if not ok:
                return SafetyVerdict.block(
                    f"{reason} Im Assistenzmodus darf keine Nachricht rausgehen, "
                    "die sich als Mensch ausgibt."
                )
        return SafetyVerdict.ok()
