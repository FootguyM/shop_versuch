"""Lokales Web-Dashboard.

Bewusst als Web-UI und nicht als Qt/Tk-Fenster: derselbe Code laeuft auf dem
Windows-PC und auf dem Raspberry Pi (dort per Browser vom Handy oder ueber
SSH-Tunnel), und es muss kein GUI-Toolkit auf dem Pi kompiliert werden.

Standardmaessig lauscht der Server nur auf 127.0.0.1. Wer ihn ins Netz haengt,
muss in .env ein UI_PASSWORD setzen - das erzwingt die Konfigurationspruefung.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config
from ..core.orchestrator import Orchestrator
from ..models import DraftStatus

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
COOKIE_NAME = "marktbot_session"


class WebUI:
    def __init__(self, config: Config, orchestrator: Orchestrator) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self.app = FastAPI(title="markt.de Assistent", docs_url=None, redoc_url=None)
        self._tokens: set[str] = set()
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None
        self._build_routes()

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    async def start(self) -> None:
        uvicorn_config = uvicorn.Config(
            self.app,
            host=self.config.ui.host,
            port=self.config.ui.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(uvicorn_config)
        # install_signal_handlers aus, sonst kapert uvicorn Ctrl+C vom Hauptprogramm.
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._task = asyncio.create_task(self._server.serve(), name="web-ui")
        log.info(
            "Web-UI erreichbar unter http://%s:%d",
            self.config.ui.host, self.config.ui.port,
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None
        log.info("Web-UI beendet.")

    # ------------------------------------------------------------------
    # Authentifizierung
    # ------------------------------------------------------------------

    def _auth_required(self) -> bool:
        return bool(self.config.ui.password)

    async def _require_auth(self, request: Request) -> None:
        if not self._auth_required():
            return
        token = request.cookies.get(COOKIE_NAME, "")
        if token not in self._tokens:
            raise HTTPException(status_code=401, detail="Nicht angemeldet.")

    # ------------------------------------------------------------------
    # Routen
    # ------------------------------------------------------------------

    def _build_routes(self) -> None:
        app = self.app
        auth = Depends(self._require_auth)

        if STATIC_DIR.exists():
            app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        # -- Anmeldung --------------------------------------------------

        @app.get("/api/auth")
        async def auth_state(request: Request) -> dict[str, Any]:
            token = request.cookies.get(COOKIE_NAME, "")
            return {
                "required": self._auth_required(),
                "authenticated": not self._auth_required() or token in self._tokens,
            }

        @app.post("/api/login")
        async def login(request: Request, response: Response) -> dict[str, Any]:
            if not self._auth_required():
                return {"ok": True}
            body = await request.json()
            supplied = str(body.get("password", ""))
            if not secrets.compare_digest(supplied, self.config.ui.password):
                raise HTTPException(status_code=401, detail="Falsches Passwort.")
            token = secrets.token_urlsafe(32)
            self._tokens.add(token)
            response.set_cookie(
                COOKIE_NAME, token, httponly=True, samesite="strict", max_age=86400
            )
            return {"ok": True}

        @app.post("/api/logout")
        async def logout(request: Request, response: Response) -> dict[str, Any]:
            token = request.cookies.get(COOKIE_NAME, "")
            self._tokens.discard(token)
            response.delete_cookie(COOKIE_NAME)
            return {"ok": True}

        # -- Status -----------------------------------------------------

        @app.get("/api/status", dependencies=[auth])
        async def status() -> dict[str, Any]:
            state = self.orchestrator.snapshot()
            limiter = self.orchestrator.limiter
            return {
                "running": state.running,
                "paused": state.paused,
                "logged_in": state.logged_in,
                "ai_ready": state.ai_ready,
                "ai_backend": state.ai_backend,
                "pending_drafts": state.pending_drafts,
                "replies_today": limiter.replies_today(),
                "replies_last_hour": limiter.replies_last_hour(),
                "limit_day": self.config.schedule.limits.replies_per_day,
                "limit_hour": self.config.schedule.limits.replies_per_hour,
                "quiet_hours": limiter.in_quiet_hours(),
                "require_approval": self.config.replies.require_approval,
                "assistant_mode": self.config.assistant.enabled,
                "assistant_name": self.config.assistant.assistant_name,
                "last_poll_at": state.last_poll_at.isoformat() if state.last_poll_at else None,
                "next_poll_at": state.next_poll_at.isoformat() if state.next_poll_at else None,
                "last_error": state.last_error,
            }

        @app.get("/api/log", dependencies=[auth])
        async def action_log() -> list[dict[str, Any]]:
            return self.orchestrator.storage.recent_actions(limit=40)

        # -- Steuerung --------------------------------------------------

        @app.post("/api/control/{action}", dependencies=[auth])
        async def control(action: str) -> dict[str, Any]:
            if action == "pause":
                self.orchestrator.pause()
            elif action == "resume":
                self.orchestrator.resume()
            elif action == "poll":
                count = await self.orchestrator.poll_once()
                return {"ok": True, "message": f"{count} neue Nachricht(en)."}
            else:
                raise HTTPException(status_code=400, detail=f"Unbekannte Aktion: {action}")
            return {"ok": True}

        # -- Postfach ---------------------------------------------------

        @app.get("/api/threads", dependencies=[auth])
        async def threads() -> list[dict[str, Any]]:
            return [
                {
                    "thread_id": t.thread_id,
                    "partner_name": t.partner_name,
                    "ad_title": t.ad_title,
                    "url": t.url,
                    "unread": t.unread,
                    "escalated": t.escalated,
                    "escalation_reason": t.escalation_reason,
                    "message_count": t.message_count,
                    "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
                }
                for t in self.orchestrator.storage.list_threads(limit=50)
            ]

        @app.get("/api/threads/{thread_id}", dependencies=[auth])
        async def thread_detail(thread_id: str) -> dict[str, Any]:
            thread = self.orchestrator.storage.get_thread(thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="Konversation unbekannt.")
            history = self.orchestrator.storage.get_history(thread_id, limit=50)
            return {
                "thread_id": thread.thread_id,
                "partner_name": thread.partner_name,
                "url": thread.url,
                "messages": [
                    {
                        "direction": m.direction.value,
                        "body": m.body,
                        "sent_at": m.sent_at.isoformat(),
                    }
                    for m in history
                ],
            }

        @app.post("/api/threads/{thread_id}/reply", dependencies=[auth])
        async def manual_reply(thread_id: str, request: Request) -> dict[str, Any]:
            body = await request.json()
            text = str(body.get("text", "")).strip()
            if not text:
                raise HTTPException(status_code=400, detail="Leerer Text.")
            ok, message = await self.orchestrator.send_manual_reply(thread_id, text)
            return {"ok": ok, "message": message}

        @app.post("/api/threads/{thread_id}/draft", dependencies=[auth])
        async def regenerate(thread_id: str) -> dict[str, Any]:
            try:
                draft = await self.orchestrator.draft_for_thread_id(thread_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if draft is None:
                return {"ok": False, "message": "Kein Entwurf erzeugt - siehe Status/Log."}
            return {"ok": True, "draft_id": draft.id, "text": draft.text}

        # -- Entwuerfe --------------------------------------------------

        @app.get("/api/drafts", dependencies=[auth])
        async def drafts() -> list[dict[str, Any]]:
            result = []
            for draft in self.orchestrator.storage.list_drafts(DraftStatus.PENDING):
                thread = self.orchestrator.storage.get_thread(draft.thread_id)
                result.append({
                    "id": draft.id,
                    "thread_id": draft.thread_id,
                    "partner_name": thread.partner_name if thread else "",
                    "text": draft.text,
                    "model_name": draft.model_name,
                    "created_at": draft.created_at.isoformat(),
                })
            return result

        @app.post("/api/drafts/{draft_id}/send", dependencies=[auth])
        async def send_draft(draft_id: int, request: Request) -> dict[str, Any]:
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001 - Body ist optional
                body = {}
            text = str(body.get("text", "")).strip()
            if text:
                self.orchestrator.edit_draft(draft_id, text)
            ok, message = await self.orchestrator.send_draft(draft_id)
            return {"ok": ok, "message": message}

        @app.post("/api/drafts/{draft_id}/reject", dependencies=[auth])
        async def reject_draft(draft_id: int) -> dict[str, Any]:
            ok = self.orchestrator.reject_draft(draft_id)
            return {"ok": ok, "message": "Verworfen." if ok else "Entwurf nicht mehr offen."}

        # -- Anzeigen ---------------------------------------------------

        @app.get("/api/ads", dependencies=[auth])
        async def ads(refresh: bool = False) -> list[dict[str, Any]]:
            items = await self.orchestrator.refresh_ads() if refresh else \
                self.orchestrator.storage.list_ads()
            return [
                {
                    "ad_id": ad.ad_id,
                    "title": ad.title,
                    "status": ad.status.value,
                    "views": ad.views,
                    "url": ad.url,
                    "age_days": ad.age_days(),
                }
                for ad in items
            ]

        @app.get("/api/ad-templates", dependencies=[auth])
        async def ad_templates() -> list[dict[str, Any]]:
            return [
                {
                    "name": name,
                    "title": template.title,
                    "description": template.description,
                    "images": template.images,
                }
                for name, template in sorted(self.orchestrator.list_ad_templates().items())
            ]

        @app.post("/api/ads/create", dependencies=[auth])
        async def create_ad(request: Request) -> dict[str, Any]:
            body = await request.json()
            name = str(body.get("template", "")).strip()
            if not name:
                raise HTTPException(status_code=400, detail="Keine Vorlage angegeben.")
            ok, message = await self.orchestrator.create_ad_from_template(name)
            return {"ok": ok, "message": message}

        @app.post("/api/ads/{ad_id}/{action}", dependencies=[auth])
        async def ad_action(ad_id: str, action: str) -> dict[str, Any]:
            actions = {
                "renew": self.orchestrator.renew_ad,
                "pause": self.orchestrator.pause_ad,
                "delete": self.orchestrator.delete_ad,
            }
            handler = actions.get(action)
            if handler is None:
                raise HTTPException(status_code=400, detail=f"Unbekannte Aktion: {action}")
            ok, message = await handler(ad_id)
            return {"ok": ok, "message": message}

        # -- Diagnose ---------------------------------------------------

        @app.get("/api/screenshot", dependencies=[auth])
        async def screenshot() -> FileResponse:
            path = await self.orchestrator.screenshot("webui")
            return FileResponse(path, media_type="image/png")

        @app.exception_handler(HTTPException)
        async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code, content={"ok": False, "message": exc.detail}
            )
