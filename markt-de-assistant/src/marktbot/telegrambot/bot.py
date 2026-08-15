"""Telegram-Fernsteuerung.

Laeuft im selben Event-Loop wie der Orchestrator. Deshalb wird die Application
von Hand hochgefahren (initialize/start/updater.start_polling) statt ueber
run_polling(), das sich einen eigenen Loop bauen wuerde.

Nur die konfigurierte Chat-ID darf steuern. Alles andere wird abgewiesen und
protokolliert.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import Config
from ..core.orchestrator import Orchestrator

log = logging.getLogger(__name__)

MAX_MESSAGE = 3800   # Telegram-Limit ist 4096, etwas Luft lassen

COMMANDS = [
    BotCommand("status", "Zustand, Limits, offene Entwuerfe"),
    BotCommand("postfach", "Letzte Konversationen anzeigen"),
    BotCommand("pruefen", "Sofort nach neuen Nachrichten sehen"),
    BotCommand("entwuerfe", "Offene Antwortentwuerfe zur Freigabe"),
    BotCommand("antwort", "/antwort <id> <text> - selbst antworten"),
    BotCommand("anzeigen", "Eigene Anzeigen auflisten"),
    BotCommand("vorlagen", "Anzeigenvorlagen auflisten"),
    BotCommand("neu", "/neu <vorlage> - Anzeige aufgeben"),
    BotCommand("hoch", "/hoch <id> - Anzeige hochschieben"),
    BotCommand("stoppen", "/stoppen <id> - Anzeige pausieren"),
    BotCommand("loeschen", "/loeschen <id> - Anzeige loeschen"),
    BotCommand("pause", "Automatik anhalten"),
    BotCommand("weiter", "Automatik fortsetzen"),
    BotCommand("screenshot", "Aktuelle Browseransicht schicken"),
    BotCommand("code", "/code <ziffern> - 2FA-Code eintragen"),
    BotCommand("doctor", "Selektoren pruefen"),
    BotCommand("hilfe", "Alle Befehle"),
]

HELP_TEXT = """*markt.de Assistent*

*Postfach*
/status - Zustand, Limits, offene Entwuerfe
/pruefen - sofort nach neuen Nachrichten sehen
/postfach - letzte Konversationen
/entwuerfe - offene Entwuerfe mit Freigabe-Knoepfen
/antwort <id> <text> - selbst antworten

*Anzeigen*
/anzeigen - eigene Anzeigen auflisten
/vorlagen - vorhandene Vorlagen aus ads/
/neu <vorlage> - Anzeige aus Vorlage aufgeben
/hoch <id> - hochschieben
/stoppen <id> - pausieren
/loeschen <id> - loeschen

*Steuerung*
/pause - Automatik anhalten
/weiter - Automatik fortsetzen
/screenshot - Browseransicht schicken
/code <ziffern> - 2FA-Code eintragen
/doctor - pruefen, welche Selektoren greifen

Bei einem Entwurf: *Senden* schickt ihn ab, *Aendern* fragt nach neuem Text, \
*Verwerfen* loescht ihn."""


def _shorten(text: str, limit: int = MAX_MESSAGE) -> str:
    return text if len(text) <= limit else text[: limit - 20] + "\n... (gekuerzt)"


class TelegramInterface:
    """Notifier + Fernsteuerung in einem."""

    def __init__(self, config: Config, orchestrator: Orchestrator) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self.chat_id = config.telegram.chat_id
        self.app: Application | None = None
        # chat_id -> draft_id, waehrend auf einen neuen Entwurfstext gewartet wird
        self._awaiting_edit: dict[int, int] = {}

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self.config.telegram.configured:
            raise RuntimeError(
                "Telegram ist nicht konfiguriert. TELEGRAM_BOT_TOKEN und "
                "TELEGRAM_CHAT_ID in .env eintragen."
            )

        self.app = ApplicationBuilder().token(self.config.telegram.token).build()
        self._register_handlers(self.app)

        await self.app.initialize()
        await self.app.start()
        try:
            await self.app.bot.set_my_commands(COMMANDS)
        except TelegramError as exc:
            log.warning("Befehlsliste konnte nicht gesetzt werden: %s", exc)
        await self.app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram-Bot laeuft (Chat %s).", self.chat_id)

    async def stop(self) -> None:
        if self.app is None:
            return
        try:
            if self.app.updater is not None:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        finally:
            self.app = None
            log.info("Telegram-Bot beendet.")

    def _register_handlers(self, app: Application) -> None:
        handlers = {
            "start": self.cmd_help,
            "hilfe": self.cmd_help,
            "help": self.cmd_help,
            "status": self.cmd_status,
            "pruefen": self.cmd_check,
            "postfach": self.cmd_inbox,
            "entwuerfe": self.cmd_drafts,
            "antwort": self.cmd_reply,
            "anzeigen": self.cmd_ads,
            "vorlagen": self.cmd_templates,
            "neu": self.cmd_new_ad,
            "hoch": self.cmd_renew,
            "stoppen": self.cmd_pause_ad,
            "loeschen": self.cmd_delete_ad,
            "pause": self.cmd_pause,
            "weiter": self.cmd_resume,
            "screenshot": self.cmd_screenshot,
            "code": self.cmd_2fa,
            "doctor": self.cmd_doctor,
        }
        for name, callback in handlers.items():
            app.add_handler(CommandHandler(name, callback))
        app.add_handler(CallbackQueryHandler(self.on_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_error_handler(self.on_error)

    # ------------------------------------------------------------------
    # Notifier-Schnittstelle
    # ------------------------------------------------------------------

    async def notify(self, text: str) -> None:
        await self._send(_shorten(text))

    async def notify_photo(self, path: str | Path, caption: str = "") -> None:
        if self.app is None:
            return
        try:
            with Path(path).open("rb") as handle:
                await self.app.bot.send_photo(
                    chat_id=self.chat_id, photo=handle, caption=caption[:1000]
                )
        except (TelegramError, OSError) as exc:
            log.warning("Foto konnte nicht gesendet werden: %s", exc)
            await self.notify(f"{caption}\n(Screenshot: {path})")

    async def ask_approval(self, draft_id: int, thread_title: str, text: str) -> None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Senden", callback_data=f"send:{draft_id}"),
            InlineKeyboardButton("✏️ Aendern", callback_data=f"edit:{draft_id}"),
            InlineKeyboardButton("🗑 Verwerfen", callback_data=f"drop:{draft_id}"),
        ]])
        body = (
            f"✍️ <b>Entwurf #{draft_id}</b> fuer <b>{html.escape(thread_title)}</b>\n\n"
            f"{html.escape(text)}"
        )
        await self._send(_shorten(body), reply_markup=keyboard, html=True)

    async def _send(
        self,
        text: str,
        reply_markup: Any = None,
        html: bool = False,
    ) -> None:
        if self.app is None:
            log.info("[Telegram nicht bereit] %s", text)
            return
        mode = ParseMode.HTML if html else ParseMode.MARKDOWN
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except TelegramError as exc:
            # Formatierungsfehler sind haeufig, wenn Nutzertext Sonderzeichen
            # enthaelt - dann eben unformatiert.
            log.debug("Formatierter Versand fehlgeschlagen (%s), sende als Klartext.", exc)
            try:
                await self.app.bot.send_message(
                    chat_id=self.chat_id, text=text, reply_markup=reply_markup
                )
            except TelegramError as inner:
                log.error("Telegram-Versand fehlgeschlagen: %s", inner)

    # ------------------------------------------------------------------
    # Zugriffsschutz
    # ------------------------------------------------------------------

    def _authorized(self, update: Update) -> bool:
        chat = update.effective_chat
        if chat is None or chat.id != self.chat_id:
            log.warning(
                "Fremder Zugriff abgewiesen: chat_id=%s user=%s",
                chat.id if chat else "?",
                update.effective_user.id if update.effective_user else "?",
            )
            return False
        return True

    async def _guard(self, update: Update) -> bool:
        if self._authorized(update):
            return True
        if update.effective_message:
            await update.effective_message.reply_text(
                "Dieser Bot ist an einen festen Chat gebunden."
            )
        return False

    # ------------------------------------------------------------------
    # Befehle
    # ------------------------------------------------------------------

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await update.effective_message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        state = self.orchestrator.snapshot()
        limiter = self.orchestrator.limiter

        def flag(value: bool) -> str:
            return "✅" if value else "❌"

        lines = [
            "*Status*",
            f"{flag(state.running and not state.paused)} Automatik: "
            f"{'pausiert' if state.paused else 'laeuft' if state.running else 'gestoppt'}",
            f"{flag(state.logged_in)} Bei markt.de angemeldet",
            f"{flag(state.ai_ready)} KI bereit ({state.ai_backend})",
            "",
            f"Offene Entwuerfe: {state.pending_drafts}",
            limiter.usage_summary(),
        ]
        if limiter.in_quiet_hours():
            lines.append(f"Ruhezeit aktiv, noch {int(limiter.seconds_until_quiet_end() / 60)} min")
        if state.last_poll_at:
            lines.append(f"Letzter Abruf: {state.last_poll_at:%d.%m. %H:%M} UTC")
        if state.next_poll_at:
            lines.append(f"Naechster Abruf: {state.next_poll_at:%d.%m. %H:%M} UTC")
        if state.last_error:
            lines += ["", f"Letzter Fehler: {state.last_error[:300]}"]

        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await update.effective_message.reply_text("Sehe nach ...")
        try:
            count = await self.orchestrator.poll_once()
        except Exception as exc:  # noqa: BLE001
            await update.effective_message.reply_text(f"Fehlgeschlagen: {exc}")
            return
        await update.effective_message.reply_text(
            f"Fertig. {count} neue Nachricht(en)." if count else "Fertig. Nichts Neues."
        )

    async def cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        threads = self.orchestrator.storage.list_threads(limit=15)
        if not threads:
            await update.effective_message.reply_text(
                "Noch keine Konversationen gespeichert. /pruefen ruft das Postfach ab."
            )
            return
        lines = ["*Postfach*"]
        for thread in threads:
            marker = "🔵" if thread.unread else "▪️"
            if thread.escalated:
                marker = "🛑"
            stamp = f"{thread.last_message_at:%d.%m. %H:%M}" if thread.last_message_at else "-"
            lines.append(
                f"{marker} `{thread.thread_id}` {thread.partner_name or 'unbekannt'} - {stamp}"
            )
        lines.append("\nAntworten mit `/antwort <id> <text>`")
        await update.effective_message.reply_text(
            _shorten("\n".join(lines)), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_drafts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        drafts = self.orchestrator.list_pending_drafts()
        if not drafts:
            await update.effective_message.reply_text("Keine offenen Entwuerfe.")
            return
        for draft in drafts[:10]:
            thread = self.orchestrator.storage.get_thread(draft.thread_id)
            await self.ask_approval(
                draft.id,
                (thread.partner_name if thread else "") or draft.thread_id,
                draft.text,
            )

    async def cmd_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "So geht's: `/antwort <konversations-id> <text>`\n"
                "Die IDs stehen in /postfach.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        thread_id, text = context.args[0], " ".join(context.args[1:])
        ok, message = await self.orchestrator.send_manual_reply(thread_id, text)
        await update.effective_message.reply_text(("✅ " if ok else "❌ ") + message)

    async def cmd_ads(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await update.effective_message.reply_text("Lade Anzeigen ...")
        try:
            ads = await self.orchestrator.refresh_ads()
        except Exception as exc:  # noqa: BLE001
            await update.effective_message.reply_text(f"Fehlgeschlagen: {exc}")
            return
        if not ads:
            await update.effective_message.reply_text("Keine Anzeigen gefunden.")
            return
        lines = ["*Deine Anzeigen*"]
        for ad in ads:
            age = ad.age_days()
            age_text = f", {age:.0f} Tage alt" if age is not None else ""
            lines.append(
                f"▪️ `{ad.ad_id}` {ad.title}\n   {ad.status.value}, {ad.views} Aufrufe{age_text}"
            )
        lines.append("\n`/hoch <id>` `/stoppen <id>` `/loeschen <id>`")
        await update.effective_message.reply_text(
            _shorten("\n".join(lines)), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_templates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        templates = self.orchestrator.list_ad_templates()
        if not templates:
            await update.effective_message.reply_text(
                "Keine Vorlagen. Lege eine YAML-Datei in ads/ an - "
                "ads/beispiel.yaml zeigt das Format."
            )
            return
        lines = ["*Vorlagen*"]
        for name, template in sorted(templates.items()):
            lines.append(f"▪️ `{name}` - {template.title}")
        lines.append("\nAufgeben mit `/neu <name>`")
        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_new_ad(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "So geht's: `/neu <vorlage>`. /vorlagen zeigt, was da ist.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await update.effective_message.reply_text("Gebe die Anzeige auf, das dauert etwas ...")
        ok, message = await self.orchestrator.create_ad_from_template(context.args[0])
        await update.effective_message.reply_text(("✅ " if ok else "❌ ") + message)

    async def cmd_renew(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ad_command(update, context, self.orchestrator.renew_ad, "/hoch <id>")

    async def cmd_pause_ad(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ad_command(update, context, self.orchestrator.pause_ad, "/stoppen <id>")

    async def cmd_delete_ad(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._ad_command(update, context, self.orchestrator.delete_ad, "/loeschen <id>")

    async def _ad_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: Any,
        usage: str,
    ) -> None:
        if not await self._guard(update):
            return
        if not context.args:
            await update.effective_message.reply_text(
                f"So geht's: `{usage}`. IDs stehen in /anzeigen.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        ok, message = await action(context.args[0])
        await update.effective_message.reply_text(("✅ " if ok else "❌ ") + message)

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        self.orchestrator.pause()
        await update.effective_message.reply_text(
            "⏸ Automatik angehalten. Es wird nichts mehr abgerufen oder gesendet. /weiter startet wieder."
        )

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        self.orchestrator.resume()
        await update.effective_message.reply_text("▶️ Automatik laeuft wieder.")

    async def cmd_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        try:
            path = await self.orchestrator.screenshot("telegram")
        except Exception as exc:  # noqa: BLE001
            await update.effective_message.reply_text(f"Screenshot fehlgeschlagen: {exc}")
            return
        await self.notify_photo(path, "Aktuelle Browseransicht")

    async def cmd_2fa(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        if not context.args:
            await update.effective_message.reply_text("So geht's: `/code 123456`",
                                                      parse_mode=ParseMode.MARKDOWN)
            return
        ok, message = await self.orchestrator.submit_2fa(context.args[0])
        await update.effective_message.reply_text(("✅ " if ok else "❌ ") + message)

    async def cmd_doctor(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        url = context.args[0] if context.args else ""
        await update.effective_message.reply_text("Pruefe Selektoren ...")
        try:
            report = await self.orchestrator.diagnose_selectors(url)
        except Exception as exc:  # noqa: BLE001
            await update.effective_message.reply_text(f"Fehlgeschlagen: {exc}")
            return
        missing = [key for key, hit in report.items() if hit.startswith("--")]
        found = len(report) - len(missing)
        lines = [f"*Selektor-Check*: {found}/{len(report)} gefunden"]
        if missing:
            lines.append("\nNicht gefunden auf dieser Seite:")
            lines += [f"• `{key}`" for key in missing[:25]]
            lines.append(
                "\nDas ist nur ein Problem, wenn das Element auf DIESER Seite "
                "vorkommen sollte. Korrekturen in selectors.yaml eintragen."
            )
        await update.effective_message.reply_text(
            _shorten("\n".join(lines)), parse_mode=ParseMode.MARKDOWN
        )

    # ------------------------------------------------------------------
    # Knoepfe und freier Text
    # ------------------------------------------------------------------

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        if not self._authorized(update):
            await query.answer("Nicht berechtigt.", show_alert=True)
            return
        await query.answer()

        try:
            action, raw_id = (query.data or "").split(":", 1)
            draft_id = int(raw_id)
        except ValueError:
            await query.edit_message_text("Unbekannte Aktion.")
            return

        if action == "send":
            ok, message = await self.orchestrator.send_draft(draft_id)
            suffix = f"\n\n{'✅' if ok else '❌'} {message}"
            await self._append_to_message(query, suffix)

        elif action == "drop":
            self.orchestrator.reject_draft(draft_id)
            await self._append_to_message(query, "\n\n🗑 Verworfen.")

        elif action == "edit":
            chat = update.effective_chat
            if chat is not None:
                self._awaiting_edit[chat.id] = draft_id
            await query.message.reply_text(
                f"Schick mir den neuen Text fuer Entwurf #{draft_id}. "
                "Er wird danach direkt gesendet.\n(/pause bricht ab.)"
            )

    async def _append_to_message(self, query: Any, suffix: str) -> None:
        """Ergebnis an die Entwurfsnachricht haengen und Knoepfe entfernen."""
        original = query.message.text or ""
        try:
            await query.edit_message_text(_shorten(original + suffix), reply_markup=None)
        except TelegramError as exc:
            log.debug("Nachricht nicht editierbar (%s), sende separat.", exc)
            await query.message.reply_text(suffix.strip())

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Freier Text - relevant, wenn gerade ein Entwurf bearbeitet wird."""
        if not await self._guard(update):
            return
        chat = update.effective_chat
        message = update.effective_message
        if chat is None or message is None or not message.text:
            return

        draft_id = self._awaiting_edit.pop(chat.id, None)
        if draft_id is None:
            await message.reply_text("Kenne ich nicht. /hilfe zeigt alle Befehle.")
            return

        if not self.orchestrator.edit_draft(draft_id, message.text):
            await message.reply_text(
                f"Entwurf #{draft_id} ist nicht mehr offen (schon gesendet oder verworfen)."
            )
            return

        ok, result = await self.orchestrator.send_draft(draft_id)
        await message.reply_text(("✅ " if ok else "❌ ") + result)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Telegram-Handler-Fehler", exc_info=context.error)
        if self.config.telegram.notify_errors:
            await self._send(f"⚠️ Interner Fehler: {context.error}")
