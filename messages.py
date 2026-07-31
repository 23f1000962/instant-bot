from telegram.ext import MessageHandler, ContextTypes, filters
from telegram import Update
from downloader import download_instagram
import os

async def handle(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    url=(update.message.text or "").strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Send a valid Instagram post/reel URL.")
        return
    status=await update.message.reply_text("⏳ Downloading...")
    try:
        path=download_instagram(url)
        await update.message.reply_document(open(path,"rb"))
        os.remove(path)
    except Exception:
        await status.edit_text("❌ Unable to download. The post may be private or temporarily unsupported.")
def register_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle))
