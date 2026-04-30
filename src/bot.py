"""
Multi-bot entry point.

Runs the main bot (admin) and N character bots (chat) concurrently in a single
process. Each bot has its own Application instance and uses bot_data to keep
its configuration isolated.

Env vars:
  MAIN_BOT_TOKEN    — main bot token (onboarding, profile, admin)
  CHAR_BOT_{char_id} — character bot token (chat, image)
"""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv
load_dotenv()  # load .env before module imports (so module-level os.getenv works)

from telegram.ext import ApplicationBuilder

from src.handlers_main import register_main_handlers
from src.handlers_char import register_char_handlers
from src.handlers_imagegen import register_imagegen_handlers
from src.history import init_db, set_admin
from src.prompt import load_all_characters, load_system_config
from src.logging_config import setup_logging
from src.llm_queue import llm_queue
from src.watchdog import notify_admins, comfyui_watchdog

setup_logging()
logger = logging.getLogger(__name__)


def _uncaught_exception_handler(exc_type, exc_value, exc_tb):
    """sys.excepthook — log uncaught exceptions before the process exits."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


def _asyncio_exception_handler(loop, context):
    """Asyncio event-loop uncaught exception handler."""
    msg = context.get("exception", context.get("message", "Unknown asyncio error"))
    logger.error("Asyncio exception: %s", msg)


async def main():
    # ── Install exception handlers ──
    sys.excepthook = _uncaught_exception_handler
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)

    # ── DB init ──
    init_db()

    # ── Start the LLM queue worker ──
    await llm_queue.start()

    # ── Register admin accounts ──
    admin_ids = os.getenv("ADMIN_USER_IDS", "")
    for uid in admin_ids.split(","):
        uid = uid.strip()
        if uid:
            set_admin(int(uid), True)
            logger.info("admin registered: %s", uid)

    # ── Load character + system configuration ──
    characters = load_all_characters()
    if not characters:
        raise SystemExit("No character JSON files found under persona/.")
    logger.info("loaded %d characters: %s", len(characters), ", ".join(characters.keys()))

    system_config = load_system_config()
    logger.info("master system prompt loaded")

    # ── Register bots ──
    apps: list[tuple[str, any]] = []  # list of (name, Application) pairs

    # Main bot — REQUIRED. The character / imagegen bots assume the main bot is
    # alive (deep-link handoffs, onboarding redirects). Refuse to start without it.
    main_token = os.getenv("MAIN_BOT_TOKEN", "").strip()
    main_username = os.getenv("MAIN_BOT_USERNAME", "").strip()
    if not main_token or not main_username:
        missing = []
        if not main_token: missing.append("MAIN_BOT_TOKEN")
        if not main_username: missing.append("MAIN_BOT_USERNAME")
        raise SystemExit(
            "Main bot is not configured — missing " + " + ".join(missing)
            + " in .env. Set both values and try again."
        )
    main_app = ApplicationBuilder().token(main_token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
    main_app.bot_data["characters"] = characters
    main_app.bot_data["system_config"] = system_config
    register_main_handlers(main_app)
    apps.append(("main", main_app))
    logger.info("main bot registered")

    # Character bots — map CHAR_BOT_{char_id} token per char_id
    for char_id, char_data in characters.items():
        token = os.getenv(f"CHAR_BOT_{char_id}")
        if not token:
            continue
        char_app = ApplicationBuilder().token(token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
        char_app.bot_data["char_id"] = char_id
        char_app.bot_data["character"] = char_data
        char_app.bot_data["characters"] = characters  # for full character reference
        char_app.bot_data["system_config"] = system_config
        register_char_handlers(char_app)
        apps.append((char_id, char_app))
        logger.info("character bot registered: %s (%s)", char_id, char_data.get("name", char_id))

    # Image-generator bot — registered separately from characters
    imagegen_token = os.getenv("CHAR_BOT_imagegen")
    if imagegen_token:
        imagegen_app = ApplicationBuilder().token(imagegen_token).write_timeout(60).media_write_timeout(120).read_timeout(30).connect_timeout(20).pool_timeout(10).build()
        imagegen_app.bot_data["characters"] = characters
        imagegen_app.bot_data["system_config"] = system_config
        register_imagegen_handlers(imagegen_app)
        apps.append(("imagegen", imagegen_app))
        logger.info("image generator bot registered")

    if not apps:
        raise SystemExit(
            "No bots registered. "
            "Set MAIN_BOT_TOKEN or CHAR_BOT_* tokens in .env."
        )

    logger.info("starting %d bots...", len(apps))

    # ── Initialize all bots and start polling (non-blocking) ──
    for name, app in apps:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("bot polling started: %s", name)

    logger.info("all bots running. Ctrl+C to exit.")

    # ── Admin start notification + ComfyUI watchdog ──
    # Use the main bot's instance for notifications
    main_bot = None
    for name, app in apps:
        if name == "main":
            main_bot = app.bot
            break
    if main_bot is None and apps:
        # If no main bot, use the first registered bot
        main_bot = apps[0][1].bot

    watchdog_task = None
    admin_notify = os.getenv("ADMIN_NOTIFY", "1") == "1"
    if main_bot:
        if admin_notify:
            try:
                await notify_admins(main_bot, "✅ Bot started.")
            except Exception as e:
                logger.error("admin start notify failed: %s", e)
        watchdog_task = asyncio.create_task(comfyui_watchdog(main_bot))

    # ── Wait for shutdown signal ──
    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # ── Graceful shutdown ──
    logger.info("shutting down bots...")

    # Cancel the watchdog
    if watchdog_task is not None:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

    # Admin shutdown notification
    if main_bot and admin_notify:
        try:
            await notify_admins(main_bot, "⚠️ Bot is shutting down.")
        except Exception as e:
            logger.error("admin shutdown notify failed: %s", e)

    await llm_queue.stop()
    for name, app in apps:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("bot stopped: %s", name)

    logger.info("all bots stopped.")


if __name__ == "__main__":
    asyncio.run(main())
