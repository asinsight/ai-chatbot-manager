"""Image generator bot handlers — every message is an image generation request.

No character chat: a free-form English description -> Grok tags -> ComfyUI image.
Direct Danbooru tag input is also supported.
"""

import asyncio
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.handlers_common import check_admin, notify_admins_video
from src.history import (
    is_onboarded, increment_usage,
    increment_daily_images, increment_daily_videos,
    is_valid_saved_char_name, save_character, list_saved_characters,
    get_saved_character_by_name, get_saved_character_by_slot,
    delete_saved_character, find_available_slot, SAVED_CHAR_MAX_SLOTS,
)
from src.grok import (
    generate_danbooru_tags,
    generate_danbooru_tags_random,
    classify_tags_to_nested_blocks,
    analyze_partial_edit_intent,
)
import src.comfyui
from src.comfyui import generate_image, check_queue, COMFYUI_MAX_QUEUE
from src.input_filter import filter_input
from src.intent_router import analyze_input_intent
from src.rate_limiter import rate_limiter
from src.trait_pools import roll_character, roll_sfw_scene
from src.video_context import (
    store_video_context,
    get_video_context,
    cleanup_video_context,
)

logger = logging.getLogger(__name__)

MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "")

# Available checkpoints
AVAILABLE_MODELS = {
    "1": {"name": "OneObsession v2.0", "path": "illustrious/oneObsession_v20Bold.safetensors"},
    "2": {"name": "JANKU Chenkin Noobai v7.77", "path": "illustrious/JANKUTrainedChenkinNoobai_v777.safetensors"},
}
DEFAULT_MODEL_KEY = "1"

_HELP_TEXT = (
    "🎨 Image Generator\n\n"
    "⚠️ Every character generated here is 20 years or older.\n\n"
    "Send a description of the image you want to create.\n\n"
    "💡 Examples:\n"
    "• Yerin drinking coffee at a cafe\n"
    "• Sua at the beach in a bikini\n"
    "• A woman reading at a library\n"
    "• Now with a smiling expression  ← edits the previous image\n"
    "• Same composition, just change the outfit  seed:12345\n\n"
    "📌 Features:\n"
    "• Mention a character name -> their look is applied automatically\n"
    "• Direct Danbooru tag input supported\n"
    "• Edits based on the previous image (automatic)\n"
    "• Pin a seed to keep the same composition\n"
    "• 🎲 /random — fully random SFW image\n"
    "• 💾 Save character — save after generation via the button (up to 3)\n\n"
    "💾 Save / recall a character:\n"
    "• After generating, tap 💾 Save character -> enter a name (letters/digits/underscore, 1-20 chars)\n"
    "• Recall via `@name` -> generates a new image with that look\n"
    "  e.g. `@minkyung beach bikini`\n"
    "  e.g. `@yerin_dress cafe coffee`\n\n"
    "🔧 Commands:\n"
    "/help — show this help\n"
    "/reset — reset the session (HQ / model preferences are kept)\n"
    "/seed — show the last used seed\n"
    "/model — change the model (initial generation may take longer)\n"
    "/hq on|off — toggle high-quality mode\n"
    "/random — 🎲 generate a random SFW image\n"
    "/chars — saved characters (with 🗑️ delete buttons)\n"
    "/cancel — cancel the current saving flow"
)

_VIDEO_CAPTION = (
    "🎬 Tap to generate an auto-motion video"
)

# Random-button inline keyboard (single 🎲 SFW button)
_RANDOM_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🎲 Random SFW", callback_data="random:sfw"),
]])

# Display name -> char_id mapping for fast-path matching from free-text input.
# Sample fork ships only char05; expand here when adding more characters.
CHAR_NAME_MAP = {
    "Jiwon": "char05", "jiwon": "char05",
    "Jiwon Han": "char05", "Han Jiwon": "char05",
}


def _match_character(text: str, characters: dict) -> tuple[str, dict | None]:
    """Detect a character name in the text and return (char_id, character dict)."""
    for name, char_id in CHAR_NAME_MAP.items():
        if name in text and char_id in characters:
            return char_id, characters[char_id]
    return "", None


def _is_danbooru_tags(text: str) -> bool:
    """Return True if the input looks like Danbooru tags (comma-separated)."""
    return "," in text


_HQ_WORKFLOW = os.getenv(
    "COMFYUI_WORKFLOW_HQ",
    "comfyui_workflow/main_character_build_highqual.json",
)

# Imagegen fixed positive prefix — prepended to every render (custom text + /random).
# Pushes the model toward Korean + VN style for consistency.
IMAGEGEN_FIXED_PREFIX = "1girl, solo, beautiful korean woman, visual novel style"


def _extract_seed(text: str) -> tuple[str, int]:
    """Extract a `seed:12345` pattern from the text. Returns (text-without-seed, seed). Defaults to seed=0."""
    match = re.search(r"seed[:\s]*(\d+)", text, re.IGNORECASE)
    if match:
        seed = int(match.group(1))
        cleaned = text[:match.start()].strip() + " " + text[match.end():].strip()
        return cleaned.strip(), seed
    return text, 0


# @name reference regex — an `@` immediately following an identifier char (alnum/_/.) is excluded
# (defends against false positives in email addresses).
# e.g. email@domain.com -> "domain" does NOT match. "(@minkyung)" or " @minkyung" DOES match.
_AT_NAME_RE = re.compile(r"(?<![a-zA-Z0-9_.])@([a-zA-Z0-9_]{1,20})\b")


def _resolve_saved_char_ref(
    text: str, user_id: int
) -> tuple[dict | None, str, str | None, str | None]:
    """Extract an @name reference from the text and look up the saved character.

    Returns:
        (saved_char | None, remaining_text, error_kind | None, attempted_name | None)
        - 0 matches: (None, text, None, None) — normal handling
        - 2+ matches: (None, text, "multiple", None) — handler should reply with a refusal
        - 1 match + DB hit: (char_dict, stripped_text, None, name) — identity_override applies
        - 1 match + DB miss: (None, text, "not_found", name) — handler should show a hint + listing

    Principles:
        - Only the first match is recognized (policy: refuse two simultaneous character calls)
        - DB miss surfaces an explicit message (typo discovery + saved-character listing)
        - Pure function — no side effects beyond the DB lookup
    """
    matches = _AT_NAME_RE.findall(text)
    if not matches:
        return None, text, None, None
    if len(matches) >= 2:
        return None, text, "multiple", None

    name = matches[0]
    char = get_saved_character_by_name(user_id, name)
    if not char:
        # DB miss — handler will show the saved-character list along with the hint
        return None, text, "not_found", name

    # Strip the @name token — only the first match is removed
    full_match = _AT_NAME_RE.search(text)
    if full_match:
        stripped = text[: full_match.start()] + text[full_match.end():]
        # Trim surrounding whitespace + collapse runs of whitespace
        stripped = re.sub(r"\s+", " ", stripped).strip()
    else:
        stripped = text
    return char, stripped, None, name


def _format_saved_chars_list(user_id: int) -> str:
    """Format the saved-character listing as a Markdown string.

    Returns:
        Formatted string. If no saved characters exist, an empty-state hint is returned.
    """
    chars = list_saved_characters(user_id)
    if not chars:
        return "_(No saved characters yet. After generating an image, tap 💾 Save character to save it.)_"
    lines = [f"💾 Saved characters ({len(chars)}/{SAVED_CHAR_MAX_SLOTS}):"]
    for c in chars:
        appearance = c.get('appearance_tags', '') or ''
        suffix = '...' if len(appearance) > 60 else ''
        lines.append(f"  Slot {c['slot']}: `{c['name']}` — {appearance[:60]}{suffix}")
    lines.append("")
    lines.append("Recall: include `@name` in your image request (e.g. `@minkyung beach bikini`)")
    return "\n".join(lines)


def _clear_session(user_data: dict) -> None:
    """Clear session state — but preserve persistent preferences like hq_mode / selected_model."""
    # Clean up the previous image ctx (delete file + remove context)
    old_ctx = user_data.get("last_video_ctx_id")
    if old_ctx:
        cleanup_video_context(old_ctx)
    # Image file owned only by the session (not registered in ctx)
    old_path = user_data.get("last_image_path")
    if old_path and os.path.exists(old_path):
        try:
            os.unlink(old_path)
        except OSError:
            pass
    for k in (
        "last_tags", "last_char_id", "last_character", "last_seed",
        "last_image_path", "last_korean_description", "last_random_mode",
        "last_video_ctx_id", "last_danbooru_tags",
    ):
        user_data.pop(k, None)


async def imagegen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — image generator intro."""
    # Reset the session (hq_mode / selected_model are preserved)
    _clear_session(context.user_data)
    await update.message.reply_text(_HELP_TEXT, reply_markup=_RANDOM_KEYBOARD)


async def imagegen_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — show help."""
    await update.message.reply_text(_HELP_TEXT, reply_markup=_RANDOM_KEYBOARD)


async def imagegen_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset — reset the session (persistent prefs like hq_mode / selected_model are kept)."""
    _clear_session(context.user_data)
    await update.message.reply_text("🔄 Session reset. Send a new image description!")


async def imagegen_hq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hq on|off|status — toggle high-quality mode."""
    user_id = update.effective_user.id
    args = [a.lower() for a in (context.args or [])]

    if not args or args[0] == "status":
        state = "ON" if context.user_data.get("hq_mode", False) else "OFF"
        await update.message.reply_text(f"Current HQ: {state}\n\nUsage: /hq on | /hq off")
        return

    if args[0] == "on":
        context.user_data["hq_mode"] = True
        await update.message.reply_text("✅ HQ mode ON — subsequent renders use the high-quality workflow.")
        logger.info("imagegen HQ ON: user=%s", user_id)
        return

    if args[0] == "off":
        context.user_data["hq_mode"] = False
        await update.message.reply_text("✅ HQ OFF")
        logger.info("imagegen HQ OFF: user=%s", user_id)
        return

    await update.message.reply_text("Usage: /hq on | /hq off | /hq status")


async def _send_image_with_video_option(
    *,
    target_message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    image_path: str,
    description: str,
    danbooru_tags: str,
    extra_caption: str = "",
    scene_key: str | None = None,
) -> None:
    """Send the image + attach the 🎬 video generation button.

    File deletion is delegated to the video_context TTL cleanup. Session keys updated:
    last_image_path / last_korean_description / last_danbooru_tags / last_video_ctx_id.
    """
    # Clean up the previous ctx
    old_ctx = context.user_data.get("last_video_ctx_id")
    if old_ctx:
        cleanup_video_context(old_ctx)
    old_path = context.user_data.get("last_image_path")
    if old_path and old_path != image_path and os.path.exists(old_path):
        try:
            os.unlink(old_path)
        except OSError:
            pass

    ctx_id = store_video_context(
        user_id=user_id,
        char_id="imagegen",
        image_path=image_path,
        description=description,
        danbooru_tags=danbooru_tags,
        scene_key=scene_key,
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{ctx_id}"),
        InlineKeyboardButton("💾 Save character", callback_data="savechar:init"),
    ]])
    caption = _VIDEO_CAPTION
    if extra_caption:
        caption = f"{extra_caption}\n{caption}"
    with open(image_path, "rb") as f:
        await target_message.reply_photo(photo=f, caption=caption, reply_markup=keyboard)
    context.user_data["last_video_ctx_id"] = ctx_id

    # Save into the session for follow-up edits (edits build on the previous image)
    context.user_data["last_image_path"] = image_path
    context.user_data["last_korean_description"] = description
    context.user_data["last_danbooru_tags"] = danbooru_tags


async def imagegen_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/random — show the random SFW image button."""
    await update.message.reply_text(
        "🎲 Generate a random SFW image.\nTap the button below:",
        reply_markup=_RANDOM_KEYBOARD,
    )


async def imagegen_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/seed — show the last used seed."""
    last_seed = context.user_data.get("last_seed", 0)
    if last_seed:
        await update.message.reply_text(f"🌱 Last seed: {last_seed}\n\nUsage: append `seed:{last_seed}` to your description")
    else:
        await update.message.reply_text("No images have been generated yet.")


async def imagegen_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/model [number] — change model or show the current model."""
    args = context.args or []
    current_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    current_model = AVAILABLE_MODELS[current_key]

    # Currently loaded ComfyUI checkpoint
    loaded = src.comfyui.current_loaded_checkpoint

    if not args:
        # Show the model list
        lines = []
        for key, m in AVAILABLE_MODELS.items():
            marker = " ✅" if key == current_key else ""
            loaded_marker = " (loaded)" if m["path"] == loaded else ""
            lines.append(f"  {key}. {m['name']}{marker}{loaded_marker}")
        text = (
            "🎛 Model selection:\n\n"
            + "\n".join(lines)
            + f"\n\nCurrent selection: {current_model['name']}"
        )
        if loaded and loaded != current_model["path"]:
            text += "\n⚠️ A different model is currently loaded — the first render will take longer to switch."
        text += "\n\nUsage: /model <number> (e.g. /model 2)"
        await update.message.reply_text(text)
        return

    choice = args[0]
    if choice not in AVAILABLE_MODELS:
        await update.message.reply_text(f"Pick a number between 1 and {len(AVAILABLE_MODELS)}.")
        return

    context.user_data["selected_model"] = choice
    selected = AVAILABLE_MODELS[choice]
    msg = f"✅ Model changed: {selected['name']}"
    if loaded and selected["path"] != loaded:
        msg += "\n⚠️ A different model is currently loaded — the first render will take an extra 10-30s."
    await update.message.reply_text(msg)
    logger.info("imagegen model change: user=%s model=%s", update.effective_user.id, selected["name"])


async def imagegen_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Every text message = an image generation request.

    Exception: when pending_save is set, the text is treated as the save name first.
    """
    user_id = update.effective_user.id
    description = update.message.text.strip()

    if not description:
        return

    # New turn — clear any identity_override leaked from the previous turn
    # (the save-name path does not use identity_override, so this is irrelevant there)
    context.user_data.pop("identity_override", None)

    # If pending_save is set, treat this text as the name
    if await _try_handle_save_name(update, context):
        return

    # Input filtering (prompt injection + inappropriate content)
    description, blocked, block_reason = await filter_input(description)
    if blocked:
        logger.warning("[security] imagegen input blocked: user=%s reason=%s", user_id, block_reason)
        await update.message.reply_text("_(Your message contains content that is not allowed.)_", parse_mode="Markdown")
        return

    # Extract seed (seed:12345 pattern)
    description, user_seed = _extract_seed(description)
    if not description:
        return

    # @name parser — recall a saved character (Phase 1-D)
    # Runs before the heavy path, but after security/seed parsing (security filter must pass first)
    saved_char, description, parse_err, attempted_name = _resolve_saved_char_ref(description, user_id)
    if parse_err == "multiple":
        await update.message.reply_text(
            "_(Calling two characters in one image is not supported. Use one character at a time.)_",
            parse_mode="Markdown",
        )
        return
    if parse_err == "not_found":
        # No matching saved character — show a hint + listing
        saved_list = _format_saved_chars_list(user_id)
        await update.message.reply_text(
            f"Saved character `{attempted_name}` was not found.\n\n{saved_list}",
            parse_mode="Markdown",
        )
        logger.info("@name DB miss: user=%s attempted_name=%s", user_id, attempted_name)
        return
    # Local LLM intent router — classify into RESET / EDIT_SAVED / RECALL / NEW / MODIFY / SCENE.
    # Replaces the previous 4-way heuristic (reset keyword set, edit-hint regex, last_tags-presence
    # branching, reset judgement helper) with a single classifier after the @name fast path.
    #
    # The router + dispatch + EDIT_SAVED analyzer take 1-6s in LLM calls — keep an UPLOAD_PHOTO
    # typing indicator running from router start through dispatch end so the user sees activity.
    async def _router_spinner():
        while True:
            try:
                await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            except Exception:
                pass
            await asyncio.sleep(3)

    router_spinner_task = asyncio.create_task(_router_spinner())
    try:
        last_tags_for_router = context.user_data.get("last_tags", "")
        intent_result = await analyze_input_intent(
            text=description,
            has_saved_char_ref=bool(saved_char),
            has_last_tags=bool(last_tags_for_router),
            user_id=user_id,
        )
        intent = intent_result["intent"]
        scene_description = intent_result["scene_description"]
        edit_clause = intent_result["edit_clause"]
        logger.info(
            "intent router: user=%s intent=%s scene=%r edit=%r saved_char=%s last_tags=%s",
            user_id, intent, scene_description[:40], edit_clause[:40],
            bool(saved_char), bool(last_tags_for_router),
        )

        # RESET — clear the session, then proceed with the leftover text as a NEW request (or hint and exit if leftover is empty)
        if intent == "RESET":
            for k in (
                "last_tags", "last_char_id", "last_character", "last_seed",
                "last_random_traits", "last_random_mode",
            ):
                context.user_data.pop(k, None)
            if not scene_description.strip():
                await update.message.reply_text("🔄 Session reset. Send a new image description!")
                return
            intent = "NEW"
            description = scene_description

        # RECALL — saved character identity_override + scene as-is
        elif intent == "RECALL" and saved_char:
            context.user_data["identity_override"] = saved_char
            description = scene_description or ""
            logger.info(
                "@name RECALL: user=%s name=%s slot=%s",
                user_id, saved_char["name"], saved_char["slot"],
            )

        # EDIT_SAVED — produce a surgical edit via the Grok analyzer + DB update + identity_override
        elif intent == "EDIT_SAVED" and saved_char:
            current_blocks = {
                "appearance_tags": saved_char.get("appearance_tags", "") or "",
                "clothing":        saved_char.get("clothing", "") or "",
                "underwear":       saved_char.get("underwear", "") or "",
                "body_shape":      saved_char.get("body_shape") or {},
                "breast":          saved_char.get("breast") or {},
            }
            analyzer_input = (edit_clause or description or "").strip()
            try:
                ed_intent = await analyze_partial_edit_intent(analyzer_input, current_blocks)
            except Exception as e:
                logger.error("analyze_partial_edit_intent failed: user=%s err=%s", user_id, e)
                ed_intent = {"edits": {}, "scene_description": ""}

            edits = ed_intent.get("edits") or {}
            if edits:
                # nested deep-merge: top-level flat keys are replaced; nested dicts are overlaid sub-key-wise
                merged = dict(current_blocks)
                for top_key in ("appearance_tags", "clothing", "underwear"):
                    if top_key in edits and isinstance(edits[top_key], str):
                        merged[top_key] = edits[top_key]
                for nested_key in ("body_shape", "breast"):
                    if nested_key in edits and isinstance(edits[nested_key], dict):
                        merged[nested_key] = {**(merged[nested_key] or {}), **edits[nested_key]}
                try:
                    save_character(
                        user_id=user_id,
                        slot=saved_char["slot"],
                        name=saved_char["name"],
                        appearance_tags=merged["appearance_tags"],
                        clothing=merged["clothing"],
                        underwear=merged["underwear"],
                        body_shape=merged["body_shape"],
                        breast=merged["breast"],
                    )
                    refreshed = get_saved_character_by_slot(user_id, saved_char["slot"])
                    if refreshed:
                        saved_char = refreshed
                    context.user_data["pending_edit_confirm"] = {
                        "name": saved_char["name"],
                        "fields": list(edits.keys()),
                    }
                    logger.info(
                        "@name partial edit: user=%s name=%s slot=%s fields=%s",
                        user_id, saved_char["name"], saved_char["slot"], list(edits.keys()),
                    )
                except Exception as e:
                    logger.error("save_character (partial edit) failed: user=%s err=%s", user_id, e)

            context.user_data["identity_override"] = saved_char
            # If the analyzer extracted a more accurate scene, use it; otherwise keep the router's scene_description
            analyzer_scene = (ed_intent.get("scene_description") or "").strip()
            description = analyzer_scene or scene_description or ""

        # NEW — clear last_tags then create a new character
        elif intent == "NEW":
            for k in (
                "last_tags", "last_char_id", "last_character", "last_seed",
                "last_random_traits", "last_random_mode",
            ):
                context.user_data.pop(k, None)
            description = scene_description or description

        # MODIFY — keep last_tags, proceed with scene_description (router only emits this when last_tags=true)
        elif intent == "MODIFY":
            description = scene_description or description

        # SCENE — simple scene without last_tags
        elif intent == "SCENE":
            description = scene_description or description
    finally:
        router_spinner_task.cancel()

    if parse_err is None and not saved_char and "@" in update.message.text:
        # An "@" was present but the lookbehind rejected it (e.g. inside an email)
        logger.debug("@name no match (lookbehind reject): user=%s text=%r", user_id, update.message.text[:80])

    # Note: a blank `description` is fine here as long as identity_override is set
    # (e.g. a bare "@minkyung" recall — Grok-free pose/scene generation against the saved character).
    # The "blank description AND no identity_override" case is already handled by the _extract_seed guard above.

    # HQ mode — read from the session toggle (/hq on|off)
    use_hq = bool(context.user_data.get("hq_mode", False))

    # Onboarding check
    if not is_onboarded(user_id):
        main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = "Please send /start in the main bot first to register."
        if main_link:
            text += f"\n👉 {main_link}"
        await update.message.reply_text(text)
        return

    # Rate limiting
    allowed, info = rate_limiter.check(user_id)
    if not allowed:
        await update.message.reply_text("_(You're going too fast. Please try again in a moment.)_", parse_mode="Markdown")
        return

    # ComfyUI queue check
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        await update.message.reply_text("_(Lots of image requests right now — can't generate at the moment. Please try again shortly.)_", parse_mode="Markdown")
        return

    # CHAR_NAME_MAP — when a character bot's name is detected, reset the session (separate feature)
    # RESET / NEW intent are already handled in the router — this only does char_id detection.
    characters = context.bot_data.get("characters", {})
    char_id, character = _match_character(description, characters)
    if char_id:
        for k in (
            "last_tags", "last_char_id", "last_character", "last_seed",
            "last_random_traits", "last_random_mode",
        ):
            context.user_data.pop(k, None)

    # Edit mode if a previous session exists
    last_tags = context.user_data.get("last_tags")

    # In edit mode, if the user did NOT specify an explicit seed, reuse last_seed automatically
    # (purpose: keep face / body shape consistent across different scenes of the same character)
    # When char_id was detected above, last_tags has already been cleared, so no auto-reuse.
    if user_seed == 0 and last_tags:
        _auto_seed = context.user_data.get("last_seed", 0) or 0
        if _auto_seed:
            user_seed = _auto_seed
            logger.info("imagegen edit mode — auto-reusing last_seed: user=%s seed=%s", user_id, user_seed)
    if not char_id:
        # No character match -> use the previous session's character
        char_id = context.user_data.get("last_char_id", "")
        character = context.user_data.get("last_character")

    # Detect custom Danbooru tags
    if _is_danbooru_tags(description):
        # Direct tag input -> skip Grok
        tags = {
            "pos_prompt": description,
            "neg_prompt": "worst quality, low quality, normal quality, lowres, blurry",
            "orientation": "portrait",
            "skip_face": False,
        }
        logger.info("imagegen custom tags (user %s): %s", user_id, description[:80])
    else:
        # Free-form description -> generate Grok tags
        if not character:
            character = {
                "image_prompt_prefix": IMAGEGEN_FIXED_PREFIX,
                "image_negative_prefix": "",
            }

        # Saved-character override set by the @name parser (Phase 1-D step 4)
        identity_override = context.user_data.get("identity_override")

        # When identity_override is set, force the character prefix to IMAGEGEN_FIXED_PREFIX —
        # so the previous session's persona prefix (last_character) doesn't pollute the saved character's identity.
        if identity_override:
            character = {
                "image_prompt_prefix": IMAGEGEN_FIXED_PREFIX,
                "image_negative_prefix": "",
            }

        # If we have previous tags, pass them in as chat_history (edit mode).
        # When identity_override is set, the character may have changed, so ignore last_tags.
        chat_history = []
        if last_tags and not identity_override:
            chat_history = [
                {"role": "user", "content": "(previous image request)"},
                {"role": "assistant", "content": f"Generated tags: {last_tags}"},
            ]

        # typing indicator
        async def keep_uploading():
            while True:
                await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                await asyncio.sleep(3)

        upload_task = asyncio.create_task(keep_uploading())
        try:
            tags = await generate_danbooru_tags(
                chat_history=chat_history,
                custom_command=description,
                character=character,
                char_id=char_id,
                identity_override=identity_override,
            )
            logger.info(
                "imagegen Grok tags (user %s, edit=%s, override=%s): pos=%s | neg=%s | orient=%s",
                user_id,
                bool(last_tags) and not identity_override,
                identity_override["name"] if identity_override else "(none)",
                tags["pos_prompt"][:300], tags["neg_prompt"][:100], tags.get("orientation"),
            )
        finally:
            upload_task.cancel()

    # Grok safety block check
    if tags.get("pos_prompt") == "BLOCKED":
        logger.warning("[security] Grok safety block: user=%s", user_id)
        await update.message.reply_text("_(Your message contains content that is not allowed.)_", parse_mode="Markdown")
        return

    # ComfyUI image generation
    async def keep_uploading():
        while True:
            await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    # Selected model
    model_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    selected_checkpoint = AVAILABLE_MODELS[model_key]["path"]

    upload_task = asyncio.create_task(keep_uploading())
    try:
        anchor_image = character.get("anchor_image", "") if character and isinstance(character, dict) and "anchor_image" in character else ""
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)
        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            anchor_image, orientation, skip_face,
            seed=user_seed,
            workflow_override=_HQ_WORKFLOW if use_hq else "",
            checkpoint_override=selected_checkpoint,
        )

        if image_path == "TIMEOUT":
            await update.message.reply_text("_(Image generation is taking too long. Please try again.)_", parse_mode="Markdown")
        elif image_path == "QUEUE_FULL":
            await update.message.reply_text("_(Lots of image requests right now — can't generate at the moment.)_", parse_mode="Markdown")
        elif image_path:
            await _send_image_with_video_option(
                target_message=update.message,
                context=context,
                user_id=user_id,
                image_path=image_path,
                description=description,
                danbooru_tags=tags["pos_prompt"],
            )
            increment_usage(user_id, "images")
            increment_daily_images(user_id)
            # Save into the session for follow-up edit-mode references
            context.user_data["last_tags"] = tags["pos_prompt"]
            context.user_data["last_char_id"] = char_id
            context.user_data["last_character"] = character
            context.user_data["last_seed"] = src.comfyui.last_used_seed
            logger.info("imagegen generation done: user=%s", user_id)

            # Confirm permanent partial-edit application (sent right after the image)
            edit_confirm = context.user_data.pop("pending_edit_confirm", None)
            if edit_confirm:
                _FIELD_LABELS = {
                    "appearance_tags": "appearance",
                    "clothing":        "clothing",
                    "underwear":       "underwear",
                    "body_shape":      "body shape",
                    "breast":          "bust",
                }
                labels = ", ".join(_FIELD_LABELS.get(f, f) for f in edit_confirm["fields"])
                await update.message.reply_text(
                    f"✏️ `{edit_confirm['name']}` permanently updated: {labels}",
                    parse_mode="Markdown",
                )
        else:
            await update.message.reply_text("_(Image generation failed. Please try again.)_", parse_mode="Markdown")
    finally:
        upload_task.cancel()


async def random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎲 Random SFW button callback — trait_pools random + Grok tags -> ComfyUI."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = query.from_user.id
    data = query.data or ""
    if data != "random:sfw":
        return
    mode = "sfw"

    # Onboarding check
    if not is_onboarded(user_id):
        main_link = f"https://t.me/{MAIN_BOT_USERNAME}" if MAIN_BOT_USERNAME else ""
        text = "Please send /start in the main bot first to register."
        if main_link:
            text += f"\n👉 {main_link}"
        await query.message.reply_text(text)
        return

    # Rate limiting
    allowed, _info = rate_limiter.check(user_id)
    if not allowed:
        await query.message.reply_text(
            "_(You're going too fast. Please try again in a moment.)_",
            parse_mode="Markdown",
        )
        return

    # HQ mode — read from the session toggle
    use_hq = bool(context.user_data.get("hq_mode", False))

    # ComfyUI queue check
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        await query.message.reply_text(
            "_(Lots of image requests right now — can't generate at the moment. Please try again shortly.)_",
            parse_mode="Markdown",
        )
        return

    # 1) trait_pools random sampling
    traits = roll_character(location="global")

    # 1-b) Pre-select the SFW scene type in Python (-> Grok)
    #     When Grok picks the pose autonomously from the list it tends to bias toward a few poses;
    #     pinning the "scene type" in Python eliminates that bias.
    sfw_scene = roll_sfw_scene()
    logger.info(
        "imagegen SFW scene pick: user=%s key=%s label=%s",
        user_id, sfw_scene["key"], sfw_scene["label"],
    )

    # 2) Grok random tag generation
    async def keep_uploading():
        while True:
            await query.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
            await asyncio.sleep(3)

    upload_task = asyncio.create_task(keep_uploading())
    try:
        tags = await generate_danbooru_tags_random(
            traits, mode, sfw_scene=sfw_scene
        )
    finally:
        upload_task.cancel()

    if tags.get("pos_prompt") == "BLOCKED":
        logger.warning("[security] Grok random safety block: user=%s mode=%s", user_id, mode)
        await query.message.reply_text(
            "_(Your message contains content that is not allowed.)_",
            parse_mode="Markdown",
        )
        return

    logger.info(
        "imagegen random Grok tags (user=%s mode=%s): pos=%s | neg=%s | orient=%s",
        user_id, mode, tags["pos_prompt"], tags["neg_prompt"], tags.get("orientation"),
    )

    # 3) ComfyUI image generation
    model_key = context.user_data.get("selected_model", DEFAULT_MODEL_KEY)
    selected_checkpoint = AVAILABLE_MODELS[model_key]["path"]

    upload_task = asyncio.create_task(keep_uploading())
    try:
        orientation = tags.get("orientation", "portrait")
        skip_face = tags.get("skip_face", False)

        image_path = await generate_image(
            tags["pos_prompt"], tags["neg_prompt"],
            "",  # no anchor_image — random characters don't need a fixed anchor
            orientation, skip_face,
            seed=0,
            workflow_override=_HQ_WORKFLOW if use_hq else "",
            checkpoint_override=selected_checkpoint,
        )

        if image_path == "TIMEOUT":
            await query.message.reply_text(
                "_(Image generation is taking too long. Please try again.)_",
                parse_mode="Markdown",
            )
            return
        if image_path == "QUEUE_FULL":
            await query.message.reply_text(
                "_(Lots of image requests right now — can't generate at the moment.)_",
                parse_mode="Markdown",
            )
            return
        if not image_path:
            await query.message.reply_text(
                "_(Image generation failed. Please try again.)_",
                parse_mode="Markdown",
            )
            return

        # 4) Send (+ 🎬 button)
        scene_desc = tags.get("scene_description", "random_sfw")
        await _send_image_with_video_option(
            target_message=query.message,
            context=context,
            user_id=user_id,
            image_path=image_path,
            description=scene_desc,
            danbooru_tags=tags["pos_prompt"],
            extra_caption="🎲 Random SFW",
            scene_key=sfw_scene.get("key") if sfw_scene else None,
        )

        increment_usage(user_id, "images")
        increment_daily_images(user_id)

        # 5) Save to the session — subsequent edits are handled by the standard imagegen_message flow
        # Pin the look: store the SFW tags (appearance + body IDENTITY) as the prefix.
        _dtags = traits.get("danbooru_tags", {}) if isinstance(traits, dict) else {}
        _sfw_appearance = (_dtags.get("appearance") or "").strip()
        _sfw_body = (_dtags.get("body") or "").strip()
        _sfw_clothing = (_dtags.get("clothing") or "").strip()

        # prefix = fixed prefix + IDENTITY tags (appearance + body silhouette).
        # The fixed prefix already includes "1girl", so strip any duplicate "1girl," from appearance.
        _sfw_appearance_clean = _sfw_appearance.replace("1girl, ", "").replace("1girl,", "")
        _identity_parts = [IMAGEGEN_FIXED_PREFIX] + [p for p in [_sfw_appearance_clean, _sfw_body] if p]
        _random_prefix = ", ".join(_identity_parts)

        # If Grok produced a resolved clothing (filled with colors), overwrite the session with it.
        # Otherwise keep the original trait (fallback). Grok rule: only fill items missing color, preserve already-colored ones.
        _resolved_clothing = (tags.get("clothing_resolved") or "").strip()
        _final_sfw_clothing = _resolved_clothing if _resolved_clothing else _sfw_clothing

        random_character = {
            "name": "random",
            "image_prompt_prefix": _random_prefix,
            "image_negative_prefix": "",
            # Structured tag blocks — generate_danbooru_tags picks a subset based on scene context
            "_random_sfw_tags": {
                "appearance": _sfw_appearance,
                "body": _sfw_body,
                "clothing": _final_sfw_clothing,  # <- Grok resolved (color-filled) or original
            },
            "_random_mode": mode,  # initial generation mode — for reference
            "_random_clothing_original": _sfw_clothing,  # original kept for debug / rollback
        } if _random_prefix else None

        context.user_data["last_tags"] = tags["pos_prompt"]
        context.user_data["last_char_id"] = ""
        context.user_data["last_character"] = random_character
        context.user_data["last_random_traits"] = traits
        context.user_data["last_seed"] = src.comfyui.last_used_seed
        context.user_data["last_random_mode"] = mode

        logger.info(
            "imagegen random generation done: user=%s mode=%s identity_prefix=%s "
            "clothing_resolved=%s (original=%s) seed=%s",
            user_id, mode,
            (_random_prefix[:80] if _random_prefix else "(none)"),
            (_final_sfw_clothing[:80] if _final_sfw_clothing else "(none)"),
            (_sfw_clothing[:40] if _sfw_clothing else "(none)"),
            src.comfyui.last_used_seed,
        )
    finally:
        upload_task.cancel()


async def _run_video_generation(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    target_message,
    user_id: int,
    image_path: str,
    description: str,
    danbooru_tags: str,
    motion_override: str | None,
    preferred_pose_key: str | None = None,
) -> bool:
    """Shared video-generation core. On success, sends the video + bumps usage counters. Returns: success flag.

    Does NOT delete the image file here — that's left to session lifetime so retries / other motions can reuse it.
    """
    chat_id = target_message.chat_id

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
        from src.grok import generate_video_prompts
        try:
            prompts = await generate_video_prompts(
                description,
                image_path=image_path,
                chat_history=None,
                danbooru_tags=danbooru_tags,
                mood="neutral",
                motion_override=motion_override,
                preferred_pose_key=preferred_pose_key,
            )
        except Exception as e:
            logger.error("ImageGen Grok video prompt failed: %s", e)
            prompts = {
                "motion_prompt": motion_override or description,
                "audio_prompt": "soft breath, intimate silence",
            }

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
                    logger.warning("VIDEO_DEBUG_DUMP send failed (imagegen): %s", _e)

        # Phase 2-B — log Step 2 tag-augment fallback success (for monitoring)
        if prompts.get("_csam_fallback_used"):
            logger.info("Grok Step 2 fallback succeeded: user=%s", user_id)

        # motion_override path explicit block (user-supplied motion tripped the CSAM filter)
        # NOTE: the standard 🎬 path also flips prompts_blocked when Grok returns BLOCKED
        if prompts.get("motion_prompt") == "BLOCKED" or prompts.get("_csam_blocked"):
            prompts_blocked = True
            logger.warning("Grok video finally blocked: user=%s", user_id)
        else:
            try:
                await notify_admins_video(
                    context,
                    triggering_user_id=user_id,
                    source="imagegen",
                    char_id="imagegen",
                    status="started",
                    pose_key=prompts.get("_debug_pose_key_resolved", ""),
                    safety_level=prompts.get("_debug_safety_level", ""),
                    motion_prompt=prompts.get("motion_prompt", ""),
                    audio_prompt=prompts.get("audio_prompt", ""),
                )
            except Exception as _e:
                logger.warning("admin video notify (started) failed: %s", _e)
            from src.video import generate_video
            video_path = await generate_video(
                image_path=image_path,
                motion_prompt=prompts["motion_prompt"],
                audio_prompt=prompts.get("audio_prompt", ""),
            )
    finally:
        upload_task.cancel()

    if prompts_blocked:
        # Grok blocked twice — show a single error to the user (count only increments on success, so no change here)
        await target_message.reply_text("😢 Video generation was blocked. Please try again.")
        logger.warning("imagegen video blocked by Grok: user=%s override=%s", user_id, bool(motion_override))
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                      char_id="imagegen", status="blocked",
                                      extra=f"motion_override={bool(motion_override)}")
        except Exception:
            pass
        return False

    if video_path:
        with open(video_path, "rb") as f:
            await target_message.reply_video(video=f)
        increment_usage(user_id, "videos")
        increment_daily_videos(user_id)
        try:
            os.unlink(video_path)
        except OSError:
            pass
        logger.info("imagegen video generation done: user=%s override=%s", user_id, bool(motion_override))
        try:
            await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                      char_id="imagegen", status="success",
                                      pose_key=prompts.get("_debug_pose_key_resolved", ""))
        except Exception:
            pass
        return True

    await target_message.reply_text("😢 Video generation failed. Please try again.")
    logger.error("imagegen video generation failed: user=%s override=%s", user_id, bool(motion_override))
    try:
        await notify_admins_video(context, triggering_user_id=user_id, source="imagegen",
                                  char_id="imagegen", status="failed",
                                  extra=f"motion_override={bool(motion_override)} — check logs")
    except Exception:
        pass
    return False


async def imagegen_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎬 video generation button — always uses Grok auto-motion (danbooru only)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    if not data.startswith("video:"):
        return

    ctx_id = data.split(":", 1)[1]
    ctx = get_video_context(ctx_id)
    if not ctx:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text("⏰ Video generation has timed out.")
        return

    user_id = ctx["user_id"]

    # Button state -> generating
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏳ Generating video...", callback_data="noop")
        ]]))
    except Exception:
        pass

    ok = await _run_video_generation(
        context=context,
        target_message=query.message,
        user_id=user_id,
        image_path=ctx["image_path"],
        description=ctx["description"],
        danbooru_tags=ctx.get("danbooru_tags", ""),
        motion_override=None,  # button always uses auto motion
        preferred_pose_key=ctx.get("scene_key"),
    )

    if ok:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    else:
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Generate video", callback_data=f"video:{ctx_id}"),
            ]]))
        except Exception:
            pass


async def imagegen_scene(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scene [key|off|list|status] — force a SFW scene override (Admin testing only).

    - /scene list              — list SFW scene keys
    - /scene status            — show the current SFW override
    - /scene <sfw_key>         — pin to that SFW scene
    - /scene off / clear       — clear the SFW override
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
        if s_forced:
            line = f"🌸 SFW: pinned to `{s_forced}`"
        else:
            line = "🌸 SFW: random"
        await update.message.reply_text(line + "\n\n(use /scene off to clear)")
        return

    # key input — apply SFW scene key
    key = args[0]
    sfw_keys = trait_pools.list_sfw_scene_keys()

    if key in sfw_keys:
        ok, msg = trait_pools.set_forced_sfw_scene(key)
        await update.message.reply_text(("✅ SFW: " if ok else "❌ SFW: ") + msg)
    else:
        await update.message.reply_text(
            f"❌ Unknown scene key '{key}'.\n"
            f"SFW: {', '.join(sfw_keys[:5])}...\n"
            f"Full list: /scene list"
        )


# ═══════════════════════════════════════════════════════════════════════
# Saved Characters UI (Feature 1 Phase 1-B / 1-C)
# ═══════════════════════════════════════════════════════════════════════

_SAVE_NAME_PROMPT = (
    "💾 Saving this character.\n\n"
    "Please enter a name (letters / digits / underscore, 1-20 chars).\n"
    "Examples: `minkyung`, `user_01`, `yerin_dress`\n\n"
    "Send /cancel to cancel."
)


async def savechar_init_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💾 Save button click — Grok-classifier produces a nested 5-block split, then enter name-input state.

    Both /random and custom-text paths send the last_tags blob to Grok and store the result
    under the unified appearance_tags / clothing / underwear / body_shape{} / breast{} nested
    schema (same shape as images/char*.json).
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    last_tags = context.user_data.get("last_tags", "")
    if not last_tags:
        await query.message.reply_text("_(No image to save. Please generate an image first.)_", parse_mode="Markdown")
        return

    # Classification progress notice (1-3s expected)
    progress_msg = await query.message.reply_text("_(Analyzing character...)_", parse_mode="Markdown")

    try:
        nested = await classify_tags_to_nested_blocks(last_tags)
    except Exception as e:
        logger.error("classify_tags_to_nested_blocks failed: user=%s err=%s", user_id, e)
        try:
            await progress_msg.edit_text("_(Character analysis failed. Please try again.)_", parse_mode="Markdown")
        except Exception:
            pass
        return

    # Refuse to save when every entry is empty (classification failed) — checks all 3 flat strings + 2 nested dicts
    has_content = (
        (nested.get("appearance_tags") or "").strip()
        or (nested.get("clothing") or "").strip()
        or (nested.get("underwear") or "").strip()
        or any(nested.get("body_shape", {}).values())
        or any(nested.get("breast", {}).values())
    )
    if not has_content:
        try:
            await progress_msg.edit_text("_(Character analysis came back empty. Please try again.)_", parse_mode="Markdown")
        except Exception:
            pass
        return

    base_pending = {
        "appearance_tags": (nested.get("appearance_tags") or "").strip(),
        "clothing":        (nested.get("clothing") or "").strip(),
        "underwear":       (nested.get("underwear") or "").strip(),
        "body_shape":      nested.get("body_shape") or {},
        "breast":          nested.get("breast") or {},
    }

    logger.info(
        "[savechar] Grok classify nested: user=%s "
        "appearance=%d clothing=%d underwear=%d body_shape_keys=%d breast_keys=%d",
        user_id,
        len(base_pending["appearance_tags"]),
        len(base_pending["clothing"]),
        len(base_pending["underwear"]),
        len([k for k, v in base_pending["body_shape"].items() if v]),
        len([k for k, v in base_pending["breast"].items() if v]),
    )

    # Delete the analysis-progress message
    try:
        await progress_msg.delete()
    except Exception:
        pass

    # Find an empty slot
    available_slot = find_available_slot(user_id)
    if available_slot is not None:
        # Auto-assign
        context.user_data["pending_save"] = {**base_pending, "slot": available_slot}
        await query.message.reply_text(_SAVE_NAME_PROMPT, parse_mode="Markdown")
    else:
        # Slots full — pick one to overwrite
        chars = list_saved_characters(user_id)
        buttons = []
        for c in chars:
            buttons.append([InlineKeyboardButton(
                f"Slot {c['slot']}: {c['name']}", callback_data=f"savechar:slot:{c['slot']}"
            )])
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="savechar:cancel")])
        context.user_data["pending_save"] = {**base_pending, "slot": None}
        await query.message.reply_text(
            "All slots are full. Which slot would you like to overwrite?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def savechar_slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slot selection (overwrite) -> wait for name input."""
    query = update.callback_query
    await query.answer()
    data = query.data  # "savechar:slot:1"
    slot = int(data.split(":")[-1])

    pending = context.user_data.get("pending_save")
    # nested schema: at minimum appearance_tags must be present
    if not pending or not pending.get("appearance_tags"):
        await query.message.reply_text("_(Save session expired. Please try again.)_", parse_mode="Markdown")
        return
    pending["slot"] = slot  # preserve the rest of the nested keys
    context.user_data["pending_save"] = pending
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(_SAVE_NAME_PROMPT, parse_mode="Markdown")


async def savechar_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel save."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_save", None)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text("_(Save cancelled.)_", parse_mode="Markdown")


async def imagegen_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel — clear the pending save state."""
    if context.user_data.pop("pending_save", None):
        await update.message.reply_text("_(Save cancelled.)_", parse_mode="Markdown")
    else:
        await update.message.reply_text("_(No active task in progress.)_", parse_mode="Markdown")


async def imagegen_chars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chars — saved character list."""
    user_id = update.effective_user.id
    chars = list_saved_characters(user_id)
    if not chars:
        await update.message.reply_text(
            "No saved characters yet.\nAfter generating an image, tap 💾 Save character to save it."
        )
        return
    # Delete button per character
    buttons = [
        [InlineKeyboardButton(f"🗑️ Delete slot {c['slot']} ({c['name']})",
                              callback_data=f"savechar:delete:{c['slot']}")]
        for c in chars
    ]
    await update.message.reply_text(
        _format_saved_chars_list(user_id),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def savechar_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🗑️ slot delete button."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    slot = int(query.data.split(":")[-1])
    ok = delete_saved_character(user_id, slot)
    if ok:
        await query.message.reply_text(f"_(Slot {slot} character deleted.)_", parse_mode="Markdown")
    else:
        await query.message.reply_text("_(Delete failed — slot is already empty.)_", parse_mode="Markdown")


async def _try_handle_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """While in pending_save state, treat the text as a name. Returns True if handled."""
    pending = context.user_data.get("pending_save")
    # nested schema: at minimum appearance_tags must be filled in
    if not pending or not pending.get("appearance_tags") or pending.get("slot") is None:
        return False

    user_id = update.effective_user.id
    name = (update.message.text or "").strip()

    if not is_valid_saved_char_name(name):
        await update.message.reply_text(
            "_(Name must be 1-20 chars: letters, digits, underscore. Please try again.)_",
            parse_mode="Markdown",
        )
        return True

    # Check for duplicate name (same user, different slot)
    existing = get_saved_character_by_name(user_id, name)
    if existing and existing["slot"] != pending["slot"]:
        await update.message.reply_text(
            f"_(Name `{name}` is already used in slot {existing['slot']}. Please pick a different name.)_",
            parse_mode="Markdown",
        )
        return True

    try:
        save_character(
            user_id=user_id,
            slot=pending["slot"],
            name=name,
            appearance_tags=pending.get("appearance_tags", ""),
            clothing=pending.get("clothing", ""),
            underwear=pending.get("underwear", ""),
            body_shape=pending.get("body_shape") or {},
            breast=pending.get("breast") or {},
        )
    except Exception as e:
        logger.error("save_character failed: user=%s slot=%s name=%s err=%s", user_id, pending["slot"], name, e)
        await update.message.reply_text("_(Save failed. Please try again.)_", parse_mode="Markdown")
        context.user_data.pop("pending_save", None)
        return True

    logger.info(
        "saved_character commit: user=%s slot=%s name=%s "
        "appearance=%d clothing=%d underwear=%d body_shape_keys=%d breast_keys=%d",
        user_id, pending["slot"], name,
        len(pending.get("appearance_tags", "")),
        len(pending.get("clothing", "")),
        len(pending.get("underwear", "")),
        len([k for k, v in (pending.get("body_shape") or {}).items() if v]),
        len([k for k, v in (pending.get("breast") or {}).items() if v]),
    )

    context.user_data.pop("pending_save", None)
    await update.message.reply_text(
        f"✅ Character saved!\n"
        f"Slot {pending['slot']}: `{name}`\n\n"
        f"Next time you can recall it with `@{name}`.\n"
        f"e.g. `@{name} beach bikini`",
        parse_mode="Markdown",
    )
    return True


def register_imagegen_handlers(app):
    """Register handlers on the image generator bot."""
    app.add_handler(CommandHandler("start", imagegen_start))
    app.add_handler(CommandHandler("help", imagegen_help))
    app.add_handler(CommandHandler("reset", imagegen_reset))
    app.add_handler(CommandHandler("seed", imagegen_seed))
    app.add_handler(CommandHandler("model", imagegen_model))
    app.add_handler(CommandHandler("hq", imagegen_hq))
    app.add_handler(CommandHandler("random", imagegen_random))
    app.add_handler(CommandHandler("scene", imagegen_scene))
    app.add_handler(CommandHandler("chars", imagegen_chars))
    app.add_handler(CommandHandler("cancel", imagegen_cancel))
    app.add_handler(CallbackQueryHandler(random_callback, pattern=r"^random:sfw$"))
    app.add_handler(CallbackQueryHandler(imagegen_video_callback, pattern=r"^video:"))
    app.add_handler(CallbackQueryHandler(savechar_init_callback, pattern=r"^savechar:init$"))
    app.add_handler(CallbackQueryHandler(savechar_slot_callback, pattern=r"^savechar:slot:[1-3]$"))
    app.add_handler(CallbackQueryHandler(savechar_cancel_callback, pattern=r"^savechar:cancel$"))
    app.add_handler(CallbackQueryHandler(savechar_delete_callback, pattern=r"^savechar:delete:[1-3]$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, imagegen_message))
