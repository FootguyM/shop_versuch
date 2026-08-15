"""Datenmodelle, die zwischen Browser, KI, Telegram und UI wandern."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


class Direction(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class DraftStatus(StrEnum):
    PENDING = "pending"       # wartet auf Freigabe
    APPROVED = "approved"     # freigegeben, wird gesendet
    SENT = "sent"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"
    BLOCKED = "blocked"       # vom Sicherheitsfilter gestoppt


class AdStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    DRAFT = "draft"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Message:
    """Eine einzelne Nachricht in einem Konversationsverlauf."""

    thread_id: str
    direction: Direction
    body: str
    sent_at: datetime = field(default_factory=utcnow)
    external_id: str = ""
    id: int | None = None

    @property
    def is_incoming(self) -> bool:
        return self.direction is Direction.INCOMING


@dataclass(slots=True)
class Thread:
    """Eine Konversation mit einem Kontakt im Postfach."""

    thread_id: str
    partner_name: str = ""
    url: str = ""
    ad_title: str = ""
    last_message_at: datetime | None = None
    unread: bool = False
    muted: bool = False
    escalated: bool = False
    escalation_reason: str = ""
    message_count: int = 0
    first_seen_at: datetime = field(default_factory=utcnow)

    @property
    def is_first_contact(self) -> bool:
        return self.message_count <= 1


@dataclass(slots=True)
class Draft:
    """Ein KI-Antwortentwurf, der auf Freigabe wartet."""

    thread_id: str
    text: str
    status: DraftStatus = DraftStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
    decided_at: datetime | None = None
    source_message_id: int | None = None
    model_name: str = ""
    note: str = ""
    id: int | None = None

    @property
    def is_open(self) -> bool:
        return self.status in (DraftStatus.PENDING, DraftStatus.APPROVED)


@dataclass(slots=True)
class Ad:
    """Eine Anzeige im Account."""

    ad_id: str
    title: str = ""
    description: str = ""
    category: str = ""
    price: str = ""
    location: str = ""
    url: str = ""
    status: AdStatus = AdStatus.UNKNOWN
    views: int = 0
    created_at: datetime | None = None
    last_renewed_at: datetime | None = None
    images: list[str] = field(default_factory=list)

    def age_days(self, now: datetime | None = None) -> float | None:
        reference = self.last_renewed_at or self.created_at
        if reference is None:
            return None
        return ((now or utcnow()) - reference).total_seconds() / 86400


@dataclass(slots=True)
class AdTemplate:
    """Vorlage aus ads/*.yaml, aus der eine neue Anzeige entsteht."""

    name: str
    title: str
    description: str
    category: str = ""
    price: str = ""
    location: str = ""
    postal_code: str = ""
    images: list[str] = field(default_factory=list)
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AdTemplate:
        missing = [key for key in ("title", "description") if not data.get(key)]
        if missing:
            raise ValueError(f"Anzeigenvorlage '{name}': Pflichtfeld(er) fehlen: {', '.join(missing)}")
        known = {
            "title", "description", "category", "price",
            "location", "postal_code", "images",
        }
        return cls(
            name=name,
            title=str(data["title"]),
            description=str(data["description"]),
            category=str(data.get("category", "")),
            price=str(data.get("price", "")),
            location=str(data.get("location", "")),
            postal_code=str(data.get("postal_code", "")),
            images=[str(item) for item in data.get("images", []) or []],
            extra_fields={k: v for k, v in data.items() if k not in known},
        )


@dataclass(slots=True)
class SafetyVerdict:
    """Ergebnis des Sicherheitsfilters."""

    allowed: bool
    reason: str = ""
    matched: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> SafetyVerdict:
        return cls(allowed=True)

    @classmethod
    def block(cls, reason: str, matched: list[str] | None = None) -> SafetyVerdict:
        return cls(allowed=False, reason=reason, matched=matched or [])


@dataclass(slots=True)
class BotState:
    """Laufzeitzustand, den UI und Telegram gemeinsam anzeigen."""

    running: bool = False
    paused: bool = False
    logged_in: bool = False
    last_poll_at: datetime | None = None
    next_poll_at: datetime | None = None
    last_error: str = ""
    replies_sent_today: int = 0
    pending_drafts: int = 0
    ai_backend: str = ""
    ai_ready: bool = False
