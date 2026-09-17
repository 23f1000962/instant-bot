import asyncio
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


# ============================================================
# /start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.message is None:
        return

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "📥 Send me a public Instagram link and I will "
        "try to download the media.\n\n"

        "Supported:\n"
        "• 🎬 Reels\n"
        "• 🖼️ Image posts\n"
        "• 🎥 Video posts\n"
        "• 📚 Carousel posts\n"
        "• 👤 Profile picture\n\n"

        "⚠️ Only publicly accessible Instagram content "
        "can be downloaded."
    )


# ============================================================
# MAIN MESSAGE HANDLER
# ============================================================

async def handle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.message is None:
        return

    if update.message.text is None:
        return

    text = update.message.text.strip()

    if not text:
        return

    lower_text = text.lower()

    # --------------------------------------------------------
    # Wake-up messages
    # --------------------------------------------------------

    if lower_text in (
        "hi",
        "hey",
        "hello",
        "start",
    ):

        await update.message.reply_text(
            "✅ Bot is awake!\n\n"
            "Now send an Instagram Reel, Post, "
            "or Profile link."
        )

        return

    # --------------------------------------------------------
    # Validate Instagram URL
    # --------------------------------------------------------

    if "instagram.com" not in lower_text:

        await update.message.reply_text(
            "⚠️ Please send a valid Instagram URL."
        )

        return

    # --------------------------------------------------------
    # Status message
    # --------------------------------------------------------

    status = await update.message.reply_text(
        "⏳ Processing your Instagram link..."
    )

    files = []

    try:

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # download_instagram() is synchronous because it uses
        # requests/yt-dlp.
        #
        # Run it in a separate thread so it doesn't block
        # Telegram's async event loop.
        # ----------------------------------------------------

        files = await asyncio.to_thread(
            download_instagram,
            text,
        )

        if not files:

            raise RuntimeError(
                "No downloadable media was returned."
            )

        # ----------------------------------------------------
        # Send downloaded files
        # ----------------------------------------------------

        for path in files:

            if not os.path.isfile(path):

                logger.warning(
                    "File does not exist: %s",
                    path,
                )

                continue

            extension = (
                os.path.splitext(path)[1]
                .lower()
            )

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

            if extension in (
                ".mp4",
                ".m4v",
                ".mov",
                ".webm",
                ".mkv",
            ):

                with open(path, "rb") as media:

                    await update.message.reply_video(
                        video=media,
                        supports_streaming=True,
                    )

            # ------------------------------------------------
            # IMAGE
            # ------------------------------------------------

            elif extension in (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
            ):

                with open(path, "rb") as media:

                    await update.message.reply_photo(
                        photo=media,
                    )

            # ------------------------------------------------
            # UNKNOWN FILE
            # ------------------------------------------------

            else:

                with open(path, "rb") as media:

                    await update.message.reply_document(
                        document=media,
                    )

            # ------------------------------------------------
            # Delete file immediately after sending
            # ------------------------------------------------

            try:

                os.remove(path)

            except OSError:

                logger.warning(
                    "Could not remove file: %s",
                    path,
                )

        # ----------------------------------------------------
        # Remove status
        # ----------------------------------------------------

        try:

            await status.delete()

        except Exception:

            pass

    except Exception as error:

        logger.exception(
            "Instagram download failed",
        )

        error_text = str(error).lower()

        # ----------------------------------------------------
        # RapidAPI errors
        # ----------------------------------------------------

        if "407" in error_text:

            message = (
                "❌ Instagram API connection failed.\n\n"
                "RapidAPI returned HTTP 407. "
                "This is usually an API/provider connection "
                "problem, not a Telegram bot problem."
            )

        elif "401" in error_text:

            message = (
                "❌ RapidAPI authentication failed.\n\n"
                "Please check your RAPIDAPI_KEY."
            )

        elif "403" in error_text:

            message = (
                "❌ RapidAPI rejected the request.\n\n"
                "Check that your RapidAPI subscription "
                "for the Instagram API is active."
            )

        elif "429" in error_text:

            message = (
                "⚠️ RapidAPI rate limit reached.\n\n"
                "Please try again later."
            )

        # ----------------------------------------------------
        # Instagram