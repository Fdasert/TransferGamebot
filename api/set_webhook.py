"""
One-time webhook registration endpoint.

GET /api/set_webhook?token=<ADMIN_TOKEN>
  — registers the Vercel URL as the Telegram webhook and returns status info.

GET /api/set_webhook?token=<ADMIN_TOKEN>&action=info
  — returns current webhook info without changing anything.

GET /api/set_webhook?token=<ADMIN_TOKEN>&action=delete
  — deletes the webhook (switches bot to polling-ready state).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from telegram import Bot

from config import BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, WEBHOOK_BASE_URL, ADMIN_TOKEN

app = FastAPI(docs_url=None, redoc_url=None)

ALLOWED_UPDATES = ["message", "callback_query", "edited_message", "my_chat_member"]


@app.get("/api/set_webhook")
async def set_webhook(request: Request) -> JSONResponse:
    # Auth
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
                "last_error_date": str(info.last_error_date) if info.last_error_date else None,
            })

        if action == "delete":
            await bot.delete_webhook(drop_pending_updates=True)
            return JSONResponse({"ok": True, "action": "deleted"})

        # Default: set webhook
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
