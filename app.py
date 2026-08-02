import os
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application

from messages import register_handlers

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .connect_timeout(60)
    .read_timeout(300)
    .write_timeout(300)
    .pool_timeout(300)
    .build()
)

register_handlers(telegram_app)

app = FastAPI()


@app.on_event("startup")
async def startup():
    await telegram_app.initialize()
    await telegram_app.start()
    logging.info("Telegram application started")


@app.on_event("shutdown")
async def shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()
    logging.info("Telegram application stopped")


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()

        update = Update.de_json(data, telegram_app.bot)

        await telegram_app.process_update(update)

        return JSONResponse(
            content={"ok": True},
            status_code=200,
        )

    except Exception:
        logging.exception("Webhook error")
        return JSONResponse(
            content={"ok": False},
            status_code=500,
        )
