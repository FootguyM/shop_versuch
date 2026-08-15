"""SQLite-Persistenz.

Alles laeuft ueber eine Verbindung mit einem Lock. Die Schreibmengen sind
winzig (ein paar Dutzend Zeilen pro Tag), dafuer ist das robust und braucht
keine zusaetzliche Abhaengigkeit auf dem Pi.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import (
    Ad,
    AdStatus,
    Direction,
    Draft,
    DraftStatus,
    Message,
    Thread,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id         TEXT PRIMARY KEY,
    partner_name      TEXT NOT NULL DEFAULT '',
    url               TEXT NOT NULL DEFAULT '',
    ad_title          TEXT NOT NULL DEFAULT '',
    last_message_at   TEXT,
    unread            INTEGER NOT NULL DEFAULT 0,
    muted             INTEGER NOT NULL DEFAULT 0,
    escalated         INTEGER NOT NULL DEFAULT 0,
    escalation_reason TEXT NOT NULL DEFAULT '',
    message_count     INTEGER NOT NULL DEFAULT 0,
    first_seen_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    direction   TEXT NOT NULL,
    body        TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    external_id TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_fingerprint
    ON messages(thread_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, sent_at);

CREATE TABLE IF NOT EXISTS drafts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id         TEXT NOT NULL,
    text              TEXT NOT NULL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    decided_at        TEXT,
    source_message_id INTEGER,
    model_name        TEXT NOT NULL DEFAULT '',
    note              TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status, created_at);

CREATE TABLE IF NOT EXISTS ads (
    ad_id           TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    price           TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'unknown',
    views           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT,
    last_renewed_at TEXT,
    images          TEXT NOT NULL DEFAULT '[]',
    updated_at      TEXT NOT NULL
);

-- Jede ausgehende Aktion wird protokolliert. Das ist gleichzeitig die
-- Grundlage fuer die Rate-Limits.
CREATE TABLE IF NOT EXISTS actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    ref        TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    ok         INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_kind_time ON actions(kind, created_at);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _fingerprint(direction: Direction, body: str, external_id: str) -> str:
    """Stabile Kennung, damit dieselbe Nachricht nicht doppelt landet.

    markt.de liefert nicht ueberall stabile Message-IDs. Gibt es eine, wird
    sie genommen; sonst dient der normalisierte Text als Ersatz.
    """
    if external_id:
        return f"id:{external_id}"
    normalized = " ".join(body.split()).lower()
    return f"{direction.value}:{hash(normalized) & 0xFFFFFFFFFFFF:x}:{len(normalized)}"


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- Threads ------------------------------------------------------------

    def upsert_thread(self, thread: Thread) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO threads (thread_id, partner_name, url, ad_title,
                                     last_message_at, unread, muted, escalated,
                                     escalation_reason, message_count, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    partner_name    = excluded.partner_name,
                    url             = excluded.url,
                    ad_title        = excluded.ad_title,
                    last_message_at = excluded.last_message_at,
                    unread          = excluded.unread
                """,
                (
                    thread.thread_id, thread.partner_name, thread.url, thread.ad_title,
                    _iso(thread.last_message_at), int(thread.unread), int(thread.muted),
                    int(thread.escalated), thread.escalation_reason,
                    thread.message_count, _iso(thread.first_seen_at),
                ),
            )
            self._conn.commit()

    def get_thread(self, thread_id: str) -> Thread | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM threads WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        return self._row_to_thread(row) if row else None

    def list_threads(self, limit: int = 50, only_unread: bool = False) -> list[Thread]:
        query = "SELECT * FROM threads"
        if only_unread:
            query += " WHERE unread = 1"
        query += " ORDER BY COALESCE(last_message_at, first_seen_at) DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, (limit,)).fetchall()
        return [self._row_to_thread(row) for row in rows]

    def set_thread_flags(
        self,
        thread_id: str,
        *,
        unread: bool | None = None,
        muted: bool | None = None,
        escalated: bool | None = None,
        escalation_reason: str | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("unread", unread), ("muted", muted), ("escalated", escalated),
        ):
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(int(value))
        if escalation_reason is not None:
            updates.append("escalation_reason = ?")
            params.append(escalation_reason)
        if not updates:
            return
        params.append(thread_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE threads SET {', '.join(updates)} WHERE thread_id = ?", params
            )
            self._conn.commit()

    @staticmethod
    def _row_to_thread(row: sqlite3.Row) -> Thread:
        return Thread(
            thread_id=row["thread_id"],
            partner_name=row["partner_name"],
            url=row["url"],
            ad_title=row["ad_title"],
            last_message_at=_dt(row["last_message_at"]),
            unread=bool(row["unread"]),
            muted=bool(row["muted"]),
            escalated=bool(row["escalated"]),
            escalation_reason=row["escalation_reason"],
            message_count=row["message_count"],
            first_seen_at=_dt(row["first_seen_at"]) or utcnow(),
        )

    # -- Nachrichten --------------------------------------------------------

    def add_message(self, message: Message) -> int | None:
        """Speichern. Gibt None zurueck, wenn die Nachricht schon bekannt war."""
        fingerprint = _fingerprint(message.direction, message.body, message.external_id)
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO messages
                    (thread_id, direction, body, sent_at, external_id, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.thread_id, message.direction.value, message.body,
                    _iso(message.sent_at), message.external_id, fingerprint,
                ),
            )
            if cursor.rowcount == 0:
                self._conn.commit()
                return None
            self._conn.execute(
                """
                UPDATE threads
                   SET message_count   = message_count + 1,
                       last_message_at = MAX(COALESCE(last_message_at, ''), ?)
                 WHERE thread_id = ?
                """,
                (_iso(message.sent_at), message.thread_id),
            )
            self._conn.commit()
            return cursor.lastrowid

    def add_messages(self, messages: Iterable[Message]) -> list[int]:
        """Mehrere Nachrichten speichern, gibt die IDs der wirklich neuen zurueck."""
        return [new_id for message in messages if (new_id := self.add_message(message))]

    def get_history(self, thread_id: str, limit: int = 20) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM messages WHERE thread_id = ?
                    ORDER BY sent_at DESC, id DESC LIMIT ?
                ) ORDER BY sent_at ASC, id ASC
                """,
                (thread_id, limit),
            ).fetchall()
        return [
            Message(
                id=row["id"],
                thread_id=row["thread_id"],
                direction=Direction(row["direction"]),
                body=row["body"],
                sent_at=_dt(row["sent_at"]) or utcnow(),
                external_id=row["external_id"],
            )
            for row in rows
        ]

    # -- Entwuerfe ----------------------------------------------------------

    def add_draft(self, draft: Draft) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO drafts (thread_id, text, status, created_at, decided_at,
                                    source_message_id, model_name, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.thread_id, draft.text, draft.status.value,
                    _iso(draft.created_at), _iso(draft.decided_at),
                    draft.source_message_id, draft.model_name, draft.note,
                ),
            )
            self._conn.commit()
            draft.id = cursor.lastrowid
            return cursor.lastrowid

    def get_draft(self, draft_id: int) -> Draft | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return self._row_to_draft(row) if row else None

    def list_drafts(self, status: DraftStatus | None = DraftStatus.PENDING, limit: int = 50) -> list[Draft]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    "SELECT * FROM drafts ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM drafts WHERE status = ? ORDER BY created_at ASC LIMIT ?",
                    (status.value, limit),
                ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def has_open_draft(self, thread_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM drafts WHERE thread_id = ? AND status IN (?, ?) LIMIT 1",
                (thread_id, DraftStatus.PENDING.value, DraftStatus.APPROVED.value),
            ).fetchone()
        return row is not None

    def update_draft(
        self,
        draft_id: int,
        *,
        status: DraftStatus | None = None,
        text: str | None = None,
        note: str | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if status is not None:
            updates += ["status = ?", "decided_at = ?"]
            params += [status.value, _iso(utcnow())]
        if text is not None:
            updates.append("text = ?")
            params.append(text)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        if not updates:
            return
        params.append(draft_id)
        with self._lock:
            self._conn.execute(f"UPDATE drafts SET {', '.join(updates)} WHERE id = ?", params)
            self._conn.commit()

    def expire_stale_drafts(self, ttl_hours: int) -> int:
        cutoff = _iso(utcnow() - timedelta(hours=ttl_hours))
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE drafts SET status = ?, decided_at = ? WHERE status = ? AND created_at < ?",
                (DraftStatus.EXPIRED.value, _iso(utcnow()), DraftStatus.PENDING.value, cutoff),
            )
            self._conn.commit()
            return cursor.rowcount

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> Draft:
        return Draft(
            id=row["id"],
            thread_id=row["thread_id"],
            text=row["text"],
            status=DraftStatus(row["status"]),
            created_at=_dt(row["created_at"]) or utcnow(),
            decided_at=_dt(row["decided_at"]),
            source_message_id=row["source_message_id"],
            model_name=row["model_name"],
            note=row["note"],
        )

    # -- Anzeigen -----------------------------------------------------------

    def upsert_ad(self, ad: Ad) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO ads (ad_id, title, description, category, price, location,
                                 url, status, views, created_at, last_renewed_at,
                                 images, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ad_id) DO UPDATE SET
                    title      = excluded.title,
                    category   = excluded.category,
                    price      = excluded.price,
                    location   = excluded.location,
                    url        = excluded.url,
                    status     = excluded.status,
                    views      = excluded.views,
                    updated_at = excluded.updated_at
                """,
                (
                    ad.ad_id, ad.title, ad.description, ad.category, ad.price,
                    ad.location, ad.url, ad.status.value, ad.views,
                    _iso(ad.created_at), _iso(ad.last_renewed_at),
                    json.dumps(ad.images), _iso(utcnow()),
                ),
            )
            self._conn.commit()

    def list_ads(self) -> list[Ad]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM ads ORDER BY updated_at DESC").fetchall()
        return [
            Ad(
                ad_id=row["ad_id"],
                title=row["title"],
                description=row["description"],
                category=row["category"],
                price=row["price"],
                location=row["location"],
                url=row["url"],
                status=AdStatus(row["status"]),
                views=row["views"],
                created_at=_dt(row["created_at"]),
                last_renewed_at=_dt(row["last_renewed_at"]),
                images=json.loads(row["images"]),
            )
            for row in rows
        ]

    def mark_ad_renewed(self, ad_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE ads SET last_renewed_at = ?, updated_at = ? WHERE ad_id = ?",
                (_iso(utcnow()), _iso(utcnow()), ad_id),
            )
            self._conn.commit()

    def delete_ad(self, ad_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM ads WHERE ad_id = ?", (ad_id,))
            self._conn.commit()

    # -- Aktionsprotokoll / Rate-Limits -------------------------------------

    def log_action(self, kind: str, ref: str = "", detail: str = "", ok: bool = True) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO actions (kind, ref, detail, ok, created_at) VALUES (?, ?, ?, ?, ?)",
                (kind, ref, detail, int(ok), _iso(utcnow())),
            )
            self._conn.commit()

    def count_actions_since(self, kind: str, since: datetime, only_ok: bool = True) -> int:
        query = "SELECT COUNT(*) AS n FROM actions WHERE kind = ? AND created_at >= ?"
        params: list[Any] = [kind, _iso(since)]
        if only_ok:
            query += " AND ok = 1"
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return int(row["n"])

    def last_action_at(self, kind: str, only_ok: bool = True) -> datetime | None:
        query = "SELECT MAX(created_at) AS ts FROM actions WHERE kind = ?"
        if only_ok:
            query += " AND ok = 1"
        with self._lock:
            row = self._conn.execute(query, (kind,)).fetchone()
        return _dt(row["ts"]) if row and row["ts"] else None

    def recent_actions(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # -- Key/Value ----------------------------------------------------------

    def set_value(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def get_value(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default
