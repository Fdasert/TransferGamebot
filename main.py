"""
Vercel ASGI entrypoint — combines webhook handler and set_webhook utility.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from telegram import Bot, Update
from telegram.ext import Application

from bot import create_application, _reload_cosm_overrides
from config import BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, WEBHOOK_BASE_URL, ADMIN_TOKEN

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None)

# ── Lazy singleton ────────────────────────────────────────────────────────────
_application: Application | None = None
_initialized: bool = False
_init_lock = asyncio.Lock()


async def _ensure_initialized() -> Application:
    global _application, _initialized
    if _initialized and _application is not None:
        return _application
    async with _init_lock:
        if _initialized and _application is not None:
            return _application
        logger.info("Cold start — initialising Application…")
        _application = create_application()
        _reload_cosm_overrides()
        await _application.initialize()
        _initialized = True
        logger.info("Application ready.")
    return _application


# ── Webhook endpoints ─────────────────────────────────────────────────────────

@app.get("/api/webhook")
async def healthcheck() -> JSONResponse:
    return JSONResponse({"ok": True, "status": "running"})


@app.post("/api/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    if TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Rejected request: invalid secret token")
            return Response(status_code=403)
    try:
        application = await _ensure_initialized()
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception:
        logger.exception("Error processing Telegram update")
    return Response(status_code=200)


# ── Set webhook utility ───────────────────────────────────────────────────────

ALLOWED_UPDATES = ["message", "callback_query", "edited_message", "my_chat_member"]


@app.get("/api/set_webhook")
async def set_webhook(request: Request) -> JSONResponse:
    token = request.query_params.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return JSONResponse({"ok": False, "error": "Forbidden"}, status_code=403)

    action = request.query_params.get("action", "set")
    webhook_url = f"{WEBHOOK_BASE_URL}/api/webhook"

    async with Bot(token=BOT_TOKEN) as bot:
        if action == "info":
            info = await bot.get_webhook_info()
            return JSONResponse({
                "ok": True,
                "url": info.url,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
            })
        if action == "delete":
            await bot.delete_webhook(drop_pending_updates=True)
            return JSONResponse({"ok": True, "action": "deleted"})

        await bot.set_webhook(
            url=webhook_url,
            secret_token=TELEGRAM_WEBHOOK_SECRET or None,
            drop_pending_updates=True,
            allowed_updates=ALLOWED_UPDATES,
        )
        info = await bot.get_webhook_info()
        return JSONResponse({
            "ok": True,
            "webhook_url": webhook_url,
            "pending_update_count": info.pending_update_count,
            "last_error_message": info.last_error_message,
        })
