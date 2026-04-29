"""Main bot handlers — onboarding, profile management, admin commands.

Does not handle chat/conversation; that lives in the character bot (handlers_char.py).
"""

import asyncio
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from src.history import get_full_profile, set_profile, get_stats, _get_connection, is_onboarded, set_onboarded, delete_all_user_data
from src.handlers_common import check_admin
from src.rate_limiter import rate_limiter
from src.input_filter import check_regex, strip_signals
import src.comfyui as comfyui
import src.grok_search as grok_search

logger = logging.getLogger(__name__)
TOS_URL = "https://telegra.ph/Ella-AI-%EC%9D%B4%EC%9A%A9%EC%95%BD%EA%B4%80--Terms-of-Service-04-07"
PRIVACY_URL = "https://telegra.ph/Ella-AI-개인정보-처리방침--Privacy-Policy-04-09"


# Character display order (used as the listing order even when persona has no profile_summary_ko)
# General (1-6) -> char09 (Park Su-yeon) -> char10 (Seo Yu-jin) -> fantasy (7, 8) -> image generator
_CHAR_ORDER = ["char01", "char02", "char03", "char04", "char05", "char06", "char09", "char10", "char07", "char08", "imagegen"]

# imagegen has no persona file, so the main bot defines its caption directly
_IMAGEGEN_SUMMARY = "🎨 Image Generator\nDescribe what you want in plain English and the AI will draw it. Mention a character name to generate them!"


def _get_char_summary(char_id: str, characters: dict) -> str | None:
    """Fetch the character profile summary. Prefers persona's profile_summary_ko; imagegen is special-cased."""
    if char_id == "imagegen":
        return _IMAGEGEN_SUMMARY
    cd = characters.get(char_id, {})
    summary = cd.get("profile_summary_ko")
    if summary:
        return summary
    # fallback: name + first line of description
    name = cd.get("name", char_id)
    desc = (cd.get("description") or "").strip().split("\n")[0][:200]
    return f"{name}\n{desc}" if desc else name


def _build_character_descriptions(characters: dict) -> str:
    """Build the joined character intro text for registered characters. (legacy)"""
    lines = []
    for char_id in characters:
        summary = _get_char_summary(char_id, characters)
        if not summary:
            continue
        lines.append(summary)
    return "\n\n".join(lines)


def _build_character_keyboard(characters: dict) -> InlineKeyboardMarkup | None:
    """Build an inline keyboard with character bot links."""
    keyboard = []
    for char_id, char_data in characters.items():
        bot_username = os.getenv(f"CHAR_USERNAME_{char_id}", "")
        if not bot_username:
            continue
        name = char_data.get("name", char_id)
        keyboard.append([InlineKeyboardButton(name, url=f"https://t.me/{bot_username}")])

    # Image generator button
    imagegen_username = os.getenv("CHAR_USERNAME_imagegen", "")
    if imagegen_username:
        keyboard.append([InlineKeyboardButton(
            "🎨 Image Generator", url=f"https://t.me/{imagegen_username}"
        )])

    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def _send_character_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, characters: dict):
    """For each registered character, send a separate message with profile image + caption + inline button."""
    project_root = Path(__file__).resolve().parents[1]

    # Build the list of characters to expose:
    # 1) Preserve _CHAR_ORDER (char01~08, imagegen) — only registered ones
    # 2) Plus any other characters in `characters` that have CHAR_USERNAME set (e.g. char_test in dev)
    char_ids: list[str] = []
    seen: set[str] = set()
    for cid in _CHAR_ORDER:
        char_ids.append(cid)
        seen.add(cid)
    for cid in characters.keys():
        if cid in seen:
            continue
        if os.getenv(f"CHAR_USERNAME_{cid}", ""):
            char_ids.append(cid)
            seen.add(cid)

    for char_id in char_ids:
        # Allow imagegen even if it's not in the characters dict (it's a separate bot — only username is needed)
        if char_id != "imagegen" and char_id not in characters:
            continue

        bot_username = os.getenv(f"CHAR_USERNAME_{char_id}", "")

        # Caption: persona's profile_summary_ko (or _IMAGEGEN_SUMMARY for imagegen)
        summary = _get_char_summary(char_id, characters)

        # Character metadata (for name extraction)
        char_data = characters.get(char_id, {})
        name = char_data.get("name", char_id)

        # Inline button assembly
        if not bot_username:
            # No username configured -> skip this character
            continue
        if char_id == "imagegen":
            label = "🎨 Start Image Generation"
        else:
            label = "💬 Start Chat"
        button = InlineKeyboardButton(label, url=f"https://t.me/{bot_username}")

        reply_markup = InlineKeyboardMarkup([[button]])

        # Profile image path
        image_path = project_root / "images" / "profile" / f"{char_id}.png"

        try:
            if image_path.exists():
                with open(image_path, "rb") as f:
                    await update.effective_chat.send_photo(
                        photo=f,
                        caption=summary,
                        reply_markup=reply_markup,
                    )
            else:
                # No image available — fallback to text
                await update.effective_chat.send_message(summary, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("character card send failed (%s): %s", char_id, e)
            # On failure, still try to surface a text message
            try:
                await update.effective_chat.send_message(summary, reply_markup=reply_markup)
            except Exception:
                pass

        # Avoid rate limits
        await asyncio.sleep(0.3)


async def main_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command — onboarding gate + welcome message + character bot links."""
    user_id = update.effective_user.id

    # Already onboarded -> welcome message
    if is_onboarded(user_id):
        await _send_welcome(update, context)
        return

    # Onboarding gate
    text = (
        "⚠️ This service is for users aged 19 and above.\n"
        "Please agree to the terms below to continue.\n\n"
        "• This service is an AI character chatbot that may contain adult content.\n\n"
        f"📋 Terms of Service:\n{TOS_URL}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ I Agree", callback_data="onboard_agree"),
            InlineKeyboardButton("❌ Decline", callback_data="onboard_decline"),
        ]
    ])
    await update.message.reply_text(text, reply_markup=keyboard)


async def _send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the welcome message to onboarded users."""
    user_id = update.effective_user.id if update.effective_user else 0
    characters = context.bot_data.get("characters", {})
    text = (
        "Hello! This is the Ella AI character chatbot.\n\n"
        "📋 Available commands:\n"
        "/char — pick a character\n"
        "/profile — view / set your profile\n"
        "/privacy — privacy policy\n"
        "/deletedata — delete your data\n"
    )
    if check_admin(user_id):
        text += (
            "\n🔧 Admin:\n"
            "/admin — admin menu\n"
        )
    text += (
        "\n📩 Character requests / inquiries: ella.ai.project@gmail.com\n"
        "\nPick a character below ⬇️\n"
    )
    await update.effective_chat.send_message(text)
    await _send_character_cards(update, context, characters)


async def onboard_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main bot onboarding agree/decline callback."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "onboard_agree":
        set_onboarded(user_id)
        logger.info("user %s onboarding accepted", user_id)
        await query.edit_message_text("✅ Agreed!")
        await _send_welcome(update, context)

    elif query.data == "onboard_decline":
        await query.edit_message_text(
            "You cannot use this service without agreement.\n\n"
            "Send /start to try again."
        )


async def char_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/char — character selection menu."""
    characters = context.bot_data.get("characters", {})
    if not characters:
        await update.message.reply_text("No character bots are registered.")
        return
    await update.message.reply_text("Pick a character:")
    await _send_character_cards(update, context, characters)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/profile command — view / set the global user profile. Free-form keys supported.

    The main bot always operates in the global scope.
    Per-character profile fields (e.g. nickname) are set from the character bot.
    """
    user_id = update.effective_user.id
    args = context.args if context.args else []

    # No args -> view profile
    if not args:
        profile = get_full_profile(user_id, "global")
        if not profile:
            await update.message.reply_text(
                "No profile set yet.\n\n"
                "Usage: /profile <key> <value>\n"
                "Examples: /profile name Junhee\n"
                "/profile location Seoul\n"
                "/profile favorite_team Tottenham"
            )
            return
        lines = []
        for key, data in profile.items():
            source_tag = " (auto)" if data["source"] == "auto" else ""
            lines.append(f"• {key}: {data['value']}{source_tag}")
        await update.message.reply_text("📋 Profile:\n" + "\n".join(lines))
        return

    # delete all -> wipe the entire profile
    key = args[0].lower()
    if key == "delete" and len(args) > 1 and args[1].lower() == "all":
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM user_profile WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()
        await update.message.reply_text("✅ Your entire profile has been deleted.")
        logger.info("user %s profile fully deleted", user_id)
        return

    # Set a profile entry (free-form key)
    value = " ".join(args[1:]) if len(args) > 1 else ""

    if not value:
        await update.message.reply_text(f"Usage: /profile {key} <value>\nDelete all: /profile delete all")
        return

    # Defense against injection in profile values
    value = strip_signals(value)
    blocked, pattern = check_regex(value)
    if blocked:
        logger.warning("[security] profile injection blocked: user=%s key=%s value=%s", user_id, key, value[:100])
        await update.message.reply_text("Your profile value contains content that is not allowed.")
        return

    set_profile(user_id, "global", key, value, source="manual")
    await update.message.reply_text(f"✅ Global profile set: {key} = {value}")
    logger.info("user %s profile set: %s=%s (scope=global)", user_id, key, value)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin — Admin menu."""
    if not check_admin(update.effective_user.id):
        return
    text = (
        "🔧 Admin menu:\n\n"
        "/stats — overall statistics\n"
        "/blocked — list blocked users\n"
        "/unblock <user_id> — unblock a user\n"
        "/runpod on|off|status — manage RunPod\n"
        "/runpod_video on|off|status — manage RunPod video"
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — overall statistics (Admin only)."""
    if not check_admin(update.effective_user.id):
        return
    stats = get_stats()
    text = (
        f"📊 Overall stats:\n\n"
        f"👥 Total users: {stats['total_users']}"
    )
    await update.message.reply_text(text)


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unblock <user_id> — unblock a user (Admin only)."""
    if not check_admin(update.effective_user.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /unblock <user_id>")
        return
    target_id = int(args[0])
    if rate_limiter.unblock(target_id):
        await update.message.reply_text(f"✅ User {target_id} unblocked")
    else:
        await update.message.reply_text(f"User {target_id} is not currently blocked.")


async def blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/blocked — list currently blocked users (Admin only)."""
    if not check_admin(update.effective_user.id):
        return
    blocked = rate_limiter.get_blocked_users()
    if not blocked:
        await update.message.reply_text("No users are currently blocked.")
        return
    lines = []
    for entry in blocked:
        mins = int(entry["remaining"] // 60)
        secs = int(entry["remaining"] % 60)
        lines.append(f"• user {entry['user_id']} — {mins}m {secs}s remaining")
    text = f"🚫 Blocked users: {len(blocked)}\n\n" + "\n".join(lines)
    await update.message.reply_text(text)


async def deletedata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deletedata — request personal data deletion."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Delete", callback_data="deletedata_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="deletedata_cancel"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ Are you sure you want to delete all of your data?\n\n"
        "What will be deleted:\n"
        "• All chat history\n"
        "• Chat summaries\n"
        "• User profile\n"
        "• Long-term memory (relationships, events)\n"
        "• Outfit settings\n"
        "• Usage records\n"
        "• Account settings (onboarding will be reset)\n\n"
        "⚠️ This cannot be undone.",
        reply_markup=keyboard,
    )


async def deletedata_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm/cancel personal data deletion."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "deletedata_confirm":
        deleted = delete_all_user_data(user_id)
        total = sum(deleted.values())
        logger.info("user %s data deletion done: %s (total %d rows)", user_id, deleted, total)
        await query.edit_message_text(
            "✅ All of your data has been deleted.\n\n"
            "Send /start again to re-register if you want to use the service later."
        )
    elif query.data == "deletedata_cancel":
        await query.edit_message_text("Cancelled. Your data is unchanged.")


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/privacy — privacy policy."""
    await update.message.reply_text(
        f"📋 Privacy Policy:\n{PRIVACY_URL}\n\n"
        "If you'd like to delete your data, send /deletedata."
    )


async def runpod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runpod on|off|status — manage RunPod Serverless (Admin only)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        # 1. Set workersMin=1
        await update.message.reply_text("Starting RunPod workers...")
        result = await comfyui.set_runpod_workers(1)
        if "error" in result:
            await update.message.reply_text(f"Failed to set RunPod workersMin: {result['error']}")
            return

        # 2. Wait for workers to be ready (up to 30s, polling every 5s)
        comfyui.runpod_enabled = True
        ready = False
        for _ in range(6):
            await asyncio.sleep(5)
            health = await comfyui.check_runpod_health()
            workers = health.get("workers", {})
            workers_ready = workers.get("ready", 0) + workers.get("idle", 0) + workers.get("running", 0)
            if workers_ready > 0:
                ready = True
                break

        if ready:
            await update.message.reply_text(
                f"✅ RunPod ON — workers ready\n"
                f"Workers: ready={workers.get('ready', 0)}, idle={workers.get('idle', 0)}, running={workers.get('running', 0)}"
            )
        else:
            health = await comfyui.check_runpod_health()
            await update.message.reply_text(
                f"⚠️ RunPod ON — enabled but workers not yet ready (cold start in progress)\n"
                f"Health: {health}\n"
                f"Try /runpod status again in a moment."
            )

    elif subcmd == "off":
        comfyui.runpod_enabled = False
        result = await comfyui.set_runpod_workers(0)
        if "error" in result:
            await update.message.reply_text(
                f"RunPod disabled (routing OFF)\n"
                f"⚠️ Failed to set workersMin=0: {result['error']}"
            )
        else:
            await update.message.reply_text("✅ RunPod OFF — routing disabled + workersMin=0")

    else:
        # status (default)
        enabled_str = "ON ✅" if comfyui.runpod_enabled else "OFF ❌"
        health = await comfyui.check_runpod_health()
        local_queue = await comfyui.check_queue()

        if "error" in health:
            runpod_status = f"Error: {health['error']}"
        else:
            workers = health.get("workers", {})
            jobs = health.get("jobs", {})
            runpod_status = (
                f"Workers — ready: {workers.get('ready', 0)}, idle: {workers.get('idle', 0)}, "
                f"running: {workers.get('running', 0)}, throttled: {workers.get('throttled', 0)}\n"
                f"Jobs — inQueue: {jobs.get('inQueue', 0)}, inProgress: {jobs.get('inProgress', 0)}, "
                f"completed: {jobs.get('completed', 0)}, failed: {jobs.get('failed', 0)}"
            )

        text = (
            f"🖥 RunPod status\n"
            f"Routing: {enabled_str}\n"
            f"Endpoint: {comfyui.RUNPOD_ENDPOINT_ID or '(unset)'}\n"
            f"Max Queue: {comfyui.RUNPOD_MAX_QUEUE}\n\n"
            f"📡 RunPod Health:\n{runpod_status}\n\n"
            f"🏠 Local GB10 ComfyUI:\n"
            f"Running: {local_queue.get('running', '?')}, Pending: {local_queue.get('pending', '?')}"
        )
        await update.message.reply_text(text)


async def runpod_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runpod_video on|off|status — manage RunPod video Serverless (Admin only)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        await update.message.reply_text("Starting RunPod video workers... (cold-start S3 download ~3-5 min)")
        # Force an active worker by setting workersMin=1 (enters running state + triggers S3 model download)
        result = await comfyui.set_runpod_video_workers(1, comfyui.RUNPOD_VIDEO_MAX_WORKERS)
        if "error" in result:
            await update.message.reply_text(f"Failed to configure RunPod video: {result['error']}")
            return

        comfyui.runpod_video_enabled = True
        # Wait for the worker to enter running state (up to 5 min, polling every 10s)
        running = False
        for _ in range(30):
            await asyncio.sleep(10)
            health = await comfyui.check_runpod_video_health()
            workers = health.get("workers", {})
            if workers.get("running", 0) > 0 or workers.get("ready", 0) > 0:
                running = True
                break

        if running:
            await update.message.reply_text(
                f"✅ RunPod Video ON — worker active\n"
                f"Workers: running={workers.get('running', 0)}, ready={workers.get('ready', 0)}, "
                f"idle={workers.get('idle', 0)}, initializing={workers.get('initializing', 0)}"
            )
        else:
            health = await comfyui.check_runpod_video_health()
            await update.message.reply_text(
                f"⚠️ RunPod Video ON — enabled but no worker ready within 5 min (S3 download may be delayed)\n"
                f"Health: {health}\n"
                f"Try /runpod_video status again in a moment."
            )

    elif subcmd == "off":
        comfyui.runpod_video_enabled = False
        result = await comfyui.set_runpod_video_workers(0, 0)
        if "error" in result:
            await update.message.reply_text(
                f"RunPod Video disabled (routing OFF)\n"
                f"⚠️ Failed to set workers: {result['error']}"
            )
        else:
            await update.message.reply_text("✅ RunPod Video OFF — routing disabled + workers=0")

    else:
        # status (default)
        enabled_str = "ON ✅" if comfyui.runpod_video_enabled else "OFF ❌"
        health = await comfyui.check_runpod_video_health()

        if "error" in health:
            runpod_status = f"Error: {health['error']}"
        else:
            workers = health.get("workers", {})
            jobs = health.get("jobs", {})
            runpod_status = (
                f"Workers — ready: {workers.get('ready', 0)}, idle: {workers.get('idle', 0)}, "
                f"running: {workers.get('running', 0)}, throttled: {workers.get('throttled', 0)}\n"
                f"Jobs — inQueue: {jobs.get('inQueue', 0)}, inProgress: {jobs.get('inProgress', 0)}, "
                f"completed: {jobs.get('completed', 0)}, failed: {jobs.get('failed', 0)}"
            )

        text = (
            f"🎬 RunPod Video status\n"
            f"Routing: {enabled_str}\n"
            f"Endpoint: {comfyui.RUNPOD_VIDEO_ENDPOINT_ID or '(unset)'}\n"
            f"Max Workers: {comfyui.RUNPOD_VIDEO_MAX_WORKERS}\n\n"
            f"📡 Health:\n{runpod_status}"
        )
        await update.message.reply_text(text)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/search on|off|status — toggle Grok web search (Admin only)."""
    if not check_admin(update.effective_user.id):
        return

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "on":
        grok_search.GROK_SEARCH_ENABLED = True
        await update.message.reply_text("✅ Grok Search ON — character web search enabled")

    elif subcmd == "off":
        grok_search.GROK_SEARCH_ENABLED = False
        await update.message.reply_text("✅ Grok Search OFF — character web search disabled")

    else:
        enabled_str = "ON ✅" if grok_search.GROK_SEARCH_ENABLED else "OFF ❌"
        month = grok_search._now_month()
        monthly_used = grok_search._monthly_count.get(month, 0)
        monthly_limit = grok_search.GROK_SEARCH_MONTHLY_LIMIT
        cache_size = len(grok_search._search_cache)

        text = (
            f"🔍 Grok Search status\n"
            f"Search: {enabled_str}\n"
            f"Monthly usage: {monthly_used}/{monthly_limit} ({month})\n"
            f"Cache: {cache_size} entries\n"
            f"Excluded characters: {os.getenv('SEARCH_EXCLUDED_CHARS', 'char07,char08')}"
        )
        await update.message.reply_text(text)


async def scene_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scene [key|off|list|status] — force a SFW scene override (Admin testing only).

    If the scene key exists in SFW_SCENES, the SFW override is pinned to it.

    - /scene list              — list SFW scene keys
    - /scene status            — show current override
    - /scene <sfw_key>         — pin to that SFW scene
    - /scene off / clear       — clear override
    """
    if not check_admin(update.effective_user.id):
        return

    from src import trait_pools

    args = context.args or []
    subcmd = args[0].lower() if args else "status"

    if subcmd == "list":
        sfw = trait_pools.list_sfw_scene_keys()
        text = (
            f"🌸 SFW Scene keys ({len(sfw)}):\n" + "\n".join(f"• {k}" for k in sfw)
        )
        await update.message.reply_text(text)
        return

    if subcmd in {"off", "clear", "none"}:
        ok, msg = trait_pools.set_forced_sfw_scene(None)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
        return

    if subcmd == "status":
        s_forced = trait_pools.get_forced_sfw_scene()
        lines = []
        lines.append(f"🌸 SFW: pinned to `{s_forced}`" if s_forced else "🌸 SFW: random")
        lines.append("\n(use /scene off to clear)")
        await update.message.reply_text("\n".join(lines))
        return

    key = args[0]
    sfw_keys = trait_pools.list_sfw_scene_keys()

    if key in sfw_keys:
        ok, msg = trait_pools.set_forced_sfw_scene(key)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
    else:
        await update.message.reply_text(
            f"❌ Unknown scene key '{key}'. Run /scene list to see available keys."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — command list."""
    user_id = update.effective_user.id if update.effective_user else 0
    text = (
        "📋 Commands:\n\n"
        "/start — start the service\n"
        "/char — pick a character\n"
        "/profile — view / set your profile\n"
        "/privacy — privacy policy\n"
        "/deletedata — delete your data\n"
        "/help — this help message\n"
    )
    if check_admin(user_id):
        text += (
            "\n🔧 Admin:\n"
            "/admin — admin menu\n"
        )
    text += "\n📩 Contact: ella.ai.project@gmail.com"
    await update.message.reply_text(text)


def register_main_handlers(app):
    """Register handlers on the main bot."""
    app.add_handler(CommandHandler("start", main_start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(onboard_main_callback, pattern="^onboard_"))
    app.add_handler(CommandHandler("char", char_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("blocked", blocked_command))
    app.add_handler(CommandHandler("unblock", unblock_command))
    app.add_handler(CommandHandler("deletedata", deletedata_command))
    app.add_handler(CallbackQueryHandler(deletedata_callback, pattern="^deletedata_"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("runpod", runpod_command))
    app.add_handler(CommandHandler("runpod_video", runpod_video_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("scene", scene_command))
