"""Der Kern: verbindet Browser, KI, Speicher und Benachrichtigungen.

Telegram-Bot und Web-UI rufen ausschliesslich Methoden dieser Klasse auf. Der
gesamte Browser-Zugriff ist ueber `session.lock` serialisiert, damit sich
Hintergrundschleife und manuelle Kommandos nicht in die Quere kommen.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from ..ai.responder import Responder
from ..browser.humanize import Humanizer
from ..browser.session import BrowserSession
from ..config import Config
from ..markt.ads import AdManager, load_templates
from ..markt.auth import Authenticator, InterventionRequired, LoginError
from ..markt.inbox import Inbox
from ..markt.selectors import Selectors
from ..models import (
    Ad,
    AdTemplate,
    BotState,
    Direction,
    Draft,
    DraftStatus,
    Message,
    Thread,
    utcnow,
)
from ..storage import Storage
from .notifier import FanoutNotifier, Notifier
from .ratelimit import ACTION_AD_CREATE, ACTION_AD_RENEW, ACTION_REPLY, RateLimiter

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.storage = Storage(config.db_path)
        self.selectors = Selectors.load(config.root / "selectors.yaml")
        self.humanizer = Humanizer(config.humanize)
        self.session = BrowserSession(config.browser, config.screenshot_dir)
        self.notifier = FanoutNotifier()

        self.auth = Authenticator(
            self.session,
            self.selectors,
            self.humanizer,
            config.credentials,
            on_intervention=self._on_intervention,
        )
        self.inbox = Inbox(self.session, self.selectors, self.humanizer)
        self.ads = AdManager(self.session, self.selectors, self.humanizer, config.ads.template_dir)
        self.responder = Responder(config)
        self.limiter = RateLimiter(self.storage, config.schedule, config.browser.timezone)

        self.state = BotState(ai_backend=config.ai.backend)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    def add_notifier(self, notifier: Notifier) -> None:
        self.notifier.add(notifier)

    async def start(self, warm_model: bool = True) -> None:
        log.info("Starte Orchestrator ...")
        await self.session.start()

        try:
            result = await self.auth.ensure_logged_in()
            self.state.logged_in = result.logged_in
            log.info(
                "Angemeldet (%s).",
                "bestehende Sitzung" if result.used_existing_session else "frischer Login",
            )
        except InterventionRequired as exc:
            self.state.logged_in = False
            self.state.last_error = str(exc)
            await self.notifier.notify(f"⚠️ Login braucht dich: {exc}")
        except LoginError as exc:
            self.state.logged_in = False
            self.state.last_error = str(exc)
            await self.notifier.notify(f"❌ Login fehlgeschlagen: {exc}")

        if warm_model:
            # Im Hintergrund laden, damit UI und Telegram sofort reagieren.
            asyncio.create_task(self._warm_model())

        self.state.running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="inbox-loop")
        log.info("Orchestrator laeuft.")

    async def _warm_model(self) -> None:
        try:
            await self.responder.warmup()
            self.state.ai_ready = True
            log.info("KI-Modell geladen.")
        except Exception as exc:  # noqa: BLE001
            self.state.ai_ready = False
            self.state.last_error = f"KI-Modell: {exc}"
            log.error("KI-Modell konnte nicht geladen werden: %s", exc)
            await self.notifier.notify(f"⚠️ KI-Modell nicht geladen: {exc}")

    async def stop(self) -> None:
        log.info("Stoppe Orchestrator ...")
        self.state.running = False
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.responder.close()
        await self.session.stop()
        self.storage.close()
        log.info("Orchestrator beendet.")

    def pause(self) -> None:
        self.state.paused = True
        log.info("Pausiert - es wird nichts mehr gesendet.")

    def resume(self) -> None:
        self.state.paused = False
        self._wake_event.set()
        log.info("Fortgesetzt.")

    def wake(self) -> None:
        """Wartezeit abkuerzen und sofort pollen."""
        self._wake_event.set()

    # ------------------------------------------------------------------
    # Hintergrundschleife
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self.state.paused:
                    await self._sleep_interruptible(30)
                    continue

                if self.limiter.in_quiet_hours():
                    wait = min(self.limiter.seconds_until_quiet_end(), 1800)
                    log.info("Ruhezeit - naechste Pruefung in %d Minuten.", int(wait / 60))
                    await self._sleep_interruptible(wait)
                    continue

                await self.poll_once()

            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - die Schleife darf nie sterben
                self.state.last_error = str(exc)
                log.exception("Fehler im Abrufzyklus")
                if self.config.telegram.notify_errors:
                    await self.notifier.notify(f"⚠️ Fehler im Abrufzyklus: {exc}")
                await self._sleep_interruptible(120)
                continue

            interval = self.humanizer.next_interval(
                self.config.schedule.inbox_poll_min,
                self.config.schedule.inbox_poll_max,
            )
            self.state.next_poll_at = utcnow() + timedelta(seconds=interval)
            log.info("Naechster Postfach-Abruf in %d Sekunden.", int(interval))
            await self._sleep_interruptible(interval)

    async def _sleep_interruptible(self, seconds: float) -> None:
        """Schlafen, aber durch `wake()` oder `stop()` unterbrechbar."""
        self._wake_event.clear()
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=seconds)
        except TimeoutError:
            pass

    # ------------------------------------------------------------------
    # Postfach
    # ------------------------------------------------------------------

    async def poll_once(self) -> int:
        """Ein Abrufzyklus. Gibt die Anzahl neuer eingehender Nachrichten zurueck."""
        async with self.session.lock:
            if not await self.auth.is_logged_in():
                log.info("Sitzung abgelaufen, melde neu an.")
                try:
                    await self.auth.ensure_logged_in(force=True)
                    self.state.logged_in = True
                except (LoginError, InterventionRequired) as exc:
                    self.state.logged_in = False
                    self.state.last_error = str(exc)
                    await self.notifier.notify(f"⚠️ Anmeldung noetig: {exc}")
                    return 0

            threads = await self.inbox.list_threads()
            self.state.last_poll_at = utcnow()

            expired = self.storage.expire_stale_drafts(self.config.replies.draft_ttl_hours)
            if expired:
                log.info("%d abgelaufene Entwuerfe verworfen.", expired)

            new_count = 0
            for thread in threads:
                known = self.storage.get_thread(thread.thread_id)
                if known is not None:
                    thread.muted = known.muted
                    thread.message_count = known.message_count
                    if not thread.unread and not known.unread:
                        continue    # nichts Neues
                if thread.muted:
                    continue
                new_count += await self._process_thread(thread)

        self.state.pending_drafts = len(self.storage.list_drafts(DraftStatus.PENDING))
        self.state.replies_sent_today = self.limiter.replies_today()
        return new_count

    async def _process_thread(self, thread: Thread) -> int:
        """Verlauf einlesen, ggf. Entwurf erzeugen. Erwartet den Session-Lock."""
        self.storage.upsert_thread(thread)

        try:
            messages = await self.inbox.read_messages(thread)
        except Exception as exc:  # noqa: BLE001
            log.warning("Konversation %s nicht lesbar: %s", thread.thread_id, exc)
            return 0

        new_ids = self.storage.add_messages(messages)
        if not new_ids:
            return 0

        history = self.storage.get_history(thread.thread_id)
        if not history or history[-1].direction is not Direction.INCOMING:
            return 0   # letzte Nachricht war von uns - nichts zu tun

        stored = self.storage.get_thread(thread.thread_id) or thread
        incoming_new = sum(
            1 for m in messages if m.direction is Direction.INCOMING and m.id in new_ids
        ) or 1

        log.info(
            "Konversation %s (%s): %d neue Nachricht(en).",
            thread.thread_id, stored.partner_name, incoming_new,
        )
        if self.config.telegram.notify_new_message:
            preview = " ".join(history[-1].body.split())[:200]
            await self.notifier.notify(
                f"📬 Neue Nachricht von *{stored.partner_name or 'unbekannt'}*\n\n{preview}"
            )

        if self.storage.has_open_draft(thread.thread_id):
            log.info("Es liegt schon ein offener Entwurf vor - kein neuer.")
            return incoming_new

        await self._draft_for_thread(stored, history)
        return incoming_new

    async def _draft_for_thread(self, thread: Thread, history: list[Message]) -> Draft | None:
        result = await self.responder.draft_reply(thread, history)

        if result.blocked:
            self.storage.set_thread_flags(
                thread.thread_id, escalated=True, escalation_reason=result.reason
            )
            self.storage.add_draft(
                Draft(
                    thread_id=thread.thread_id,
                    text="",
                    status=DraftStatus.BLOCKED,
                    note=result.reason,
                    model_name=result.model_name,
                )
            )
            if self.config.safety.on_block == "escalate":
                await self.notifier.notify(
                    f"🛑 *Keine automatische Antwort*\n"
                    f"Kontakt: {thread.partner_name or thread.thread_id}\n"
                    f"Grund: {result.reason}\n\n"
                    f"Bitte selbst ansehen: {thread.url}"
                )
            return None

        if not result.ok:
            self.state.last_error = result.reason
            await self.notifier.notify(f"⚠️ Entwurf fehlgeschlagen: {result.reason}")
            return None

        draft = Draft(
            thread_id=thread.thread_id,
            text=result.text,
            source_message_id=history[-1].id,
            model_name=result.model_name,
            note=result.disclosure_note,
        )
        draft_id = self.storage.add_draft(draft)

        if self.config.assistant.enabled:
            # Im Assistenzmodus greift die Erstkontakt-Freigabe nicht: die erste
            # Antwort ist gerade die, die sich als Programm vorstellt. Sie
            # zurueckzuhalten wuerde den Modus sinnlos machen.
            needs_approval = self.config.replies.require_approval
        else:
            needs_approval = self.config.replies.require_approval or (
                self.config.replies.always_approve_first_contact and thread.is_first_contact
            )

        if needs_approval:
            await self.notifier.ask_approval(
                draft_id, thread.partner_name or thread.thread_id, result.text
            )
            log.info("Entwurf #%d wartet auf Freigabe.", draft_id)
        else:
            ok, message = await self.send_draft(draft_id, acquire_lock=False)
            # Autonom heisst nicht unbeobachtet: du siehst mit, was in deinem
            # Namen rausgegangen ist, auch wenn du nichts freigeben musst.
            if ok and self.config.telegram.notify_new_message:
                note = f"\n_{result.disclosure_note}_" if result.disclosure_note else ""
                await self.notifier.notify(
                    f"🤖 *Automatisch geantwortet* an "
                    f"{thread.partner_name or thread.thread_id}\n\n{result.text}{note}"
                )
            elif not ok:
                await self.notifier.notify(f"⚠️ Automatische Antwort nicht gesendet: {message}")

        return draft

    async def draft_for_thread_id(self, thread_id: str) -> Draft | None:
        """Entwurf fuer eine bestimmte Konversation neu erzeugen."""
        thread = self.storage.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Konversation {thread_id} ist nicht bekannt.")
        history = self.storage.get_history(thread_id)
        if not history:
            raise ValueError("Kein Verlauf gespeichert - erst einmal abrufen.")
        return await self._draft_for_thread(thread, history)

    # ------------------------------------------------------------------
    # Entwuerfe
    # ------------------------------------------------------------------

    def list_pending_drafts(self) -> list[Draft]:
        return self.storage.list_drafts(DraftStatus.PENDING)

    def reject_draft(self, draft_id: int, note: str = "Von Hand verworfen.") -> bool:
        draft = self.storage.get_draft(draft_id)
        if draft is None or draft.status is not DraftStatus.PENDING:
            return False
        self.storage.update_draft(draft_id, status=DraftStatus.REJECTED, note=note)
        log.info("Entwurf #%d verworfen.", draft_id)
        return True

    def edit_draft(self, draft_id: int, text: str) -> bool:
        draft = self.storage.get_draft(draft_id)
        if draft is None or draft.status is not DraftStatus.PENDING:
            return False
        self.storage.update_draft(draft_id, text=text, note="Von Hand bearbeitet.")
        return True

    async def send_draft(self, draft_id: int, acquire_lock: bool = True) -> tuple[bool, str]:
        """Entwurf absenden. Gibt (Erfolg, Meldung) zurueck."""
        draft = self.storage.get_draft(draft_id)
        if draft is None:
            return False, f"Entwurf #{draft_id} existiert nicht."
        if draft.status not in (DraftStatus.PENDING, DraftStatus.APPROVED):
            return False, f"Entwurf #{draft_id} ist bereits '{draft.status.value}'."

        thread = self.storage.get_thread(draft.thread_id)
        if thread is None:
            return False, f"Konversation {draft.thread_id} ist nicht bekannt."

        decision = self.limiter.can_send_reply()
        if not decision.allowed:
            return False, f"Nicht gesendet: {decision.reason}"

        outgoing = self.responder.check_manual_text(draft.text)
        if not outgoing.allowed:
            self.storage.update_draft(draft_id, status=DraftStatus.BLOCKED, note=outgoing.reason)
            return False, f"Vom Sicherheitsfilter gestoppt: {outgoing.reason}"

        async def _do_send() -> tuple[bool, str]:
            try:
                sent = await self.inbox.send_reply(thread, draft.text)
            except Exception as exc:  # noqa: BLE001
                self.storage.update_draft(draft_id, status=DraftStatus.FAILED, note=str(exc))
                self.storage.log_action(ACTION_REPLY, thread.thread_id, str(exc), ok=False)
                log.error("Senden fehlgeschlagen: %s", exc)
                return False, f"Senden fehlgeschlagen: {exc}"

            self.storage.update_draft(draft_id, status=DraftStatus.SENT)
            self.storage.add_message(
                Message(
                    thread_id=thread.thread_id,
                    direction=Direction.OUTGOING,
                    body=draft.text,
                )
            )
            self.storage.set_thread_flags(thread.thread_id, unread=False)
            self.storage.log_action(ACTION_REPLY, thread.thread_id, draft.text[:120], ok=True)
            self.state.replies_sent_today = self.limiter.replies_today()

            note = "" if sent else " (im Verlauf nicht bestaetigt - bitte kurz nachsehen)"
            return True, f"Antwort an {thread.partner_name or thread.thread_id} gesendet{note}."

        if acquire_lock:
            async with self.session.lock:
                return await _do_send()
        return await _do_send()

    async def send_manual_reply(self, thread_id: str, text: str) -> tuple[bool, str]:
        """Selbst getippte Antwort senden - laeuft trotzdem durch Filter und Limits."""
        thread = self.storage.get_thread(thread_id)
        if thread is None:
            return False, f"Konversation {thread_id} ist nicht bekannt."

        verdict = self.responder.check_manual_text(text)
        if not verdict.allowed:
            return False, f"Sicherheitsfilter: {verdict.reason}"

        decision = self.limiter.can_send_reply()
        if not decision.allowed:
            return False, f"Nicht gesendet: {decision.reason}"

        async with self.session.lock:
            try:
                await self.inbox.send_reply(thread, text)
            except Exception as exc:  # noqa: BLE001
                self.storage.log_action(ACTION_REPLY, thread_id, str(exc), ok=False)
                return False, f"Senden fehlgeschlagen: {exc}"

        self.storage.add_message(
            Message(thread_id=thread_id, direction=Direction.OUTGOING, body=text)
        )
        self.storage.set_thread_flags(thread_id, unread=False)
        self.storage.log_action(ACTION_REPLY, thread_id, text[:120], ok=True)
        return True, f"Antwort an {thread.partner_name or thread_id} gesendet."

    # ------------------------------------------------------------------
    # Anzeigen
    # ------------------------------------------------------------------

    async def refresh_ads(self) -> list[Ad]:
        async with self.session.lock:
            ads = await self.ads.list_ads()
        for ad in ads:
            existing = next((a for a in self.storage.list_ads() if a.ad_id == ad.ad_id), None)
            if existing is not None:
                ad.created_at = existing.created_at
                ad.last_renewed_at = existing.last_renewed_at
            elif ad.created_at is None:
                ad.created_at = utcnow()
            self.storage.upsert_ad(ad)
        return ads

    def list_ad_templates(self) -> dict[str, AdTemplate]:
        return load_templates(self.config.ads.template_dir)

    async def create_ad_from_template(self, template_name: str) -> tuple[bool, str]:
        templates = self.list_ad_templates()
        template = templates.get(template_name)
        if template is None:
            available = ", ".join(sorted(templates)) or "(keine)"
            return False, f"Vorlage '{template_name}' nicht gefunden. Verfuegbar: {available}"

        decision = self.limiter.can_create_ad()
        if not decision.allowed:
            return False, f"Nicht angelegt: {decision.reason}"

        async with self.session.lock:
            try:
                ad = await self.ads.create_ad(template)
            except Exception as exc:  # noqa: BLE001
                self.storage.log_action(ACTION_AD_CREATE, template_name, str(exc), ok=False)
                return False, f"Anzeige konnte nicht aufgegeben werden: {exc}"

        self.storage.upsert_ad(ad)
        self.storage.log_action(ACTION_AD_CREATE, ad.ad_id, ad.title, ok=True)
        return True, f"Anzeige '{ad.title}' ist online.\n{ad.url}"

    async def renew_ad(self, ad_id: str) -> tuple[bool, str]:
        ad = self._find_ad(ad_id)
        if ad is None:
            return False, f"Anzeige {ad_id} ist nicht bekannt. Erst '/anzeigen' aufrufen."
        async with self.session.lock:
            try:
                await self.ads.renew_ad(ad)
            except Exception as exc:  # noqa: BLE001
                self.storage.log_action(ACTION_AD_RENEW, ad_id, str(exc), ok=False)
                return False, f"Hochschieben fehlgeschlagen: {exc}"
        self.storage.mark_ad_renewed(ad_id)
        self.storage.log_action(ACTION_AD_RENEW, ad_id, ad.title, ok=True)
        return True, f"Anzeige '{ad.title}' wurde hochgeschoben."

    async def pause_ad(self, ad_id: str) -> tuple[bool, str]:
        ad = self._find_ad(ad_id)
        if ad is None:
            return False, f"Anzeige {ad_id} ist nicht bekannt."
        async with self.session.lock:
            try:
                await self.ads.pause_ad(ad)
            except Exception as exc:  # noqa: BLE001
                return False, f"Pausieren fehlgeschlagen: {exc}"
        self.storage.log_action("ad_paused", ad_id, ad.title, ok=True)
        return True, f"Anzeige '{ad.title}' pausiert."

    async def delete_ad(self, ad_id: str) -> tuple[bool, str]:
        ad = self._find_ad(ad_id)
        if ad is None:
            return False, f"Anzeige {ad_id} ist nicht bekannt."
        async with self.session.lock:
            try:
                await self.ads.delete_ad(ad)
            except Exception as exc:  # noqa: BLE001
                return False, f"Loeschen fehlgeschlagen: {exc}"
        self.storage.delete_ad(ad_id)
        self.storage.log_action("ad_deleted", ad_id, ad.title, ok=True)
        return True, f"Anzeige '{ad.title}' geloescht."

    async def edit_ad(
        self, ad_id: str, *, title: str | None = None, description: str | None = None
    ) -> tuple[bool, str]:
        ad = self._find_ad(ad_id)
        if ad is None:
            return False, f"Anzeige {ad_id} ist nicht bekannt."
        async with self.session.lock:
            try:
                await self.ads.edit_ad(ad, title=title, description=description)
            except Exception as exc:  # noqa: BLE001
                return False, f"Bearbeiten fehlgeschlagen: {exc}"
        if title:
            ad.title = title
        if description:
            ad.description = description
        self.storage.upsert_ad(ad)
        return True, f"Anzeige '{ad.title}' aktualisiert."

    async def run_auto_renew(self) -> list[str]:
        """Faellige Anzeigen hochschieben. Wird vom Nutzer oder Cron angestossen."""
        if not self.config.ads.auto_renew:
            return []
        done: list[str] = []
        for ad in self.storage.list_ads():
            age = ad.age_days()
            if age is not None and age >= self.config.ads.auto_renew_after_days:
                ok, message = await self.renew_ad(ad.ad_id)
                done.append(message)
                if ok:
                    await asyncio.sleep(self.humanizer.next_interval(30, 180))
        return done

    def _find_ad(self, ad_id: str) -> Ad | None:
        ads = self.storage.list_ads()
        exact = next((a for a in ads if a.ad_id == ad_id), None)
        if exact is not None:
            return exact
        # Bequemlichkeit: Titelanfang statt ID erlauben.
        lowered = ad_id.lower()
        return next((a for a in ads if a.title.lower().startswith(lowered)), None)

    # ------------------------------------------------------------------
    # Status & Diagnose
    # ------------------------------------------------------------------

    def snapshot(self) -> BotState:
        self.state.pending_drafts = len(self.storage.list_drafts(DraftStatus.PENDING))
        self.state.replies_sent_today = self.limiter.replies_today()
        self.state.ai_ready = self.responder.ready
        return self.state

    async def screenshot(self, name: str = "manuell") -> Path:
        async with self.session.lock:
            return await self.session.screenshot(name)

    async def diagnose_selectors(self, url: str = "") -> dict[str, str]:
        async with self.session.lock:
            page = await self.session.goto(url) if url else await self.session.page()
            return await self.selectors.diagnose(page)

    async def submit_2fa(self, code: str) -> tuple[bool, str]:
        async with self.session.lock:
            try:
                ok = await self.auth.submit_2fa_code(code)
            except LoginError as exc:
                return False, str(exc)
        self.state.logged_in = ok
        return ok, "Angemeldet." if ok else "Code akzeptiert, aber weiterhin nicht angemeldet."

    async def _on_intervention(self, screenshot_path: str, reason: str) -> None:
        await self.notifier.notify_photo(screenshot_path, f"⚠️ {reason}")
