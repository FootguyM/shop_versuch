"""Prompt-Bau und Nachbearbeitung der Modellausgabe."""

from __future__ import annotations

import re

from ..config import PersonaConfig, RepliesConfig
from ..models import Direction, Message, Thread
from .base import ChatTurn

SYSTEM_TEMPLATE = """Du schreibst Kurzantworten fuer das Postfach eines Kleinanzeigen-Accounts auf markt.de.

Du antwortest im Namen von: {display_name}

Tonfall und Rolle:
{description}

Feste Regeln:
{rules}

Diese Themen beantwortest du NICHT selbst. Wenn sie aufkommen, schreibst du
einen kurzen Satz, dass du dich spaeter persoenlich dazu meldest:
{handover}

Weitere Vorgaben:
- Schreibe ausschliesslich die Antwort. Keine Anrede-Floskeln wie "Hallo, hier ist der Assistent",
  keine Erklaerungen, keine Anfuehrungszeichen um den Text, keine Signatur.
- Halte dich kurz. Zwei bis drei Saetze sind das Maximum.
- Erfinde keine Details ueber Person, Angebot, Verfuegbarkeit oder Preise.
- Wenn du eine Frage nicht beantworten kannst, sag das offen und kurz.
- Antworte auf Deutsch."""

CONTEXT_TEMPLATE = """Kontext zur Konversation:
- Gespraechspartner: {partner}
- Bezug zur Anzeige: {ad_title}

Bisheriger Verlauf (aelteste zuerst):
{history}

Beantworte die letzte Nachricht des Gespraechspartners."""


def build_system_prompt(persona: PersonaConfig) -> str:
    rules = "\n".join(f"- {rule}" for rule in persona.rules) or "- (keine zusaetzlichen Regeln)"
    handover = (
        "\n".join(f"- {topic}" for topic in persona.handover_topics)
        or "- (keine)"
    )
    return SYSTEM_TEMPLATE.format(
        display_name=persona.display_name,
        description=persona.description or "Freundlich, knapp, natuerlich.",
        rules=rules,
        handover=handover,
    )


def build_turns(
    persona: PersonaConfig,
    thread: Thread,
    history: list[Message],
    max_history: int = 12,
) -> list[ChatTurn]:
    """System-Prompt + Verlauf in eine Chat-Turn-Liste giessen."""
    recent = history[-max_history:]
    lines = []
    for message in recent:
        who = "Ich" if message.direction is Direction.OUTGOING else "Er/Sie"
        body = " ".join(message.body.split())
        lines.append(f"{who}: {body}")

    context = CONTEXT_TEMPLATE.format(
        partner=thread.partner_name or "unbekannt",
        ad_title=thread.ad_title or "unbekannt",
        history="\n".join(lines) or "(kein Verlauf vorhanden)",
    )

    return [
        ChatTurn("system", build_system_prompt(persona)),
        ChatTurn("user", context),
    ]


# --------------------------------------------------------------------------
# Nachbearbeitung
# --------------------------------------------------------------------------

_PREFIXES = re.compile(
    r"^\s*(antwort|reply|assistant|ich schreibe|meine antwort|hier ist die antwort)\s*[:\-–]\s*",
    re.IGNORECASE,
)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def clean_reply(text: str, replies: RepliesConfig, max_chars: int = 600) -> str:
    """Modellausgabe auf etwas trimmen, das man wirklich abschicken kann."""
    cleaned = _THINK_BLOCK.sub("", text).strip()
    cleaned = _PREFIXES.sub("", cleaned)

    # Modelle packen die Antwort gern in Anfuehrungszeichen.
    if len(cleaned) > 1 and cleaned[0] in "\"'„»" and cleaned[-1] in "\"'“«":
        cleaned = cleaned[1:-1].strip()

    # Rollenpraefixe, die aus dem Verlaufsformat zurueckschwappen.
    cleaned = re.sub(r"^(Ich|Er/Sie|Du)\s*:\s*", "", cleaned).strip()

    # Mehrfache Leerzeilen zusammenfassen.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if len(cleaned) > max_chars:
        # An der letzten Satzgrenze vor dem Limit abschneiden.
        cut = cleaned[:max_chars]
        boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        cleaned = (cut[: boundary + 1] if boundary > max_chars // 2 else cut).strip()

    if replies.disclosure and replies.disclosure not in cleaned:
        cleaned = f"{cleaned}\n\n{replies.disclosure}"

    return cleaned.strip()


def to_prompt_string(turns: list[ChatTurn]) -> str:
    """Fallback fuer Backends ohne Chat-Template."""
    parts = []
    for turn in turns:
        label = {"system": "System", "user": "Nutzer", "assistant": "Assistent"}.get(
            turn.role, turn.role
        )
        parts.append(f"### {label}\n{turn.content}")
    parts.append("### Assistent\n")
    return "\n\n".join(parts)
