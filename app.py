from flask import Flask, request
from telegram import Update
from telegram.ext import Application
from handlers.messages import register_handlers
import os

BOT_TOKEN=os.environ["BOT_TOKEN"]
SECRET=os.environ["WEBHOOK_SECRET"]

application=Application.builder().token(BOT_TOKEN).build()
register_handlers(application)

app=Flask(__name__)

@app.get("/")
def health():
    return {"status":"ok"}

@app.post(f"/webhook/{SECRET}")
async def webhook():
    update=Update.de_json(request.get_json(force=True),application.bot)
    await application.process_update(update)
    return {"ok":True}
