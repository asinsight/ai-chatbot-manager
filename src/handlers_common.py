"""handlers_common.py — Shared utilities for main bot / character bot handlers."""

import logging
import os

from src.history import (
    save_message, get_history, get_active_character, set_active_character,
    clear_history, get_message_count, get_latest_summary, save_summary,
    delete_old_messages, get_full_profile, set_profile, get_memories,
    save_memory, delete_oldest_events, _get_connection,
)
from src.summary import summarize_messages, extract_memory_and_profile
from src.input_filter import strip_signals
from src.profile_keys import canonicalize as _canon_key


def check_admin(user_id: int) -> bool:
    """Check whether the user is an Admin (based on .env)."""
    admin_ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    return str(user_id) in [x.strip() for x in admin_ids]


def get_admin_ids() -> list[int]:
    """List of configured Admin user IDs."""
    raw = os.getenv("ADMIN_USER_IDS", "")
    ids = []
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            ids.append(int(x))
    return ids


async def notify_admins_video(
    context,
    *,
    triggering_user_id: int,
    source: str,        # "char_bot" or "imagegen"
    char_id: str = "",  # char01~10 or "imagegen"
    status: str,        # "started" / "success" / "failed" / "blocked"
    pose_key: str = "",
    safety_level: str = "",
    motion_prompt: str = "",
    audio_prompt: str = "",
    extra: str = "",
) -> None:
    """Notify all Admins about a video generation event.

    **VIDEO_DEBUG_DUMP=1 env guard** — only sent in debug mode (prevents message spam in normal use).
    Failures are silently swallowed.
    """
    if os.getenv("VIDEO_DEBUG_DUMP", "0") != "1":
        return
    admin_ids = get_admin_ids()
    if not admin_ids:
        return

    icon_map = {"started": "🎬", "success": "✅", "failed": "❌", "blocked": "🚫"}
    icon = icon_map.get(status, "📹")
    lines = [
        f"{icon} Video {status} — {source}",
        f"User: `{triggering_user_id}`",
    ]
    if char_id:
        lines.append(f"Char: `{char_id}`")
    if pose_key:
        lines.append(f"Pose: `{pose_key}` | Safety: `{safety_level or 'N/A'}`")
    if motion_prompt:
        mp = motion_prompt[:400] + ("…" if len(motion_prompt) > 400 else "")
        lines.append(f"Motion: {mp}")
    if audio_prompt:
        ap = audio_prompt[:200] + ("…" if len(audio_prompt) > 200 else "")
        lines.append(f"Audio: {ap}")
    if extra:
        lines.append(extra)
    msg = "\n".join(lines)

    for aid in admin_ids:
        try:
            await context.bot.send_message(chat_id=aid, text=msg, parse_mode="Markdown")
        except Exception:
            try:
                # Markdown parsing failed — retry with plain text
                await context.bot.send_message(chat_id=aid, text=msg[:4000])
            except Exception as _e:
                logger.warning("admin video notify failed: admin=%s err=%s", aid, _e)

logger = logging.getLogger(__name__)


def _get_character(context, user_id):
    """Return the user's active character."""
    # Multi-bot: for character bots, char_id is fixed in bot_data
    if "char_id" in context.bot_data and "character" in context.bot_data:
        return context.bot_data["char_id"], context.bot_data["character"]
    # Legacy / main bot: look up from DB
    characters = context.bot_data.get("characters", {})
    char_id = get_active_character(user_id)
    if char_id in characters:
        return char_id, characters[char_id]
    # fallback: first character
    first_id = next(iter(characters), None)
    if first_id:
        return first_id, characters[first_id]
    return "default", context.bot_data.get("character", {})


async def _run_summary(user_id: int, char_id: str, recent_keep: int) -> None:
    """Async summary + long-term memory / profile extraction."""
    try:
        all_messages = get_history(user_id, limit=9999, character_id=char_id)
        if len(all_messages) <= recent_keep:
            return

        # Summary target: everything except the most recent `keep` messages
        to_summarize = all_messages[:-recent_keep]
        existing_summary = get_latest_summary(user_id, char_id)

        # If a previous summary exists, prepend it for continuity (max 500 chars — prevents accumulation)
        max_prev_summary = int(os.getenv("SUMMARY_MAX_PREV_CHARS", "500"))
        if existing_summary:
            truncated = existing_summary[:max_prev_summary]
            to_summarize.insert(0, {"role": "system", "content": f"Previous summary: {truncated}"})

        # 1. Generate summary
        summary = await summarize_messages(to_summarize)
        if summary and summary != "(summary unavailable)":
            save_summary(user_id, char_id, summary, len(to_summarize))
            deleted = delete_old_messages(user_id, char_id, keep_recent=recent_keep)
            logger.info("user %s character %s summary done: %d messages compressed, %d deleted", user_id, char_id, len(to_summarize), deleted)
        else:
            logger.warning("user %s character %s summary failed", user_id, char_id)

        # 1-1. Flush character stats to DB (write cache when summary is triggered)
        try:
            from src.history import flush_character_stats
            flush_character_stats(user_id, char_id)
        except Exception:
            pass

        # 2. Long-term memory + profile extraction
        extracted = await extract_memory_and_profile(to_summarize, truncated if existing_summary else "")

        # Save relationship (overwrite) — sanitize
        if extracted.get("relationship"):
            save_memory(user_id, char_id, "relationship", strip_signals(extracted["relationship"]))
            logger.info("user %s character %s relationship updated", user_id, char_id)

        # Save events (append)
        for event in extracted.get("events", []):
            if event.strip():
                save_memory(user_id, char_id, "event", strip_signals(event.strip()))
        delete_oldest_events(user_id, char_id, keep=10)

        # user_info → save to profile (only non-manual entries) — normalize to canonical key
        for key, value in extracted.get("user_info", {}).items():
            if not value or not value.strip():
                continue
            canon = _canon_key(key)
            existing = get_full_profile(user_id, char_id)
            if canon in existing and existing[canon].get("source") == "manual":
                continue
            set_profile(user_id, "global", canon, strip_signals(value.strip()), source="auto")
            logger.info("user %s profile auto-extracted: %s=%s (LLM key='%s')", user_id, canon, value.strip(), key)

    except Exception as e:
        logger.error("error during summary/extract: %s", e)
