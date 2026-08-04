import logging
import os

from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from downloader import download_instagram

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome folks!\n"
        "This bot takes time to wake up.🫡\n\n"
        "📥 Instructions to use this bot:\n\n"
        "• This bot works with public Instagram account's medias only.\n"
        "• If you return after a while, send 'Hi', 'Hey', or 'Start' to wake up the bot server.\n"
        "• Once the bot responds, send a valid Instagram Post or Reel link.\n"
        "• If an error occurs, wait a few seconds and resend the same link."
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip()
    lower_text = text.lower()

    # Wake-up messages
    if lower_text in ("hi", "hey", "hello", "start"):
        await update.message.reply_text(
            "✅ Bot is awake!\n\n"
            "Now send a valid Instagram Post or Reel link."
        )
        return

    # Validate Instagram URL
    if "instagram.com" not in text.lower():
        await update.message.reply_text(
            "⚠️ Please send a valid Instagram Post or Reel link."
        )
        return

    status = await update.message.reply_text("⏳ Downloading...")

    try:
        files = download_instagram(text)

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

        error = str(e).lower()

        if "502" in error:
            await status.edit_text(
                "❌ Failed to reach Instagram.\n\n"
                "Please resend the link after a few seconds."
            )

        elif "timeout" in error or "timed out" in error:
            await status.edit_text(
                "⏱️ Response time exceeded.\n\n"
                "Please resend the link after a few seconds."
            )

        else:
            await status.edit_text(
                "❌ Something went wrong.\n\n"
                "Please wait a few seconds and resend the link."
            )


def register_handlers(application):
    application.add_handler(CommandHandler("start", start))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle,
        )
    )
