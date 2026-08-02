import logging
import os

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from downloader import download_instagram

logger = logging.getLogger(__name__)


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    url = update.message.text.strip()

    if "instagram.com" not in url:
        await update.message.reply_text(
            "Please send a valid Instagram Reel or Post URL."
        )
        return

    status = await update.message.reply_text("⏳ Downloading...")

    try:
        files = download_instagram(url)

        # Convert single file to list
        if isinstance(files, str):
            files = [files]

        for path in files:
            with open(path, "rb") as media:

                if path.lower().endswith((".mp4", ".mov", ".mkv")):
                    await update.message.reply_video(video=media)
                else:
                    await update.message.reply_photo(photo=media)

            if os.path.exists(path):
                os.remove(path)

        await status.delete()

    except Exception as e:
        logger.exception("Download failed")

        await status.edit_text(
            f"❌ Error:\n{str(e)}"
        )


def register_handlers(application):
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle,
        )
    )
