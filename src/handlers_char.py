"""Character bot handlers — handlers registered on each character bot in the multi-bot architecture.

Assumes each bot's bot_data has `char_id` and `character` populated.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from src.handlers_common import _get_character, _run_summary, check_admin, notify_admins_video
from src.history import (
    save_message, get_history, get_message_count,
    get_full_profile, get_memories, get_latest_summary, clear_history,
    is_onboarded, get_usage, increment_usage,
    get_outfit, set_outfit, reset_outfit,
    increment_daily_images, increment_daily_videos,
    get_character_stats, update_character_stats,
    increment_total_turns, _stats_cache, _schedule_flush,
    _normalize_location_key,
)
from src.llm_queue import llm_queue, QueueFullError, QueueTimeoutError
from src.prompt import build_messages, replace_macros, SEARCH_EXCLUDED_CHARS
from src.grok import generate_danbooru_tags, _load_image_config
from src.comfyui import generate_image, check_queue
from src.watchdog import notify_image_timeout
from src.rate_limiter import rate_limiter
from src.input_filter import filter_input, is_non_character_image_request
from src.video_context import (
    store_video_context as _store_video_context,
    get_video_context as _get_video_context,
    cleanup_video_context as _cleanup_video_context,
)

logger = logging.getLogger(__name__)

MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "")

# SFW denylist — defense-in-depth for [OUTFIT: ...] parser.
# Keyword literals live in config/sfw_denylist.json (not in code) so PMs can
# tune the list without editing Python. If the LLM emits an outfit value
# containing a denied token despite the system prompt's full-clothing
# invariant, the parser silently drops it instead of persisting it.
_SFW_DENYLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "sfw_denylist.json"
_DENIED_OUTFIT_TOKENS: frozenset[str] = frozenset()
try:
    with open(_SFW_DENYLIST_PATH, "r", encoding="utf-8") as _f:
        _denylist = json.load(_f)
    _DENIED_OUTFIT_TOKENS = frozenset(
        k.lower().strip()
        for k in _denylist.get("outfit_state_keywords", [])
        if isinstance(k, str) and k.strip()
    )
    logger.info(
        "SFW denylist loaded: %d outfit-state tokens",
        len(_DENIED_OUTFIT_TOKENS),
    )
except Exception as _exc:
    logger.warning("sfw_denylist.json load failed (%s) — proceeding without denylist", _exc)


# P10 Phase 2 — Location research in-flight dedup (avoid back-to-back duplicate requests)
_location_research_inflight: set[str] = set()


async def _research_location_bg(location_key: str) -> None:
    """Background location research — on cache miss, run a Grok search and persist to DB.

    Fire-and-forget. Failures must not affect the main chat flow.
    Includes an in-memory guard to prevent duplicate in-flight requests.
    """
    from src.history import get_location_context
    from src.grok_search import search_location

    key = _normalize_location_key(location_key or "")
    if not key:
        return

    # Already cached -> bail immediately to avoid an unnecessary API call
    if get_location_context(key):
        return

    # Dedup concurrent requests
    if key in _location_research_inflight:
        return
    _location_research_inflight.add(key)

    try:
        result = await search_location(key)
        if result:
            logger.info("Location research queued success: %s", key)
        else:
            logger.info("Location research queued no-result: %s", key)
    except Exception as e:
        logger.error("Location research background task failed (%s): %s", key, e)
    finally:
        _location_research_inflight.discard(key)


def _parse_outfit_signal(text: str) -> str | None:
    """Extract the [OUTFIT: ...] signal from an LLM response. Returns None if absent.

    SFW invariant (config/grok_prompts.json): clothing is always full and
    intact — the LLM should never emit a state-style outfit (e.g. partial
    undress). Defense-in-depth: if the extracted value contains any token
    from config/sfw_denylist.json (whole-token match against the
    comma-split tag list, OR substring match for compound phrases like
    "underwear only"), the whole emission is silently dropped — we do
    NOT cherry-pick "safe" sub-tags out of a CSV that contains a denied
    one. Otherwise the value flows into the standard Grok tag converter.
    """
    match = re.search(r"\[OUTFIT:\s*(.+?)\]", text, re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).strip()
    if not raw:
        return None

    if _DENIED_OUTFIT_TOKENS:
        lowered = raw.lower()
        # Whole-tag check on the CSV-split list: catches single-word
        # state tokens that appear as their own comma-separated entry.
        for tag in _split_tags(lowered):
            if tag in _DENIED_OUTFIT_TOKENS:
                logger.debug(
                    "[OUTFIT] denied token in tag list — dropping emission: %r",
                    raw,
                )
                return None
        # Substring check: catches multi-word state phrases and tokens
        # embedded inside a longer value without comma separation.
        for token in _DENIED_OUTFIT_TOKENS:
            if token in lowered:
                logger.debug(
                    "[OUTFIT] denied substring %r — dropping emission: %r",
                    token, raw,
                )
                return None

    return raw


def _split_tags(text: str) -> list[str]:
    """Split a comma-separated tag string into a trimmed list."""
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]


async def _convert_outfit_tags(description: str) -> dict | None:
    """Convert a natural-language outfit description into Danbooru tags. Lightweight Grok call."""
    from openai import AsyncOpenAI

    api_key = os.getenv("GROK_API_KEY", "")
    if not api_key:
        return None

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    model = os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")

    prompt = (
        "Convert this clothing description to accurate Danbooru tags.\n"
        "Use only well-known Danbooru clothing/underwear tags.\n\n"
        f"Description: {description}\n\n"
        'Respond with JSON only: {"clothing": "tag1, tag2", "underwear": "tag1, tag2"}\n'
        'If underwear is not mentioned, set underwear to empty string.'
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            return None
        import json as _json
        data = _json.loads(json_match.group(0))
        return data if data.get("clothing") else None
    except Exception as e:
        logger.error("outfit tag conversion failed: %s", e)
        return None


async def char_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start handler — checks onboarding and sends the character bot's first_mes."""
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    user_name = update.effective_user.first_name or "User"
    user_id = update.effective_user.id

    # Onboarding check — if incomplete, redirect to the main bot
    if not is_onboarded(user_id):
        link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = (
            "Please complete age verification + terms of service in the main bot first."
        )
        if link:
            text += f"\n\n👉 {link}"
        await update.message.reply_text(text)
        return

    # Send first_mes
    first_mes = character.get("first_mes", "")
    if first_mes:
        first_mes = replace_macros(first_mes, character["name"], user_name)

    # Send profile photo (anchor image)
    anchor_image = character.get("anchor_image", "")
    if anchor_image:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        image_path = os.path.join(base_dir, "images", "profile", anchor_image)
        if os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(photo=photo)

    greeting = first_mes or "Hi! Ask me anything :)"
    await update.message.reply_text(greeting)

    # Save first_mes into history (so it's part of context next turn)
    if first_mes:
        save_message(user_id, "assistant", first_mes, character_id=char_id)
        logger.info("sent first_mes to user %s and stored in history (char=%s)", user_id, char_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text message handler — builds the prompt from history + character card and returns the LLM reply."""
    user_text = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "User"

    # Rate limit check
    allowed, reason = rate_limiter.check(user_id)
    if not allowed:
        if reason == "rate_limit":
            await update.message.reply_text("Hold on... slow down a bit. You're typing too fast.")
        elif reason == "spam_blocked":
            await update.message.reply_text("Let's pick this up in a bit.")
        return

    # Prompt-injection filter
    user_text, blocked, block_reason = await filter_input(user_text)
    if blocked:
        logger.warning("[security] injection blocked: user=%s reason=%s text=%s", user_id, block_reason, update.message.text[:100])
        await update.message.reply_text("Hmm? I'm not sure what you mean~")
        return

    # Onboarding check
    if not is_onboarded(user_id):
        await update.message.reply_text("Please send /start to complete age verification + terms of service before using the service.")
        return

    char_id, character = _get_character(context, user_id)

    system_config = context.bot_data.get("system_config")

    # Read character stats once (reused below) + bump the turn count immediately
    _cached_stats = get_character_stats(user_id, char_id)
    turn_num = increment_total_turns(user_id, char_id)
    _cached_stats = get_character_stats(user_id, char_id)

    # Pull history + profile + memory + summary -> assemble prompt
    # Only RECENT_MESSAGES_KEEP messages are exposed to the LLM (peak token control)
    # Older messages are absorbed into the running summary on the next cycle
    history_limit = int(os.getenv("RECENT_MESSAGES_KEEP", "5"))
    chat_history = get_history(user_id, character_id=char_id, limit=history_limit)
    summary = get_latest_summary(user_id, char_id)
    profile = get_full_profile(user_id, char_id)
    memories = get_memories(user_id, char_id)
    messages = build_messages(
        character, chat_history, user_text, user_name, system_config,
        profile=profile, memories=memories, summary=summary,
        user_id=user_id, char_id=char_id,
        turn_count=get_message_count(user_id, char_id),
    )

    async def keep_typing():
        """While waiting for the LLM response, send a typing indicator every 3 seconds."""
        while True:
            await update.message.chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(3)

    typing_task = asyncio.create_task(keep_typing())
    try:
        char_max_tokens = character.get("max_tokens", 250)
        reply = await llm_queue.enqueue(messages, user_id=user_id, task_type="chat", max_tokens=char_max_tokens)
    except QueueFullError:
        typing_task.cancel()
        await update.message.reply_text("Lots of people are chatting right now... try me again in a bit!")
        return
    except QueueTimeoutError:
        typing_task.cancel()
        await update.message.reply_text("This is taking too long... please try again!")
        return
    finally:
        typing_task.cancel()

    # ── Grok Search two-pass ──
    search_match = re.search(r"\[SEARCH:\s*(.+?)\]", reply)
    if search_match and char_id not in SEARCH_EXCLUDED_CHARS:
        search_query = search_match.group(1).strip()
        logger.info("[SEARCH] signal detected (user %s): query='%s'", user_id, search_query)
        # Keep the typing indicator running across the search + second LLM call
        typing_task_search = asyncio.create_task(keep_typing())
        try:
            try:
                from src.grok_search import search as grok_search
                search_results = await grok_search(search_query, user_id=user_id)
            except Exception as e:
                logger.warning("Grok Search call failed: %s", e)
                search_results = ""

            if search_results:
                # Re-assemble the prompt with the search results included
                messages_with_search = build_messages(
                    character, chat_history, user_text, user_name,
                    system_config,
                    profile=profile, memories=memories, summary=summary,
                    user_id=user_id, char_id=char_id,
                    turn_count=get_message_count(user_id, char_id),
                    search_results=search_results,
                )
                try:
                    reply = await llm_queue.enqueue(
                        messages_with_search, user_id=user_id,
                        task_type="chat", max_tokens=char_max_tokens,
                    )
                except (QueueFullError, QueueTimeoutError):
                    reply = re.sub(r"\[SEARCH:\s*.+?\]", "", reply).strip()
                    if not reply:
                        reply = "Hmm... I tried to look it up but couldn't."
            else:
                # Search failed — strip the signal and use the first-pass response
                reply = re.sub(r"\[SEARCH:\s*.+?\]", "", reply).strip()
        finally:
            typing_task_search.cancel()

    # Strip <think>...</think> blocks (internal reasoning from reasoning models)
    reply = re.sub(r"</?think>", "", reply)
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
    if "<think>" in reply:
        reply = reply.split("<think>")[0]
    # Strip markdown formatting (*bold*, _italic_)
    reply = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", reply)
    reply = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", reply)
    reply = reply.strip()

    # Error check
    if reply.startswith("[error]") or reply.startswith("[Error]"):
        logger.warning("LLM error response, skipping history save: %s", reply)
        await update.message.reply_text(reply)
        return

    # LLM response debug log
    logger.info("LLM response (user %s): %s", user_id, reply)

    # Parse [STAT: ...] signal — update DB (must not break the main flow if it errors)
    # Format: [STAT: fixation+3, mood:jealous, location:bedroom]
    try:
        stat_match = re.search(r'\[STAT:\s*(.+?)\]', reply)
        if stat_match:
            stat_str = stat_match.group(1)
            fixation_delta = 0
            stat_mood = ""
            stat_location = ""
            for part in stat_str.split(","):
                part = part.strip()
                if part.startswith("fixation"):
                    fd_match = re.search(r'[+-]\d+', part)
                    if fd_match:
                        fixation_delta = int(fd_match.group())
                elif part.startswith("mood:"):
                    stat_mood = part.split(":")[1].strip()
                elif part.startswith("location:"):
                    stat_location = _normalize_location_key(part.split(":", 1)[1])
            update_character_stats(user_id, char_id, fixation_delta, stat_mood, location=stat_location, stat_limits=character.get("stat_limits"))
            logger.info("character stats updated (user %s, %s): fix=%+d, mood=%s, loc=%s",
                        user_id, char_id, fixation_delta, stat_mood or "(unchanged)", stat_location or "(unchanged)")

            # P10 Phase 2 — when a new location is detected, kick off async research (non-blocking)
            # Cache-hit check happens inside _research_location_bg
            if stat_location:
                try:
                    asyncio.create_task(_research_location_bg(stat_location))
                except Exception as _e:
                    logger.debug("location research task spawn failed: %s", _e)
    except Exception as e:
        logger.error("character stats parse/update failed (user %s): %s", user_id, e)

    # Image-signal parsing — only match SEND_IMAGE / photo sent
    # Other signals like [STAT:], [MOOD:], [OUTFIT:] must not match here
    image_signal_pattern = r"\[(SEND_IMAGE|photo sent):\s*(.+?)\]"
    image_match = re.search(image_signal_pattern, reply, re.IGNORECASE)
    # 2) Bare form without brackets: SEND_IMAGE: ...
    if not image_match:
        bare_pattern = r"(?:SEND_IMAGE|photo sent):\s*(.+?)$"
        image_match = re.search(bare_pattern, reply, re.IGNORECASE | re.MULTILINE)

    # 3) Hard keyword trigger — even if the LLM omits the signal, force generation when the user clearly asks.
    force_image = False
    force_mood = None
    if not image_match:
        _IMAGE_KEYWORDS = [
            "photo", "selfie", "picture", "show me", "send me", "snap",
            "from far", "close up", "another angle", "full body",
        ]
        lower_user_text = user_text.lower()
        for kw in _IMAGE_KEYWORDS:
            needle = kw.lower()
            if needle in lower_user_text or kw in user_text:
                force_image = True
                logger.info("keyword forced image trigger: '%s' (user %s)", kw, user_id)
                break

    # 4) Per-character special-mood trigger — when a mood_trigger keyword matches, force an image + override the expression
    if not image_match and not force_image:
        img_config = _load_image_config(char_id)
        mood_triggers = img_config.get("mood_triggers", {})
        for mood, keywords in mood_triggers.items():
            for kw in keywords:
                if kw in user_text:
                    force_image = True
                    force_mood = mood
                    logger.info("character special trigger: mood=%s, keyword='%s' (user %s, %s)", mood, kw, user_id, char_id)
                    break
            if force_mood:
                break

    # 5) Stats-based mood fallback — when no keyword trigger fired, use the stat-mood
    if not force_mood and char_id:
        try:
            if _cached_stats["mood"] not in ("neutral", ""):
                force_mood = _cached_stats["mood"]
                logger.info("stat mood fallback: mood=%s (user %s, %s)", force_mood, user_id, char_id)
        except Exception as e:
            logger.error("stat mood fallback failed: %s", e)

    # Strip [...] brackets + unclosed [ + bracketless signals — drop everything
    clean_reply = re.sub(r"\[[^\[\]]*?\]", "", reply)
    clean_reply = re.sub(r"\[.*$", "", clean_reply, flags=re.DOTALL)
    clean_reply = re.sub(r"(?:SEND_IMAGE|photo sent):\s*.+?$", "", clean_reply, flags=re.IGNORECASE | re.MULTILINE)
    # Drop the (IMAGE_SENT: ...) pattern that may have been parroted from history
    clean_reply = re.sub(r"\(IMAGE_SENT:\s*.+?\)", "", clean_reply, flags=re.IGNORECASE)
    # Drop [MOOD:...] tags
    clean_reply = re.sub(r"\[MOOD:\w+\]", "", clean_reply)
    # Drop [OUTFIT:...] tags
    clean_reply = re.sub(r"\[OUTFIT:\s*.+?\]", "", clean_reply, flags=re.IGNORECASE)
    # Drop [STAT:...] tags (including location)
    clean_reply = re.sub(r"\[STAT:\s*[^\]]*\]", "", clean_reply)
    # Drop [LOCATION:...] tags (in case it ever shows up separately)
    clean_reply = re.sub(r"\[LOCATION:\s*[^\]]*\]", "", clean_reply, flags=re.IGNORECASE)
    # Drop [SEARCH:...] tags
    clean_reply = re.sub(r"\[SEARCH:\s*[^\]]*\]", "", clean_reply)
    clean_reply = clean_reply.strip()

    # 📷 capture button — only show when fixation > 50 AND no image is being sent
    capture_keyboard = None
    if not image_match and not force_image:
        try:
            if _cached_stats["fixation"] > 50:
                capture_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📷 Capture", callback_data="capture_scene")]
                ])
        except Exception:
            pass

    if clean_reply:
        # Keep stage directions (parens) as-is; bold the dialogue (HTML)
        def _format_dialogue_bold(text: str) -> str:
            """Wrap dialogue (text outside parens) in <b>; leave action descriptions inside parens unchanged."""
            parts = re.split(r'(\([^)]*\))', text)
            result = []
            for part in parts:
                if part.startswith('(') and part.endswith(')'):
                    result.append(part)
                else:
                    stripped = part.strip()
                    if stripped:
                        result.append(f"<b>{stripped}</b>")
                    elif part:
                        result.append(part)
            return ' '.join(result)

        formatted_reply = _format_dialogue_bold(clean_reply)
        try:
            await update.message.reply_text(formatted_reply, parse_mode="HTML", reply_markup=capture_keyboard)
        except Exception:
            # Fallback to plain text if HTML parsing fails
            await update.message.reply_text(clean_reply, reply_markup=capture_keyboard)

    # Save to history (full text including stage directions — the split is just for display)
    save_message(user_id, "user", user_text, character_id=char_id)
    save_message(user_id, "assistant", clean_reply if clean_reply else reply, character_id=char_id)
    # Turn count (one user message = one turn). total_turns is already incremented on receipt.
    increment_usage(user_id, "turns")  # monthly stats (Admin /stats)

    # Detect outfit changes — parse the LLM's [OUTFIT: ...] signal
    # Must run before image generation so the current image reflects the change
    # Only full outfit changes (full-set names) are allowed -> Grok tag conversion
    outfit_raw = _parse_outfit_signal(reply)
    current_outfit_override = None
    if outfit_raw:
        # Sanity check — log when the LLM invents tags not in the character default
        try:
            _default_clothing = _load_image_config(char_id).get("clothing", "").lower()
            _default_underwear = _load_image_config(char_id).get("underwear", "").lower()
            _emitted = [t.lower() for t in _split_tags(outfit_raw)]
            _novel = [t for t in _emitted if t not in _default_clothing and t not in _default_underwear]
            if _novel:
                logger.warning(
                    "outfit full-change novel tags (user %s, %s): %s — not in default wardrobe",
                    user_id, char_id, _novel,
                )
        except Exception:
            pass

        converted = await _convert_outfit_tags(outfit_raw)
        if converted:
            set_outfit(user_id, char_id, converted["clothing"], converted.get("underwear", ""), source="custom")
            current_outfit_override = converted
            logger.info("outfit change saved (user %s, %s): %s", user_id, char_id, converted["clothing"])
        else:
            # Grok conversion failed — store the raw value as-is
            set_outfit(user_id, char_id, outfit_raw, "", source="custom")
            current_outfit_override = {"clothing": outfit_raw, "underwear": ""}
            logger.info("outfit change saved (raw, user %s, %s): %s", user_id, char_id, outfit_raw)

    # Block non-character image requests
    if (image_match or force_image) and is_non_character_image_request(user_text):
        logger.info("non-character image request blocked (user %s): %s", user_id, user_text[:80])
        image_match = None
        force_image = False

    # Image signal or keyword-forced trigger
    if image_match or force_image:
        # Stat-based distance gate — skip image generation when fixation < 20
        try:
            _img_stats = _cached_stats
            if _img_stats["fixation"] < 20:
                logger.info("distance state — image generation skipped (fixation=%d, user %s, %s)",
                            _img_stats["fixation"], user_id, char_id)
                image_match = None
                force_image = False
        except Exception as e:
            logger.error("image stat check failed: %s", e)

    if image_match or force_image:
        # Queue check first — reject before calling the Grok API
        queue_status = await check_queue()
        from src.comfyui import COMFYUI_MAX_QUEUE
        total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
        if total_queued >= COMFYUI_MAX_QUEUE:
            await update.message.reply_text("(Lots of image requests right now... try me again in a bit!)")
        else:
            image_description = image_match.group(2) if image_match else user_text
            # When a special mood is set, append a mood/expression hint to the image description
            if force_mood:
                image_description = f"{image_description} [mood:{force_mood}]"

            anchor_image = character.get("anchor_image", "")

            # Send upload-photo indicator while generating
            async def keep_uploading():
                while True:
                    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                    await asyncio.sleep(3)

            upload_task = asyncio.create_task(keep_uploading())
            try:
                recent_history = get_history(user_id, limit=6, character_id=char_id)
                # Append current-location info (chat context is delivered separately via chat_history, so no duplication)
                _cur_location = _cached_stats.get("location", "")
                loc_hint = f" Current location: {_cur_location}." if _cur_location else ""
                combined_desc = f"{loc_hint} Image instruction: {image_description}"
                outfit = current_outfit_override or get_outfit(user_id, char_id)
                # P10 Phase 2 — inject location_context background tags (cache-hit only)
                _loc_bg = ""
                if _cur_location:
                    try:
                        from src.history import get_location_context as _glc
                        _loc_ctx = _glc(_normalize_location_key(_cur_location))
                        if _loc_ctx:
                            _loc_bg = _loc_ctx.get("danbooru_background", "") or ""
                    except Exception:
                        _loc_bg = ""
                tags = await generate_danbooru_tags(
                    recent_history, combined_desc, character=character, char_id=char_id,
                    outfit_override=outfit,
                    location_background=_loc_bg,
                )
                logger.info("Grok tags (user %s): pos=%s | neg=%s | orient=%s | skip_face=%s",
                            user_id, tags["pos_prompt"], tags["neg_prompt"],
                            tags.get("orientation"), tags.get("skip_face"))
                orientation = tags.get("orientation", "portrait")
                skip_face = tags.get("skip_face", False)
                image_path = await generate_image(
                    tags["pos_prompt"], tags["neg_prompt"], anchor_image, orientation, skip_face,
                )

                if image_path == "TIMEOUT":
                    await update.message.reply_text("(Image generation is taking too long... please try again later!)")
                    # Detailed Admin notification
                    username = update.effective_user.username or update.effective_user.first_name or "unknown"
                    char_name = character.get("name", char_id)
                    try:
                        await notify_image_timeout(context.bot, user_id, username, char_id, char_name)
                    except Exception as e:
                        logger.error("image timeout Admin notify failed: %s", e)
                elif image_path:
                    # Show 🎬 video generation button (image file is owned by the video context, auto-deleted after TTL)
                    video_ctx_id = _store_video_context(
                        user_id, char_id, image_path, image_description,
                        danbooru_tags=tags["pos_prompt"],
                    )
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{video_ctx_id}")
                    ]])
                    with open(image_path, "rb") as photo_file:
                        await update.message.reply_photo(photo=photo_file, reply_markup=keyboard)
                    save_message(user_id, "assistant", f"(IMAGE_SENT: {image_description})", character_id=char_id)
                    increment_usage(user_id, "images")
                    increment_daily_images(user_id)
                    logger.info("user %s auto image generation done", user_id)
            finally:
                upload_task.cancel()

    # Summary trigger — when message count exceeds threshold, run summary asynchronously
    summary_threshold = int(os.getenv("SUMMARY_THRESHOLD", "20"))
    recent_keep = int(os.getenv("RECENT_MESSAGES_KEEP", "10"))
    msg_count = get_message_count(user_id, char_id)
    if msg_count > summary_threshold:
        asyncio.create_task(_run_summary(user_id, char_id, recent_keep))


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/image command handler — generate an image using current chat context. (Admin only)"""
    # Admin check
    admin_ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    if str(update.effective_user.id) not in admin_ids:
        await update.message.reply_text("This command is admin-only.")
        return

    custom_command = " ".join(context.args) if context.args else ""
    user_id = update.effective_user.id
    char_id, character = _get_character(context, user_id)
    anchor_image = character.get("anchor_image", "")

    recent_history = get_history(user_id, limit=6, character_id=char_id)

    async def keep_typing():
        """Send an upload_photo indicator every 3 seconds while the image is being generated."""
        while True:
            await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    outfit = get_outfit(user_id, char_id)
    # P10 Phase 2 — inject location_context background tags (cache-hit only)
    _img_loc_bg = ""
    try:
        _img_stats = get_character_stats(user_id, char_id)
        _img_loc = _normalize_location_key(_img_stats.get("location") or "")
        if _img_loc:
            from src.history import get_location_context as _glc2
            _img_ctx = _glc2(_img_loc)
            if _img_ctx:
                _img_loc_bg = _img_ctx.get("danbooru_background", "") or ""
    except Exception:
        _img_loc_bg = ""
    typing_task = asyncio.create_task(keep_typing())
    try:
        tags = await generate_danbooru_tags(
            recent_history, custom_command, character=character, char_id=char_id,
            outfit_override=outfit,
            location_background=_img_loc_bg,
        )
        logger.info("Grok tags (user %s /image): pos=%s | neg=%s | orient=%s | skip_face=%s",
                    user_id, tags["pos_prompt"][:150], tags["neg_prompt"][:80],
                    tags.get("orientation"), tags.get("skip_face"))
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"], anchor_image, orientation, skip_face,
        )

        if image_path:
            desc = custom_command if custom_command else "photo"
            # Admin always sees the video button
            video_ctx_id = _store_video_context(
                user_id, char_id, image_path, desc,
                danbooru_tags=tags["pos_prompt"],
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{video_ctx_id}")
            ]])
            with open(image_path, "rb") as photo_file:
                await update.message.reply_photo(photo=photo_file, reply_markup=keyboard)
            save_message(user_id, "assistant", f"(IMAGE_SENT: {desc})", character_id=char_id)
            logger.info("user %s image generation done: %s", user_id, tags["pos_prompt"][:80])
        else:
            await update.message.reply_text("Image generation failed... please try again!")
    finally:
        typing_task.cancel()


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset command — wipe this character bot's chat history."""
    user_id = update.effective_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)

    clear_history(user_id, character_id=char_id)
    await update.message.reply_text(f"[{char_name}] Chat history has been reset.")
    logger.info("user %s character %s history cleared", user_id, char_id)


async def _unsupported_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Non-text messages (photos, files, stickers, etc.) — send a notice that auto-deletes."""
    msg = await update.message.reply_text("Text messages only!")
    # Delete the notice 5 seconds later (avoid chat clutter)
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except Exception:
        pass


# Outfit-change detection keywords

async def outfit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/outfit command — view / reset the current outfit."""
    user_id = update.effective_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)

    args = context.args

    # /outfit reset — back to preset
    if args and args[0].lower() == "reset":
        reset_outfit(user_id, char_id)
        img_config = _load_image_config(char_id)
        default_clothing = img_config.get("clothing", "default")
        await update.message.reply_text(f"({char_name}'s outfit reset to default: {default_clothing})")
        return

    # /outfit — show current outfit + preset list
    outfit = get_outfit(user_id, char_id)
    img_config = _load_image_config(char_id)

    if outfit and outfit["source"] == "custom":
        current = outfit["clothing"]
        current_underwear = outfit.get("underwear", "") or ""
        source_text = "custom"
    else:
        current = img_config.get("clothing", "(none)")
        current_underwear = ""
        source_text = "default"

    text = f"👗 {char_name}'s current outfit\n\n"
    text += f"Outfit: {current}\n"
    if current_underwear:
        text += f"Underwear: {current_underwear}\n"
    text += f"Source: {source_text}\n\n"

    # Preset list (shown when an outfits array is configured)
    outfits = img_config.get("outfits", [])
    if outfits:
        text += "Presets:\n"
        keyboard = []
        for i, o in enumerate(outfits):
            text += f"  {i+1}. {o['name']}\n"
            keyboard.append([InlineKeyboardButton(o["name"], callback_data=f"outfit_{i}")])
        keyboard.append([InlineKeyboardButton("🔄 Reset to default", callback_data="outfit_reset")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        text += "/outfit reset — restore the default outfit"
        await update.message.reply_text(text)


async def outfit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Outfit preset selection callback."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    char_id = context.bot_data["char_id"]
    character = context.bot_data["character"]
    char_name = character.get("name", char_id)
    img_config = _load_image_config(char_id)
    outfits = img_config.get("outfits", [])

    if query.data == "outfit_reset":
        reset_outfit(user_id, char_id)
        default_clothing = img_config.get("clothing", "default")
        await query.edit_message_text(f"({char_name}'s outfit reset to default: {default_clothing})")
        return

    # outfit_0, outfit_1, etc.
    try:
        idx = int(query.data.split("_")[1])
        selected = outfits[idx]
    except (IndexError, ValueError):
        await query.edit_message_text("Invalid selection.")
        return

    set_outfit(user_id, char_id, selected["clothing"], selected.get("underwear", ""), source="custom")
    await query.edit_message_text(f"({char_name}'s outfit changed: {selected['name']})")
    logger.info("user %s outfit change: %s -> %s", user_id, char_id, selected["name"])


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — view character stats (Admin only)."""
    if not check_admin(update.effective_user.id):
        return

    char_id = context.bot_data.get("char_id", "")
    char_name = context.bot_data.get("character", {}).get("name", char_id)
    args = context.args or []

    # /stats <user_id> -> view a specific user (Admin)
    target_user = int(args[0]) if args else update.effective_user.id

    stats = get_character_stats(target_user, char_id)
    text = (
        f"📊 Character stats ({char_name})\n"
        f"User: {target_user}\n\n"
        f"fixation: {stats['fixation']}/100\n"
        f"mood: {stats['mood']}\n"
        f"location: {stats.get('location') or '(none)'}\n"
        f"total_turns: {stats.get('total_turns', 0)}"
    )
    await update.message.reply_text(text)


async def setstat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setstat — set a character stat directly (Admin only).
    Usage: /setstat fixation 50, /setstat mood worship, /setstat total_turns 8
    """
    if not check_admin(update.effective_user.id):
        return

    user_id = update.effective_user.id
    char_id = context.bot_data.get("char_id", "")
    if not char_id:
        await update.message.reply_text("This command only works inside a character bot.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("Usage: /setstat <key> <value>\nExample: /setstat fixation 50")
        return

    key = args[0].lower()
    value = args[1]

    cache_key = (user_id, char_id)
    stats = get_character_stats(user_id, char_id)
    cached = _stats_cache.get(cache_key, {})

    if key == "fixation":
        cached["fixation"] = max(0, min(100, int(value)))
    elif key == "mood":
        cached["mood"] = value
    elif key == "total_turns":
        cached["_total_turns"] = int(value)
    elif key == "location":
        cached["location"] = value
    else:
        await update.message.reply_text(f"Unknown key: {key}\nAllowed: fixation, mood, total_turns, location")
        return

    cached["_dirty"] = True
    _stats_cache[cache_key] = cached
    _schedule_flush(user_id, char_id)

    await update.message.reply_text(f"✅ {char_id} {key} = {value}")


async def capture_scene_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📷 capture button callback — capture the current scene as an image."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    char_id = context.bot_data.get("char_id", "")
    character = context.bot_data.get("character", {})
    char_name = character.get("name", char_id)

    # Remove the button + show progress
    await query.edit_message_reply_markup(reply_markup=None)

    # Load recent chat history (limit=6, same as auto-image)
    recent_history = get_history(user_id, limit=6, character_id=char_id)

    if not recent_history:
        return

    # Generate tags via Grok
    try:
        chat_id = query.message.chat_id

        async def keep_uploading_capture():
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(3)

        upload_task = asyncio.create_task(keep_uploading_capture())

        image_config = _load_image_config(char_id)
        current_stats = get_character_stats(user_id, char_id)
        force_mood = current_stats["mood"] if current_stats["mood"] not in ("neutral", "") else None

        _cur_location = current_stats.get("location", "")
        loc_hint = f" Current location: {_cur_location}." if _cur_location else ""
        # Scene hint — passed in via custom_command (same pattern as auto-image)
        scene_desc = f"Capture the current scene.{loc_hint}"
        if force_mood:
            scene_desc += f" [mood:{force_mood}]"

        outfit = get_outfit(user_id, char_id)
        # P10 Phase 2 — inject location_context background tags (cache-hit only)
        _cap_loc_bg = ""
        if _cur_location:
            try:
                from src.history import get_location_context as _glc3
                _cap_ctx = _glc3(_normalize_location_key(_cur_location))
                if _cap_ctx:
                    _cap_loc_bg = _cap_ctx.get("danbooru_background", "") or ""
            except Exception:
                _cap_loc_bg = ""
        # Pass the actual history list directly to Grok (same as auto-image)
        tags = await generate_danbooru_tags(
            recent_history,
            scene_desc,
            character=character,
            char_id=char_id,
            outfit_override=outfit,
            location_background=_cap_loc_bg,
        )

        if not tags or tags.get("pos_prompt") == "BLOCKED":
            upload_task.cancel()
            return

        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        anchor = character.get("anchor_image", "")

        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            anchor, orientation, skip_face,
        )

        upload_task.cancel()

        if image_path and image_path not in ("QUEUE_FULL", "TIMEOUT"):
            video_ctx_id = _store_video_context(
                user_id, char_id, image_path, scene_desc,
                danbooru_tags=tags["pos_prompt"],
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{video_ctx_id}")
            ]])
            with open(image_path, "rb") as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, reply_markup=keyboard)
            increment_usage(user_id, "images")
            increment_daily_images(user_id)
        elif image_path == "TIMEOUT":
            await notify_image_timeout(context.bot, user_id, char_name)
    except Exception as e:
        upload_task.cancel()
        logger.error("📷 capture failed: %s", e)


async def video_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎬 video generation button callback handler."""
    query = update.callback_query
    await query.answer()

    data = query.data  # "video:{ctx_id}"
    if not data or not data.startswith("video:"):
        return

    ctx_id = data.split(":", 1)[1]
    ctx = _get_video_context(ctx_id)
    if not ctx:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⏰ Video generation has timed out.")
        return

    user_id = ctx["user_id"]
    char_id = ctx["char_id"]

    # Replace the button with "Generating..."
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("⏳ Generating video...", callback_data="noop")
    ]]))

    # upload_video typing indicator (repeats every 3s)
    chat_id = query.message.chat_id
    async def keep_uploading_video():
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
            except Exception:
                pass
            await asyncio.sleep(3)

    upload_task = asyncio.create_task(keep_uploading_video())

    video_path = None
    prompts_blocked = False
    try:
        # Generate Grok video prompts (image Vision + chat history + i2v guide)
        from src.grok import generate_video_prompts
        recent_history = get_history(user_id, limit=6, character_id=char_id)
        stats = get_character_stats(user_id, char_id)
        try:
            prompts = await generate_video_prompts(
                ctx["description"],
                image_path=ctx["image_path"],
                chat_history=recent_history,
                danbooru_tags=ctx.get("danbooru_tags", ""),
                mood=stats.get("mood", "neutral"),
            )
        except Exception as e:
            logger.error("Grok video prompt failed: %s", e)
            prompts = {"motion_prompt": ctx["description"], "audio_prompt": "soft moan, heavy breathing, intimate silence"}

        # video-improve2 (P15) — Admin debug dump (VIDEO_DEBUG_DUMP=1)
        if prompts.get("_debug_analyzer_json") and check_admin(user_id):
            import json as _json
            dump = (
                "🔍 VIDEO DEBUG\n\n"
                f"Analyzer:\n```\n{_json.dumps(prompts['_debug_analyzer_json'], ensure_ascii=False, indent=2)}\n```\n\n"
                f"Preset ({prompts.get('_debug_pose_key_resolved')}):\n"
                f"```\n{_json.dumps(prompts.get('_debug_preset'), ensure_ascii=False, indent=2)}\n```\n\n"
                f"Motion:\n{(prompts.get('motion_prompt') or '')[:500]}"
            )
            try:
                await context.bot.send_message(chat_id=user_id, text=dump, parse_mode="Markdown")
            except Exception:
                try:
                    await context.bot.send_message(chat_id=user_id, text=dump[:4000])
                except Exception as _e:
                    logger.warning("VIDEO_DEBUG_DUMP send failed (char): %s", _e)

        # Phase 2-B — log Step 2 tag-augment fallback success (for monitoring)
        if prompts.get("_csam_fallback_used"):
            logger.info("Grok Step 2 fallback succeeded: user=%s char=%s", user_id, char_id)

        # Phase 2-B — emit error when both passes are BLOCKED
        if prompts.get("motion_prompt") == "BLOCKED" or prompts.get("_csam_blocked"):
            prompts_blocked = True
            logger.warning("Grok video finally blocked: user=%s char=%s", user_id, char_id)
        else:
            # Admin notify — video generation started (with prompts info)
            try:
                await notify_admins_video(
                    context,
                    triggering_user_id=user_id,
                    source="char_bot",
                    char_id=char_id,
                    status="started",
                    pose_key=prompts.get("_debug_pose_key_resolved", ""),
                    safety_level=prompts.get("_debug_safety_level", ""),
                    motion_prompt=prompts.get("motion_prompt", ""),
                    audio_prompt=prompts.get("audio_prompt", ""),
                )
            except Exception as _e:
                logger.warning("admin video notify (started) failed: %s", _e)

            # AtlasCloud video generation (audio handled automatically)
            from src.video import generate_video
            video_path = await generate_video(
                image_path=ctx["image_path"],
                motion_prompt=prompts["motion_prompt"],
                audio_prompt=prompts.get("audio_prompt", ""),
                lora_config=prompts.get("lora_config"),
            )
    finally:
        upload_task.cancel()

    if prompts_blocked:
        # When Grok blocks twice — show a single error to the user (count only bumps on success, so unchanged)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{ctx_id}")
            ]]))
        except Exception:
            pass
        await query.message.reply_text("😢 Video generation was blocked. Please try again.")
        logger.warning("user %s video blocked by Grok (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="blocked",
                                      extra="Grok motion BLOCKED (CSAM filter)")
        except Exception:
            pass
        return

    if video_path:
        # Success: remove the button + send the video
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        with open(video_path, "rb") as f:
            await query.message.reply_video(video=f)
        increment_usage(user_id, "videos")
        increment_daily_videos(user_id)
        _cleanup_video_context(ctx_id)
        try:
            os.unlink(video_path)
        except OSError:
            pass
        logger.info("user %s video generation done (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="success",
                                      pose_key=prompts.get("_debug_pose_key_resolved", ""))
        except Exception:
            pass
    else:
        # Failure: restore the button (retryable)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{ctx_id}")
            ]]))
        except Exception:
            pass
        await query.message.reply_text("😢 Video generation failed. Please try again.")
        logger.error("user %s video generation failed (char=%s)", user_id, char_id)
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="char_bot",
                                      char_id=char_id, status="failed",
                                      extra="AtlasCloud video generation failed — check logs")
        except Exception:
            pass


def register_char_handlers(app):
    """Register handlers on a character bot Application."""
    app.add_handler(CommandHandler("start", char_start))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("image", handle_image))
    app.add_handler(CommandHandler("outfit", outfit_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("setstat", setstat_command))
    app.add_handler(CallbackQueryHandler(outfit_callback, pattern=r"^outfit_"))
    app.add_handler(CallbackQueryHandler(capture_scene_callback, pattern=r"^capture_scene$"))
    app.add_handler(CallbackQueryHandler(video_callback_handler, pattern=r"^video:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Non-text messages (photos, files, stickers, etc.) — notify and delete
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, _unsupported_message))
