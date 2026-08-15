"""Postfach lesen und beantworten."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import Locator, Page

from ..browser.humanize import Humanizer
from ..browser.session import BrowserSession
from ..models import Direction, Message, Thread, utcnow
from .auth import BASE_URL
from .selectors import SelectorNotFound, Selectors

log = logging.getLogger(__name__)

INBOX_URL = f"{BASE_URL}/postfach/"


class InboxError(RuntimeError):
    pass


def _thread_id_from_url(url: str) -> str:
    """Stabile ID aus der Konversations-URL ziehen."""
    path = urlparse(url).path.rstrip("/")
    if not path:
        return url
    # Bevorzugt ein langes Zahlen-/Hash-Segment, sonst das letzte Pfadstueck.
    segments = [seg for seg in path.split("/") if seg]
    for segment in reversed(segments):
        if re.fullmatch(r"[A-Za-z0-9_-]{6,}", segment):
            return segment
    return segments[-1] if segments else url


class Inbox:
    def __init__(
        self,
        session: BrowserSession,
        selectors: Selectors,
        humanizer: Humanizer,
    ) -> None:
        self.session = session
        self.selectors = selectors
        self.humanizer = humanizer

    # -- Übersicht ----------------------------------------------------------

    async def list_threads(self, limit: int = 30) -> list[Thread]:
        """Konversationsliste im Postfach einlesen."""
        page = await self.session.goto(INBOX_URL)
        await self.humanizer.pause()
        await self.humanizer.browse_page(page)

        items = await self.selectors.find_all(page, "inbox_thread_item")
        if not items:
            dump = await self.session.dump_html("postfach-leer")
            log.warning(
                "Keine Konversationen erkannt. Entweder ist das Postfach leer oder "
                "die Selektoren passen nicht mehr. HTML-Dump: %s", dump
            )
            return []

        threads: list[Thread] = []
        for item in items[:limit]:
            thread = await self._parse_thread_item(page, item)
            if thread:
                threads.append(thread)
        log.info("%d Konversationen im Postfach gefunden.", len(threads))
        return threads

    async def _parse_thread_item(self, page: Page, item: Locator) -> Thread | None:
        try:
            href = await item.get_attribute("href")
            if not href:
                link = item.locator("a[href]").first
                href = await link.get_attribute("href") if await link.count() else None
            if not href:
                return None

            url = urljoin(BASE_URL, href)
            raw_text = (await item.inner_text()).strip()
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

            unread = False
            for candidate in self.selectors.candidates("inbox_unread_marker"):
                try:
                    if await item.locator(candidate).count() > 0:
                        unread = True
                        break
                except Exception:  # noqa: BLE001
                    continue

            return Thread(
                thread_id=_thread_id_from_url(url),
                partner_name=lines[0] if lines else "",
                url=url,
                ad_title=lines[1] if len(lines) > 1 else "",
                unread=unread,
                last_message_at=utcnow(),
            )
        except Exception as exc:  # noqa: BLE001 - ein kaputter Eintrag darf nicht alles stoppen
            log.debug("Konversationseintrag nicht lesbar: %s", exc)
            return None

    # -- Einzelner Verlauf --------------------------------------------------

    async def open_thread(self, thread: Thread) -> Page:
        page = await self.session.goto(thread.url)
        await self.humanizer.pause((1.0, 2.5))
        return page

    async def read_messages(self, thread: Thread, limit: int = 30) -> list[Message]:
        """Nachrichtenverlauf einer Konversation auslesen."""
        page = await self.open_thread(thread)
        bubbles = await self.selectors.find_all(page, "thread_message_item")
        if not bubbles:
            dump = await self.session.dump_html(f"thread-{thread.thread_id}")
            raise InboxError(
                f"Keine Nachrichten in Konversation {thread.thread_id} erkannt. "
                f"Selektoren pruefen. HTML-Dump: {dump}"
            )

        own_markers = self.selectors.candidates("thread_message_own_marker")
        messages: list[Message] = []

        for bubble in bubbles[-limit:]:
            try:
                body = await self._bubble_text(bubble)
                if not body:
                    continue
                is_own = await self._is_own_message(bubble, own_markers)
                messages.append(
                    Message(
                        thread_id=thread.thread_id,
                        direction=Direction.OUTGOING if is_own else Direction.INCOMING,
                        body=body,
                        sent_at=utcnow(),
                        external_id=(await bubble.get_attribute("data-message-id")) or "",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("Nachricht nicht lesbar: %s", exc)

        log.info("Konversation %s: %d Nachrichten gelesen.", thread.thread_id, len(messages))
        return messages

    async def _bubble_text(self, bubble: Locator) -> str:
        for candidate in self.selectors.candidates("thread_message_text"):
            try:
                node = bubble.locator(candidate).first
                if await node.count():
                    text = (await node.inner_text()).strip()
                    if text:
                        return text
            except Exception:  # noqa: BLE001
                continue
        return (await bubble.inner_text()).strip()

    @staticmethod
    async def _is_own_message(bubble: Locator, own_markers: list[str]) -> bool:
        """Eigene Nachricht? Erst ueber Marker-Elemente, dann ueber Klassennamen."""
        for candidate in own_markers:
            try:
                if await bubble.locator(candidate).count() > 0:
                    return True
            except Exception:  # noqa: BLE001
                continue
        class_attr = (await bubble.get_attribute("class") or "").lower()
        return any(token in class_attr for token in ("own", "self", "outgoing", "sent", "right"))

    # -- Antworten ----------------------------------------------------------

    async def send_reply(self, thread: Thread, text: str) -> bool:
        """Antwort in eine Konversation schreiben und absenden."""
        if not text.strip():
            raise InboxError("Leere Antwort wird nicht gesendet.")

        page = await self.open_thread(thread)

        # Erst "lesen", dann tippen - in dieser Reihenfolge macht es ein Mensch.
        history_preview = await self.selectors.text_of(page, "thread_message_item", default="")
        await self.humanizer.read(history_preview or text)

        try:
            field = await self.selectors.find(page, "reply_input", timeout=8000)
        except SelectorNotFound:
            dump = await self.session.dump_html(f"antwortfeld-{thread.thread_id}")
            raise InboxError(
                f"Antwortfeld nicht gefunden (Konversation {thread.thread_id}). "
                f"HTML-Dump: {dump}"
            ) from None

        await self.humanizer.type_text(field, text)
        await self.humanizer.pause_before_submit()

        submit = await self.selectors.find(page, "reply_submit", timeout=5000, required=False)
        if submit is not None:
            await self.humanizer.click(submit)
        else:
            # Manche Chats senden mit Enter.
            await field.press("Enter")

        await self.humanizer.pause((1.5, 3.5))
        sent = await self._verify_sent(page, text)
        if sent:
            log.info("Antwort in Konversation %s gesendet.", thread.thread_id)
        else:
            shot = await self.session.screenshot(f"senden-unklar-{thread.thread_id}")
            log.warning(
                "Antwort abgeschickt, aber im Verlauf nicht wiedergefunden. Screenshot: %s", shot
            )
        return sent

    async def _verify_sent(self, page: Page, text: str) -> bool:
        """Pruefen, ob der Text jetzt im Verlauf steht."""
        probe = " ".join(text.split())[:60]
        if not probe:
            return False
        try:
            content = await page.inner_text("body")
        except Exception:  # noqa: BLE001
            return False
        return " ".join(probe.split()) in " ".join(content.split())
