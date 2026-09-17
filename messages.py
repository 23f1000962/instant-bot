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
# /start COMMAND
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
    # Simple greetings
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
        # download_instagram() uses synchronous requests/yt-dlp.
        #
        # Run it in a separate thread so it does not block
        # Telegram's asynchronous event loop.
        # ----------------------------------------------------

        files = await asyncio.to_thread(
            download_instagram,
            text,
        )

        if not files:
            raise RuntimeError(
                "No downloadable media was returned."
            )

        sent_count = 0

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

                sent_count += 1

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

                sent_count += 1

            # ------------------------------------------------
            # UNKNOWN FILE TYPE
            # ------------------------------------------------

            else:

                with open(path, "rb") as media:

                    await update.message.reply_document(
                        document=media,
                    )

                sent_count += 1

            # ------------------------------------------------
            # Delete file after sending
            # ------------------------------------------------

            try:
                os.remove(path)

            except OSError:
                logger.warning(
                    "Could not remove file: %s",
                    path,
                )

        # ----------------------------------------------------
        # Check if anything was actually sent
        # ----------------------------------------------------

        if sent_count == 0:
            raise RuntimeError(
                "Downloaded files could not be sent."
            )

        # ----------------------------------------------------
        # Delete processing message
        # ----------------------------------------------------

        try:
            await status.delete()

        except Exception:
            pass

    except Exception as error:

        logger.exception(
            "Instagram download failed"
        )

        error_text = str(error).lower()

        # ----------------------------------------------------
        # RapidAPI / API errors
        # ----------------------------------------------------

        if "407" in error_text:

            message = (
                "❌ Instagram API connection failed.\n\n"
                "RapidAPI returned HTTP 407. "
                "This is usually an API/provider connection "
                "problem rather than a Telegram bot problem."
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
        # Instagram content errors
        # ----------------------------------------------------

        elif (
            "not found" in error_text
            or "404" in error_text
        ):

            message = (
                "❌ Instagram content was not found.\n\n"
                "The post may have been deleted or the "
                "link may be invalid."
            )

        elif (
            "private" in error_text
            or "login required" in error_text
            or "authentication required" in error_text
        ):

            message = (
                "🔒 This Instagram content appears to be "
                "private or requires login.\n\n"
                "Only publicly accessible content is supported."
            )

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        elif (
            "timeout" in error_text
            or "timed out" in error_text
        ):

            message = (
                "⏱️ The download timed out.\n\n"
                "Instagram or the API provider may be "
                "temporarily slow. Please try again."
            )

        # ----------------------------------------------------
        # yt-dlp errors
        # ----------------------------------------------------

        elif "yt-dlp" in error_text:

            message = (
                "❌ Instagram could not be downloaded.\n\n"
                "The fallback downloader was unable to "
                "extract the media from this link."
            )

        # ----------------------------------------------------
        # Generic error
        # ----------------------------------------------------

        else:

            message = (
                "❌ I couldn't download this Instagram link.\n\n"
                "Please make sure the content is public and "
                "the link is valid, then try again."
            )

        # ----------------------------------------------------
        # Delete processing message
        # ----------------------------------------------------

        try:
            await status.delete()

        except Exception:
            pass

        # ----------------------------------------------------
        # Send error to user
        # ----------------------------------------------------

        try:

            await update.message.reply_text(
                message
            )

        except Exception:

            logger.exception(
                "Could not send error message"
            )

        # ----------------------------------------------------
        # Cleanup any remaining files
        # ----------------------------------------------------

        for path in files:

            try:

                if (
                    path
                    and os.path.isfile(path)
                ):
                    os.remove(path)

            except OSError:

                logger.warning(
                    "Could not clean up file: %s",
                    path,
                )


# ============================================================
# REGISTER TELEGRAM HANDLERS
# ============================================================

def register_handlers(application):
    """
    Register all Telegram bot handlers.

    This function is imported by app.py.
    """

    # /start command
    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # Normal text messages
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle,
        )
    )