"""
Vercel serverless webhook handler for the Telegram bot.

This module is the single entry point on Vercel. It:
  - Exposes POST /api/webhook  — receives Telegram updates
  - Exposes GET  /api/webhook  — healthcheck
  - Lazily initialises python-telegram-bot Application once per warm container
  - Validates the X-Telegram-Bot-Api-Secret-Token header
  - Always returns HTTP 200 to prevent Telegram retries on internal errors
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Make the project root importable (bot.py, database.py, config.py, etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from telegram import Update
from telegram.ext import Application

from bot import create_application, _reload_cosm_overrides
from config import BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(docs_url=None, redoc_url=None)

# ── Lazy singleton ────────────────────────────────────────────────────────────
_application: Application | None = None
_initialized: bool = False
_init_lock = asyncio.Lock()


async def _ensure_initialized() -> Application:
    """Initialize the PTB Application once per warm container."""
    global _application, _initialized
    if _initialized and _application is not None:
        return _application
    async with _init_lock:
        # Double-checked locking
        if _initialized and _application is not None:
            return _application
        logger.info("Cold start — initialising Application…")
        _application = create_application()
        _reload_cosm_overrides()
        await _application.initialize()
        _initialized = True
        logger.info("Application ready.")
    return _application


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/webhook")
async def healthcheck() -> JSONResponse:
    return JSONResponse({"ok": True, "status": "running"})


@app.post("/api/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    # 1. Validate secret token (prevents spoofed updates)
    if TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Rejected request: invalid secret token")
            return Response(status_code=403)

    # 2. Parse and process the update
    try:
        application = await _ensure_initialized()
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception:
        # Log but always return 200 — non-200 causes Telegram to retry
        logger.exception("Error processing Telegram update")

    return Response(status_code=200)
