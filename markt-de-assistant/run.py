#!/usr/bin/env python3
"""Einstiegspunkt.

  python run.py            Alles starten (Postfach-Automatik, Telegram, Web-UI)
  python run.py ui         Nur Web-UI und Automatik, ohne Telegram
  python run.py headless   Ohne Web-UI (fuer den Raspberry Pi als Dienst)
  python run.py login      Browser oeffnen und anmelden (Profil vorbereiten)
  python run.py doctor     Pruefen, welche Selektoren auf einer Seite greifen
  python run.py check      Einmal das Postfach abrufen, dann beenden
  python run.py ai-test    KI-Backend testen, ohne den Browser zu starten
  python run.py ads        Anzeigen auflisten, dann beenden
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# src/ ins Modulsuchverzeichnis legen, damit kein "pip install -e ." noetig ist.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from marktbot.config import ConfigError, load_config  # noqa: E402
from marktbot.logging_setup import setup_logging  # noqa: E402

# marktbot.app zieht Playwright, Telegram und FastAPI nach. Das wird erst
# beim tatsaechlichen Start importiert, damit "ai-test" auch dann laeuft,
# wenn nur die KI-Abhaengigkeiten installiert sind.


# --------------------------------------------------------------------------
# Unterbefehle
# --------------------------------------------------------------------------


async def cmd_login(config) -> int:
    """Sichtbaren Browser oeffnen, anmelden, Profil speichern."""
    from marktbot.browser.humanize import Humanizer
    from marktbot.browser.session import BrowserSession
    from marktbot.markt.auth import Authenticator, InterventionRequired, LoginError
    from marktbot.markt.selectors import Selectors

    if config.browser.headless:
        print(
            "Hinweis: browser.headless steht auf true. Fuer den ersten Login ist ein\n"
            "sichtbares Fenster deutlich einfacher - in config.yaml auf false setzen.\n"
        )

    session = BrowserSession(config.browser, config.screenshot_dir)
    selectors = Selectors.load(config.root / "selectors.yaml")
    auth = Authenticator(session, selectors, Humanizer(config.humanize), config.credentials)

    async with session:
        try:
            result = await auth.ensure_logged_in()
            print(
                "\n✅ Angemeldet"
                + (" (bestehende Sitzung)." if result.used_existing_session else ".")
            )
        except InterventionRequired as exc:
            print(f"\n⚠️  {exc}")
            print("Loese die Abfrage im Browserfenster. Ich warte bis zu 5 Minuten ...")
            for _ in range(60):
                await asyncio.sleep(5)
                if await auth.is_logged_in():
                    print("✅ Angemeldet.")
                    break
            else:
                print("❌ Zeit abgelaufen - nicht angemeldet.")
                return 1
        except LoginError as exc:
            print(f"\n❌ {exc}")
            return 1

        print(f"Profil liegt in: {config.browser.profile_dir}")
        print("Dieses Verzeichnis kannst du auf den Raspberry Pi kopieren.")
        print("\nBrowser bleibt 20 Sekunden offen ...")
        await asyncio.sleep(20)
    return 0


async def cmd_doctor(config, url: str) -> int:
    """Selektoren gegen eine konkrete Seite pruefen."""
    from marktbot.browser.humanize import Humanizer
    from marktbot.browser.session import BrowserSession
    from marktbot.markt.auth import Authenticator
    from marktbot.markt.selectors import Selectors

    session = BrowserSession(config.browser, config.screenshot_dir)
    selectors = Selectors.load(config.root / "selectors.yaml")
    auth = Authenticator(session, selectors, Humanizer(config.humanize), config.credentials)

    async with session:
        page = await session.goto(url)
        await auth.dismiss_cookie_banner(page)
        await asyncio.sleep(2)
        report = await selectors.diagnose(page)

        print(f"\nSelektor-Check auf {url}\n" + "=" * 78)
        found = 0
        for key, hit in sorted(report.items()):
            mark = "  " if hit.startswith("--") else "OK"
            if not hit.startswith("--"):
                found += 1
            print(f"[{mark}] {key:28s} {hit}")
        print("=" * 78)
        print(f"{found}/{len(report)} Elemente gefunden.\n")
        print(
            "Nicht gefundene Elemente sind nur dann ein Problem, wenn sie auf DIESER\n"
            "Seite vorkommen sollten. Korrekturen kommen nach selectors.yaml:\n\n"
            "  reply_input:\n"
            "    - \"css=textarea.deine-echte-klasse\"\n"
        )
        dump = await session.dump_html("doctor")
        print(f"HTML-Dump zum Nachsehen: {dump}\n")
    return 0


async def cmd_check(config) -> int:
    """Einen Abrufzyklus fahren und das Ergebnis zeigen."""
    from marktbot.core.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)
    try:
        await orchestrator.start(warm_model=True)
        # Auf das Modell warten, sonst gibt es keine Entwuerfe.
        for _ in range(120):
            if orchestrator.state.ai_ready or orchestrator.state.last_error:
                break
            await asyncio.sleep(1)

        count = await orchestrator.poll_once()
        print(f"\n{count} neue Nachricht(en).")

        drafts = orchestrator.list_pending_drafts()
        if drafts:
            print(f"\n{len(drafts)} Entwurf/Entwuerfe:")
            for draft in drafts:
                thread = orchestrator.storage.get_thread(draft.thread_id)
                print(f"\n  #{draft.id} an {thread.partner_name if thread else draft.thread_id}:")
                print(f"  {draft.text}")
        else:
            print("Keine offenen Entwuerfe.")
    finally:
        await orchestrator.stop()
    return 0


async def cmd_ads(config) -> int:
    from marktbot.core.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)
    try:
        await orchestrator.start(warm_model=False)
        ads = await orchestrator.refresh_ads()
        if not ads:
            print("Keine Anzeigen gefunden.")
        for ad in ads:
            print(f"  {ad.ad_id:>14}  {ad.status.value:<8} {ad.views:>5} Aufrufe  {ad.title}")
    finally:
        await orchestrator.stop()
    return 0


async def cmd_ai_test(config, text: str) -> int:
    """KI-Backend pruefen, ohne den Browser anzufassen."""
    from marktbot.ai.responder import Responder
    from marktbot.models import Direction, Message, Thread

    print(f"Backend: {config.ai.backend}")
    responder = Responder(config)

    print("Lade Modell (beim ersten Mal laedt es mehrere GB herunter) ...")
    try:
        await responder.warmup()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Modell nicht geladen: {exc}")
        return 1
    print(f"✅ Bereit: {responder.model_name}\n")

    thread = Thread(thread_id="test", partner_name="Testkontakt", ad_title="Testanzeige")
    history = [Message(thread_id="test", direction=Direction.INCOMING, body=text)]

    print(f"Eingehend: {text}")
    result = await responder.draft_reply(thread, history)

    if result.blocked:
        print(f"\n🛑 Vom Sicherheitsfilter gestoppt:\n   {result.reason}")
    elif result.ok:
        print(f"\n💬 Antwortentwurf:\n   {result.text}")
    else:
        print(f"\n❌ Fehlgeschlagen: {result.reason}")

    await responder.close()
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="markt.de Assistent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-c", "--config", help="Pfad zu config.yaml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Alles starten (Standard)")
    sub.add_parser("ui", help="Ohne Telegram starten")
    sub.add_parser("headless", help="Ohne Web-UI starten")
    sub.add_parser("login", help="Browser oeffnen und anmelden")
    sub.add_parser("check", help="Einmal Postfach abrufen")
    sub.add_parser("ads", help="Anzeigen auflisten")

    doctor = sub.add_parser("doctor", help="Selektoren pruefen")
    doctor.add_argument(
        "url", nargs="?", default="https://www.markt.de/postfach/",
        help="Zu pruefende Seite (Standard: Postfach)",
    )

    ai_test = sub.add_parser("ai-test", help="KI-Backend testen")
    ai_test.add_argument(
        "text", nargs="?", default="Hallo, bist du heute Abend noch frei?",
        help="Testnachricht",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"\nKonfigurationsfehler:\n  {exc}\n", file=sys.stderr)
        return 2

    setup_logging(config.logging)

    command = args.command or "run"

    if command != "ai-test":
        from marktbot.app import configure_event_loop
        configure_event_loop()

    try:
        if command in ("run", "ui", "headless"):
            from marktbot.app import run_app
            asyncio.run(run_app(
                config,
                with_ui=command != "headless",
                with_telegram=command != "ui",
            ))
            return 0
        if command == "login":
            return asyncio.run(cmd_login(config))
        if command == "doctor":
            return asyncio.run(cmd_doctor(config, args.url))
        if command == "check":
            return asyncio.run(cmd_check(config))
        if command == "ads":
            return asyncio.run(cmd_ads(config))
        if command == "ai-test":
            return asyncio.run(cmd_ai_test(config, args.text))
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130

    print(f"Unbekannter Befehl: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
