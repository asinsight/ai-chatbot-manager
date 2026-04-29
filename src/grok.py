import json
import logging
import os
import re
from pathlib import Path
from string import Template

from openai import AsyncOpenAI

from src.pose_motion_presets import (
    list_keys as _list_pose_keys,
    lookup as _pose_lookup,
)


logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────
# Externalized prompts — config/grok_prompts.json
# ───────────────────────────────────────────────────────────────────────
# The five system prompts (system / video_analyzer / random / classify / partial_edit)
# live in config/grok_prompts.json instead of in code. Loaded once at module import
# (fail-fast — missing/empty key raises RuntimeError immediately). Lets you tune the
# prompts without touching code.
_PROMPTS_PATH = Path(__file__).resolve().parent.parent / "config" / "grok_prompts.json"
_REQUIRED_PROMPT_KEYS = ("system", "video_analyzer", "random", "classify", "partial_edit")


def _load_grok_prompts() -> dict:
    """Load grok_prompts.json and validate required keys / non-empty strings. Raises RuntimeError on failure.

    Deliberately no fallback strings — prevents accidentally running with an
    empty/wrong prompt.
    """
    try:
        raw = _PROMPTS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Grok prompts file not found at {_PROMPTS_PATH}. "
            "config/grok_prompts.json must exist for the grok module to load."
        ) from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Grok prompts file at {_PROMPTS_PATH} is not valid JSON: {e}"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Grok prompts file at {_PROMPTS_PATH} must be a JSON object."
        )
    missing = [k for k in _REQUIRED_PROMPT_KEYS if k not in data]
    if missing:
        raise RuntimeError(
            f"Grok prompts file at {_PROMPTS_PATH} is missing required keys: {missing}"
        )
    empty = [k for k in _REQUIRED_PROMPT_KEYS if not (isinstance(data[k], str) and data[k].strip())]
    if empty:
        raise RuntimeError(
            f"Grok prompts file at {_PROMPTS_PATH} has empty/non-string values for keys: {empty}"
        )
    return data


PROMPTS = _load_grok_prompts()

# VIDEO_SYSTEM_PROMPT — load the Wan i2v guide (src/wan_i2v_prompting_guide.md).
# SFW fork: original wan_nsfw_i2v_prompting_guide.md was renamed and the NSFW
# sections stripped. Used as the system prompt for Composer (Stage 2).
_GUIDE_PATH = Path(__file__).parent / "wan_i2v_prompting_guide.md"
try:
    VIDEO_SYSTEM_PROMPT = _GUIDE_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    logger.warning("Video guide file not found at %s, using fallback", _GUIDE_PATH)
    VIDEO_SYSTEM_PROMPT = "You are a video motion prompt generator. Return JSON with motion_prompt and audio_prompt."

# ───────────────────────────────────────────────────────────────────────
# video-improve2 (P15) — Stage 1 Analyzer system prompt
# ───────────────────────────────────────────────────────────────────────
# Analyzer role: takes an image + (optional) danbooru tags + (optional) chat
# intent hint and returns structured JSON the WAN 2.2 i2v Composer consumes
# directly.
# Safety-first: on CSAM / minor detection, return BLOCKED immediately with the
# other fields blank.
# pose_key enum is injected from pose_motion_presets at module load time.
_ANALYZER_POSE_KEYS_ENUM = ", ".join(f'"{k}"' for k in _list_pose_keys())

# Substitute the ${pose_keys_enum} placeholder defined in the JSON at module-load time.
VIDEO_ANALYZER_PROMPT = Template(PROMPTS["video_analyzer"]).safe_substitute(
    pose_keys_enum=_ANALYZER_POSE_KEYS_ENUM,
)


def _strip_emojis(text: str) -> str:
    """Strip emojis from text — keeps emojis from contaminating Grok tag generation."""
    return re.sub(
        r"[\U0001F600-\U0001F64F"   # Emoticons
        r"\U0001F300-\U0001F5FF"    # Misc Symbols and Pictographs
        r"\U0001F680-\U0001F6FF"    # Transport and Map
        r"\U0001F900-\U0001F9FF"    # Supplemental Symbols
        r"\U0001FA00-\U0001FA6F"    # Chess Symbols
        r"\U0001FA70-\U0001FAFF"    # Symbols Extended-A
        r"\U00002702-\U000027B0"    # Dingbats
        r"\U0000FE00-\U0000FE0F"    # Variation Selectors
        r"\U0000200D"               # Zero Width Joiner
        r"\U000023E9-\U000023F3"    # Misc symbols
        r"\U0000231A-\U0000231B"    # Watch/Hourglass
        r"\U00002934-\U00002935"    # Arrows
        r"\U000025AA-\U000025FE"    # Geometric shapes
        r"\U00002600-\U000026FF"    # Misc symbols
        r"\U00002700-\U000027BF"    # Dingbats
        r"]+", "", text
    ).strip()


def _format_chat_history(chat_history: list[dict]) -> str:
    """Convert chat history to plain text (with emojis stripped)."""
    lines = []
    for msg in chat_history:
        role = msg.get("role", "unknown")
        content = _strip_emojis(msg.get("content", ""))
        label = "User" if role == "user" else "Ella"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _parse_json_response(text: str) -> dict | None:
    """Extract and parse a JSON object from a Grok response."""
    json_block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if json_block:
        text_to_parse = json_block.group(1).strip()
    else:
        json_obj = re.search(r"\{.*\}", text, re.DOTALL)
        if json_obj:
            text_to_parse = json_obj.group(0)
        else:
            return None

    try:
        data = json.loads(text_to_parse)
        if "pos_prompt" in data and "neg_prompt" in data:
            if "orientation" not in data:
                data["orientation"] = "portrait"
            if "skip_face" not in data:
                data["skip_face"] = False
            return data
    except json.JSONDecodeError:
        pass

    return None


def _default_tags() -> dict:
    """Default tag set returned on parse failure or API error."""
    return {
        "pos_prompt": "upper body, looking at viewer, smile, blush, simple background, rating:safe",
        "neg_prompt": "",
        "orientation": "portrait",
        "skip_face": False,
    }


def _load_image_config(char_id: str) -> dict:
    """Load body_shape / breast / clothing / underwear tags from images/char*.json.

    SFW fork schema: body_shape{size,build,curve,accent,ass}, breast{size,feature}, clothing, underwear, special, expressions.
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "images", f"{char_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "clothing": "",
        "underwear": "",
        "body_shape": {"size": "", "build": "", "curve": "", "accent": "", "ass": ""},
        "breast": {"size": "", "feature": ""},
        "special": "",
    }


_prompting_guide_cache = None


def _load_prompting_guide() -> str:
    """Load danbooru_prompting_guide.md (cached)."""
    global _prompting_guide_cache
    if _prompting_guide_cache is not None:
        return _prompting_guide_cache
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "danbooru_prompting_guide.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            _prompting_guide_cache = f.read()
    else:
        _prompting_guide_cache = ""
    return _prompting_guide_cache


async def generate_danbooru_tags(
    chat_history: list[dict],
    custom_command: str = "",
    character: dict = None,
    char_id: str = "",
    outfit_override: dict | None = None,
    location_background: str = "",
    identity_override: dict | None = None,
    scene_lock: dict | None = None,
) -> dict:
    """Analyze the conversation context and produce a full Danbooru prompt (positive + negative).

    Args:
        chat_history: chat history [{"role": "user"/"assistant", "content": "..."}]
        custom_command: custom directive entered after /image (e.g. "lying on bed")
        character: character dict (must include image_prompt_prefix, image_negative_prefix)
        char_id: character id (e.g. "char01") — used to load images/char01.json
        location_background: danbooru background tags for the current location
        identity_override: saved-character dict (saved_characters DB row).
            When provided, replaces the image_config-based body/clothing/underwear blocks
            with the saved_characters tag blocks (appearance / body_shape / clothing / underwear).
        scene_lock: pre-decided SFW scene dict. Forces person_tags / pose / camera verbatim
            and instructs Grok to add exclude_tags to the negative prompt.
            Schema: {"person_tags", "scene_tags", "pose", "camera", "exclude_tags": list, ...}

    Returns:
        {"pos_prompt": "complete positive prompt", "neg_prompt": "complete negative prompt"}
    """
    api_key = os.getenv("GROK_API_KEY", "")
    model = os.getenv("GROK_PROMPTING_IMAGE_MODEL") or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")

    if not api_key:
        return _default_tags()

    pos_prefix = character.get("image_prompt_prefix", "") if character else ""
    neg_prefix = character.get("image_negative_prefix", "") if character else ""

    # Split the 6 messages into Earlier context / Recent conversation
    if len(chat_history) > 3:
        earlier = chat_history[:-3]
        recent = chat_history[-3:]
    else:
        earlier = []
        recent = chat_history
    earlier_text = _format_chat_history(earlier) if earlier else ""
    recent_text = _format_chat_history(recent)

    custom_part = custom_command.strip() if custom_command.strip() else "none"

    location_bg_block = ""
    if location_background and location_background.strip():
        location_bg_block = (
            f"## Scene background (use these tags for the background/scene portion of the positive prompt — "
            f"do NOT invent unrelated background tags):\n{location_background.strip()}\n\n"
        )

    image_config: dict = {}

    if identity_override:
        saved_appearance = (identity_override.get("appearance_tags") or "").strip()
        saved_appearance = re.sub(r"^1girl\s*,\s*", "", saved_appearance, flags=re.IGNORECASE)

        image_config = {
            "clothing":   (identity_override.get("clothing") or "").strip(),
            "underwear":  (identity_override.get("underwear") or "").strip(),
            "body_shape": identity_override.get("body_shape") or {},
            "breast":     identity_override.get("breast") or {},
            "special":    "",
            "expressions": {},
        }

        if outfit_override:
            clothing_tags = outfit_override["clothing"]
            underwear_tags = outfit_override["underwear"]
        else:
            clothing_tags = image_config["clothing"]
            underwear_tags = image_config["underwear"]

        if saved_appearance and pos_prefix:
            pos_prefix = f"{pos_prefix}, {saved_appearance}"
        elif saved_appearance:
            pos_prefix = saved_appearance

        logger.info(
            "[grok] identity_override active: name=%s slot=%s "
            "appearance=%d clothing=%d underwear=%d body_shape=%s breast=%s",
            identity_override.get("name", "?"), identity_override.get("slot", "?"),
            len(saved_appearance), len(clothing_tags), len(underwear_tags),
            list((image_config["body_shape"] or {}).keys()),
            list((image_config["breast"] or {}).keys()),
        )
    else:
        image_config = _load_image_config(char_id) if char_id else _load_image_config("")

        clothing_tags = outfit_override["clothing"] if outfit_override else image_config.get('clothing', '')
        underwear_tags = outfit_override["underwear"] if outfit_override else image_config.get('underwear', '')

    body_shape = image_config.get('body_shape', {}) or {}
    breast = image_config.get('breast', {}) or {}

    def _fmt(label, tags):
        return f"## {label}: {tags}\n\n" if tags and tags.strip() else ""

    # IDENTITY block — silhouette/build tags. ALWAYS include (shape is visible through clothing).
    identity_block = (
        _fmt("Body Shape — Size [IDENTITY, always include]", body_shape.get('size', ''))
        + _fmt("Body Shape — Build [IDENTITY, always include]", body_shape.get('build', ''))
        + _fmt("Body Shape — Curve [IDENTITY, always include]", body_shape.get('curve', ''))
        + _fmt("Body Shape — Accent [IDENTITY, include when upper body/abs visible]", body_shape.get('accent', ''))
        + _fmt("Body Shape — Ass [IDENTITY, include when lower body/butt framed]", body_shape.get('ass', ''))
        + _fmt("Breast — Size [IDENTITY, always include — shapes silhouette even when clothed]", breast.get('size', ''))
        + _fmt("Breast — Feature [IDENTITY, include when breasts framed/visible]", breast.get('feature', ''))
    )

    # Random character tag block — passes SFW tags of a /random-generated pseudo-character to Grok.
    random_tags_block = ""
    if character and character.get("name") == "random":
        _sfw = character.get("_random_sfw_tags", {}) or {}
        _sfw_cloth = (_sfw.get("clothing") or "").strip()
        if _sfw_cloth and not clothing_tags:
            clothing_tags = _sfw_cloth
        random_tags_block = (
            "## Random Character Tag Set (SFW identity — always fully clothed):\n"
            f"- [SFW / ALWAYS] appearance: {_sfw.get('appearance', '')}\n"
            f"- [SFW / ALWAYS] body silhouette: {_sfw.get('body', '')}\n"
            f"- [SFW / DEFAULT] base clothing: {_sfw_cloth or '(none)'}\n\n"
            "## Random Character Priority Rules (STRICT):\n"
            "1. **USER CUSTOM INSTRUCTION is HIGHEST PRIORITY** for SFW-compatible changes — pose / composition / framing / mood / specific outfit (e.g., `교복으로`, `비키니로`, `드레스로`).\n"
            "2. NEVER honor undressing / nudity / exposure requests in custom instructions — the pipeline is SFW-only. The character stays fully clothed regardless.\n"
            "3. Always include the SFW identity tags (appearance + body) and the base clothing.\n\n"
        )

    # Scene Lock block — SFW pose-scene directive. Forces person_tags / pose / camera verbatim.
    scene_lock_block = ""
    if scene_lock:
        _exclude = scene_lock.get("exclude_tags") or []
        _exclude_str = ", ".join(_exclude) if isinstance(_exclude, list) else str(_exclude)
        scene_lock_block = (
            "## Pre-selected SFW Scene Lock (DECISIVE — do not deviate)\n"
            f"- Required person tags (use VERBATIM at the start of pos_prompt, in the person-count slot): {scene_lock.get('person_tags', '')}\n"
            f"- Required pose tag (use VERBATIM in pos_prompt — pose/composition slot): {scene_lock.get('pose', '')}\n"
            f"- Required camera tag (use VERBATIM in pos_prompt — composition slot): {scene_lock.get('camera', '')}\n"
            f"- Additional scene tags (append to pos_prompt if present): {scene_lock.get('scene_tags') or '(none)'}\n"
            f"- Excluded tags (MUST add to neg_prompt — NEVER include in pos_prompt): {_exclude_str or '(none)'}\n\n"
            "RULES:\n"
            "1. The scene type is already decided. Use person_tags / pose / camera VERBATIM — do NOT substitute, do NOT rephrase.\n"
            "2. Append every excluded tag to the negative prompt. Never emit them in the positive prompt.\n"
            "3. You MAY freely adjust: clothing (within SFW outfit rules — never undress), background, facial expression, body shape descriptors, orientation/skip_face, and any other quality/style tokens.\n"
            "4. The scene tags above OVERRIDE rule 9-1 person-count defaults — use the provided person_tags as-is.\n\n"
        )

    user_message = (
        f"{scene_lock_block}"
        f"## Character Appearance Prefix (MUST include in positive prompt):\n{pos_prefix}\n\n"
        f"## Character Negative Prefix (MUST include in negative prompt):\n{neg_prefix}\n\n"
        f"{random_tags_block}"
        f"## Character Clothing (PRIORITY tags — use these EXACT tags as the primary clothing reference. Do NOT change colors or substitute different items. You MAY OMIT individual items not visible in the chosen camera framing/pose — e.g., shoes when framing is upper_body / close-up / portrait. Keep all visible items intact with exact colors. The outfit is ALWAYS fully worn — never undressing/displaced.):\n{clothing_tags}\n\n"
        f"## Character Underwear (PRIORITY tags — use these EXACT tags ONLY if the canonical outfit is underwear-as-outerwear (e.g., bikini/swimsuit/lingerie character). Otherwise, do not surface underwear in the positive prompt. Do NOT change colors, do NOT substitute.):\n{underwear_tags}\n\n"
        f"{identity_block}"
        f"## Character Body Tag Guidance:\n"
        f"- [IDENTITY] tags (Body Shape size/build/curve + Breast size): ALWAYS include in the positive prompt. These describe the character's silhouette and are visible even when fully clothed.\n"
        f"- [IDENTITY] accent/ass/breast_feature: include when the relevant framing/composition shows that body part.\n"
        f"- This pipeline is SFW. Never include nipple/genital/anus/pubic/fluids tags in any output.\n\n"
        f"## Character Special Tags (SFW identity-only descriptors — never explicit):\n{image_config.get('special', '')}\n\n"
        f"## Character Expression Presets (reference — use when the mood matches):\n{json.dumps(image_config.get('expressions', {}))}\n\n"
        f"{location_bg_block}"
        f"## Earlier context (background reference):\n{earlier_text}\n\n"
        f"## Recent conversation (FOCUS ON THIS for mood, pose, and expression):\n{recent_text}\n\n"
        f"## Custom instruction: {custom_part}\n\n"
        f"If the custom instruction contains [mood:X], use the matching expression preset tags exactly. "
        f"Otherwise, choose expression tags AUTONOMOUSLY based on the conversation's emotional context. "
        f"For all moods, generate appropriate SFW expression tags yourself — do NOT default to any single preset. "
        f"Generate a complete positive and negative danbooru tag prompt that fits the conversation context, "
        f"keeping the character fully clothed and the scene SFW at all times."
    )

    prompting_guide = _load_prompting_guide()

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    messages = [
        {"role": "system", "content": PROMPTS["system"]},
        {"role": "system", "content": f"## Danbooru Prompting Reference:\n{prompting_guide}"},
        {"role": "user", "content": user_message},
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        content = response.choices[0].message.content or ""
        result = _parse_json_response(content)
        if result:
            return result
        logger.warning("Grok tag parse failed: %s", content[:200])
        return _default_tags()
    except Exception as e:
        logger.error("Grok tag generation failed: %s", e)
        if "CSAM" in str(e) or "403" in str(e):
            return {"pos_prompt": "BLOCKED", "neg_prompt": "", "orientation": "portrait", "skip_face": False}
        return _default_tags()


async def generate_danbooru_tags_random(
    traits: dict,
    mode: str = "sfw",
    sfw_scene: dict | None = None,
) -> dict:
    """Build a complete Danbooru prompt from random character traits in SFW mode.

    SFW fork: NSFW mode/scenes are not supported — `mode` is kept for ABI compat only
    and is always forced to the SFW path.

    Args:
        traits: return value of `src.trait_pools.roll_character()`
        mode: formal mode argument (always treated as SFW)
        sfw_scene: result of `src.trait_pools.roll_sfw_scene()`

    Returns:
        {"pos_prompt": ..., "neg_prompt": ..., "orientation": ..., "skip_face": ..., "scene_description": ...}
    """
    api_key = os.getenv("GROK_API_KEY", "")
    model = os.getenv("GROK_PROMPTING_IMAGE_MODEL") or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")

    # SFW fork — ignore the mode argument; always handle as SFW
    mode_norm = "sfw"

    if not api_key:
        fallback = _default_tags()
        fallback["scene_description"] = f"random_{mode_norm}"
        return fallback

    dtags = traits.get("danbooru_tags", {}) if isinstance(traits, dict) else {}
    appearance_tags = dtags.get("appearance", "")
    body_tags = dtags.get("body", "")
    clothing_tags = dtags.get("clothing", "")
    underwear_tags = dtags.get("underwear", "")

    scene_block = ""
    if sfw_scene:
        scene_block = (
            "## Pre-selected SFW Scene (ONLY person_tags + pose + camera are LOCKED — other fields are reference clues to INFER the situation)\n"
            f"- Scene key: {sfw_scene['key']}\n"
            f"- Label: {sfw_scene['label']}\n"
            f"- Required person tags (use AS-IS — LOCKED): {sfw_scene['person_tags']}\n"
            f"- Pose pool — pick 1 RANDOMLY from this list ONLY (LOCKED): {sfw_scene['pose_pool']}\n"
            f"- Camera composition pool — pick 1 RANDOMLY from this list (LOCKED): {sfw_scene['camera_pool']}\n"
            f"- Location reference (READ to understand where — pick a fitting location or synthesize your own suitable one): {sfw_scene['location_pool']}\n"
            f"- Activity reference (READ to INFER the situation — time of day, weather, indoor/outdoor, activity context, mood. Do NOT copy these tags verbatim. Use them to UNDERSTAND the scene, then GENERATE fresh, well-chosen tags that fit your inferred situation): {sfw_scene['activity_tags']}\n"
            f"- Expression hint (reference for mood — adapt freely): {sfw_scene['expression_hint']}\n"
            f"- Notes: {sfw_scene['notes']}\n\n"
            "LOCKED: person_tags + pose + camera. "
            "INFERRED (read clues, generate your own fitting tags): location, weather, time of day, concrete props, mood, expression, clothing state. "
            "Read activity_tags as a DESCRIPTION of the situation (e.g., if it says `night_sky, stars, telescope`, infer nighttime outdoor stargazing → generate YOUR OWN tags like `night, starry_sky, tripod`; if it says `picnic_blanket, basket, fruit, outdoors`, infer casual outdoor meal → generate fitting tags like `picnic_blanket, basket, fruit`). "
            "ABSOLUTE: NEVER emit any lighting / atmosphere / color-grading / illumination / glow / shadow tag in the positive prompt. Use only location and time-of-day tags — the SDXL checkpoint handles lighting implicitly. See the LIGHTING RULE in the system prompt.\n\n"
        )

    user_message = (
        f"{scene_block}"
        f"## MODE: SFW\n\n"
        f"## Character Appearance (MUST include EXACTLY in positive prompt):\n{appearance_tags}\n\n"
        f"## Character Body Shape (include when the relevant body is visible):\n{body_tags}\n\n"
        f"## Character Clothing (MUST use these EXACT tags; outfit is always fully worn — never undressing):\n{clothing_tags}\n\n"
        f"## Character Underwear (use EXACT tags ONLY if the canonical outfit treats underwear as outerwear — e.g., bikini/swimsuit/lingerie character):\n{underwear_tags}\n\n"
        f"## Instructions:\n"
        f"- Decide pose, expression, composition, camera angle, and location AUTONOMOUSLY within SFW bounds.\n"
        f"- Maximize diversity — choose a different pose/expression/location than what you typically produce. Be bold but stay SFW.\n"
        f"- Subject is ALWAYS an adult 1girl, fully clothed.\n"
        f"- Generate the full danbooru prompt JSON as specified."
    )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    messages = [
        {"role": "system", "content": PROMPTS["random"]},
        {"role": "user", "content": user_message},
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=1.3,  # encourages variety
        )
        content = response.choices[0].message.content or ""
        result = _parse_json_response(content)
        if result:
            need_extract = any(k not in result for k in ("scene_description", "clothing_resolved", "underwear_resolved"))
            if need_extract:
                try:
                    json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
                    raw = json_block.group(1).strip() if json_block else re.search(r"\{.*\}", content, re.DOTALL).group(0)
                    extra = json.loads(raw)
                    if "scene_description" not in result:
                        result["scene_description"] = extra.get("scene_description", f"random_{mode_norm}")
                    if "clothing_resolved" not in result:
                        result["clothing_resolved"] = extra.get("clothing_resolved", "") or ""
                    if "underwear_resolved" not in result:
                        result["underwear_resolved"] = extra.get("underwear_resolved", "") or ""
                except Exception:
                    if "scene_description" not in result:
                        result["scene_description"] = f"random_{mode_norm}"
                    if "clothing_resolved" not in result:
                        result["clothing_resolved"] = ""
                    if "underwear_resolved" not in result:
                        result["underwear_resolved"] = ""
            return result
        logger.warning("Grok random tag parse failed: %s", content[:200])
        fallback = _default_tags()
        fallback["scene_description"] = f"random_{mode_norm}"
        return fallback
    except Exception as e:
        logger.error("Grok random tag generation failed: %s", e)
        if "CSAM" in str(e) or "403" in str(e):
            return {
                "pos_prompt": "BLOCKED",
                "neg_prompt": "",
                "orientation": "portrait",
                "skip_face": False,
                "scene_description": "blocked",
            }
        fallback = _default_tags()
        fallback["scene_description"] = f"random_{mode_norm}"
        return fallback


# ───────────────────────────────────────────────────────────────────────
# Nested classifier (used only by savechar_init_callback) — unifies the
# /random and custom-text paths into the same nested structure as
# images/char*.json sub-attributes.
# ───────────────────────────────────────────────────────────────────────

# Sub-keys for the classifier's nested structure
_CLASSIFY_BODY_SHAPE_KEYS = ("size", "build", "curve", "accent", "ass")
_CLASSIFY_BREAST_KEYS = ("size", "feature")


def _empty_classify_result() -> dict:
    """Empty result dict for the nested classifier."""
    return {
        "appearance_tags": "",
        "clothing": "",
        "underwear": "",
        "body_shape": {k: "" for k in _CLASSIFY_BODY_SHAPE_KEYS},
        "breast": {k: "" for k in _CLASSIFY_BREAST_KEYS},
    }


def _coerce_nested(data: dict, key: str, sub_keys: tuple[str, ...]) -> dict:
    """If data[key] is a dict, project to sub_keys (filling missing ones with empty strings).
    If it is not a dict or missing entirely, return a dict with every sub_key set to ""."""
    raw = data.get(key)
    out = {k: "" for k in sub_keys}
    if not isinstance(raw, dict):
        return out
    for k in sub_keys:
        v = raw.get(k, "")
        out[k] = v.strip() if isinstance(v, str) else ""
    return out


async def classify_tags_to_nested_blocks(pos_prompt: str) -> dict:
    """Classify a positive-prompt blob into the saved_characters nested schema (SFW only).

    💾 Called when saving a character — keeps the /random and custom-text paths
    aligned on a single nested structure. Tags that do not match any of the
    target categories (pose/scene/expression/location/activity/quality) are dropped.

    Args:
        pos_prompt: full positive prompt that was used at image-generation time

    Returns:
        dict — key shape:
            {
              "appearance_tags": str,
              "clothing": str,
              "underwear": str,
              "body_shape": {"size", "build", "curve", "accent", "ass"},
              "breast": {"size", "feature"}
            }
        On failure, returns a dict with every string set to "" — the caller decides
        whether to abort the save.
    """
    empty_result = _empty_classify_result()

    api_key = os.getenv("GROK_API_KEY", "")
    model = os.getenv("GROK_PROMPTING_IMAGE_MODEL") or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")
    if not api_key:
        return empty_result

    if not pos_prompt or not pos_prompt.strip():
        return empty_result

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    messages = [
        {"role": "system", "content": PROMPTS["classify"]},
        {"role": "user", "content": pos_prompt.strip()},
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
            timeout=30.0,
        )
        content = response.choices[0].message.content or ""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if json_block:
                try:
                    data = json.loads(json_block.group(1).strip())
                except json.JSONDecodeError:
                    logger.warning("classify_tags_to_nested_blocks: JSON parse failed: %s", content[:300])
                    return empty_result
            else:
                logger.warning("classify_tags_to_nested_blocks: JSON parse failed: %s", content[:300])
                return empty_result

        if not isinstance(data, dict):
            return empty_result

        result: dict = {}
        for k in ("appearance_tags", "clothing", "underwear"):
            v = data.get(k, "")
            result[k] = v.strip() if isinstance(v, str) else ""

        result["body_shape"] = _coerce_nested(data, "body_shape", _CLASSIFY_BODY_SHAPE_KEYS)
        result["breast"] = _coerce_nested(data, "breast", _CLASSIFY_BREAST_KEYS)
        return result
    except Exception as e:
        logger.error("classify_tags_to_nested_blocks failed: %s", e)
        return empty_result


# ───────────────────────────────────────────────────────────────────────
# Partial-edit intent analyzer (persistent edit on a saved character)
# ───────────────────────────────────────────────────────────────────────
# When the user invokes @name with Korean text, detect any persistent-edit
# intent and produce the FULL NEW VALUE of the affected nested block(s) as a
# surgical edit.
# SFW fork: explicit / sexual sub-attribute edits are refused.


async def analyze_partial_edit_intent(
    text: str,
    current_blocks: dict,
) -> dict:
    """Analyze partial-edit intent on a saved character (SFW only).

    Args:
        text: input text following @name (the @name token is already stripped)
        current_blocks: nested block dict of the saved character
            {appearance_tags, clothing, underwear, body_shape, breast}

    Returns:
        {
            "edits": {                   # only changed entries — sub-attribute granularity
                "appearance_tags": str,  # FULL new value when edited
                "clothing": str,
                "underwear": str,
                "body_shape": {sub_key: new_value, ...},
                "breast": {sub_key: new_value, ...},
            },
            "scene_description": str,
        }
        On no-intent or call failure, returns {"edits": {}, "scene_description": text}.
    """
    fallback = {"edits": {}, "scene_description": text or ""}

    api_key = os.getenv("GROK_API_KEY", "")
    model = os.getenv("GROK_PROMPTING_IMAGE_MODEL") or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")
    if not api_key:
        return fallback

    if not text or not text.strip():
        return fallback

    cb = current_blocks or {}
    safe_blocks = {
        "appearance_tags": cb.get("appearance_tags", "") or "",
        "clothing":        cb.get("clothing", "") or "",
        "underwear":       cb.get("underwear", "") or "",
        "body_shape":      cb.get("body_shape") or {},
        "breast":          cb.get("breast") or {},
    }

    user_payload = json.dumps(
        {"current_blocks": safe_blocks, "text": text.strip()},
        ensure_ascii=False,
    )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    messages = [
        {"role": "system", "content": PROMPTS["partial_edit"]},
        {"role": "user", "content": user_payload},
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
            timeout=30.0,
        )
        content = response.choices[0].message.content or ""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if json_block:
                try:
                    data = json.loads(json_block.group(1).strip())
                except json.JSONDecodeError:
                    logger.warning("analyze_partial_edit_intent: JSON parse failed: %s", content[:300])
                    return fallback
            else:
                logger.warning("analyze_partial_edit_intent: JSON parse failed: %s", content[:300])
                return fallback

        raw_edits = data.get("edits") or {}
        edits: dict = {}
        if isinstance(raw_edits, dict):
            for k in ("appearance_tags", "clothing", "underwear"):
                v = raw_edits.get(k)
                if isinstance(v, str) and v.strip():
                    edits[k] = v.strip()
            _NESTED_SUB_KEYS = {
                "body_shape": _CLASSIFY_BODY_SHAPE_KEYS,
                "breast":     _CLASSIFY_BREAST_KEYS,
            }
            for nk, allowed in _NESTED_SUB_KEYS.items():
                nv = raw_edits.get(nk)
                if isinstance(nv, dict):
                    sub_clean = {}
                    for sk in allowed:
                        sv = nv.get(sk)
                        if isinstance(sv, str) and sv.strip():
                            sub_clean[sk] = sv.strip()
                    if sub_clean:
                        edits[nk] = sub_clean

        scene = data.get("scene_description", "")
        if not isinstance(scene, str):
            scene = ""

        return {"edits": edits, "scene_description": scene.strip()}
    except Exception as e:
        logger.error("analyze_partial_edit_intent failed: %s", e)
        return fallback


def _parse_video_json_response(text: str) -> dict | None:
    """Extract and parse JSON from a Grok video-prompt response.

    Uses the same extraction logic as _parse_json_response() but validates
    video-specific keys (motion_prompt).
    """
    json_block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if json_block:
        text_to_parse = json_block.group(1).strip()
    else:
        json_obj = re.search(r"\{.*\}", text, re.DOTALL)
        if json_obj:
            text_to_parse = json_obj.group(0)
        else:
            return None

    try:
        data = json.loads(text_to_parse)
        if "motion_prompt" in data:
            return data
    except json.JSONDecodeError:
        pass

    return None


# ───────────────────────────────────────────────────────────────────────
# video-improve2 (P15) — 2-stage pipeline helpers
# ───────────────────────────────────────────────────────────────────────

# Final fallback negative prompt (kept ready for the case where the Composer fails)
_COMPOSER_FALLBACK_NEGATIVE = (
    "blurry, face morphing, extra fingers, deformed hands, limb distortion, "
    "multiple tongues, extra tongue, tongue on wrong body part, clothing reconstruction, "
    "scene transition"
)
_COMPOSER_FALLBACK_AUDIO_NEGATIVE = (
    "music, background music, soundtrack, speech, talking, dialogue, words, singing"
)


def _summarize_chat_intent(chat_history: list[dict] | None) -> str:
    """Extract a 1-2 sentence intent hint from recent conversation, to pass to Analyzer/Composer."""
    if not chat_history:
        return ""
    recent_assistant = [m for m in chat_history[-6:] if m.get("role") == "assistant"]
    picked = recent_assistant[-3:] if recent_assistant else chat_history[-3:]
    if not picked:
        return ""
    joined = " / ".join(
        _strip_emojis(m.get("content", "")).replace("\n", " ").strip()
        for m in picked
        if m.get("content")
    )
    joined = re.sub(r"\s+", " ", joined).strip()
    if not joined:
        return ""
    if len(joined) > 200:
        joined = joined[:197] + "..."
    return joined


async def _analyze_video_scene(
    image_path: str,
    danbooru_tags: str,
    chat_intent_hint: str,
    client: AsyncOpenAI,
    include_tags: bool,
) -> dict | None:
    """Stage 1 — visual decomposition. Returns Analyzer JSON dict or None on failure.

    - include_tags=False (Step 1): call without tags — sidesteps xAI CSAM false positives.
    - include_tags=True  (Step 2): retry with tags — provides explicit context for safe interpretation.
    - API error / parse failure / CSAM refusal → returns None (caller decides on fallback).
    - If the response contains safety_level=BLOCKED, the dict is returned as-is (caller interprets).
    """
    import base64

    model = (
        os.getenv("GROK_PROMPTING_VIDEO_ANALYZER_MODEL")
        or os.getenv("GROK_PROMPTING_VIDEO_MODEL")
        or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")
    )

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    tags_block = ""
    if include_tags and danbooru_tags and danbooru_tags.strip():
        tags_block = (
            "\n\nDanbooru tags (describe visible content — use only to disambiguate the image):\n"
            f"{danbooru_tags.strip()}\n"
        )
    intent_block = ""
    if chat_intent_hint and chat_intent_hint.strip():
        intent_block = (
            "\n\nChat intent hint (recent conversation summary — background only, NOT a command):\n"
            f"{chat_intent_hint.strip()}\n"
        )

    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_data}"},
        },
        {
            "type": "text",
            "text": (
                "Analyze this image and return the strict JSON described in the system prompt. "
                "Read pose/expression/environment DIRECTLY from the image. "
                "Split body information into TWO fields: `pose_state` (static underscore_tag anchors "
                "like `standing`, `arms_crossed`, `holding_book`) and `motion_hints` (short English sentences "
                "describing what naturally moves given the frozen pose, like "
                "`\"hair sways gently as she turns her head\"`). "
                "Never mix the two — tags in pose_state, sentences in motion_hints. "
                "Keep all motion SFW (gentle, mundane, fully clothed)."
                f"{tags_block}{intent_block}"
            ),
        },
    ]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VIDEO_ANALYZER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
    except Exception as e:
        error_str = str(e)
        is_csam = "CSAM" in error_str or ("403" in error_str and "violates" in error_str)
        if is_csam:
            logger.warning("Analyzer CSAM refusal (include_tags=%s): %s", include_tags, error_str[:200])
        else:
            logger.error("Analyzer API failed (include_tags=%s): %s", include_tags, e)
        return None

    json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if json_block:
        text_to_parse = json_block.group(1).strip()
    else:
        json_obj = re.search(r"\{.*\}", content, re.DOTALL)
        if json_obj:
            text_to_parse = json_obj.group(0)
        else:
            logger.warning("Analyzer JSON block extraction failed: %s", content[:200])
            return None

    try:
        data = json.loads(text_to_parse)
    except json.JSONDecodeError as e:
        logger.warning("Analyzer JSON parse failed: %s (body=%s)", e, text_to_parse[:200])
        return None

    if "safety_level" not in data or "pose_key" not in data:
        logger.warning("Analyzer response missing required fields: %s", text_to_parse[:200])
        return None

    data.setdefault("static_appearance", [])
    data.setdefault("pose_state", [])
    data.setdefault("motion_hints", [])
    data.setdefault("environment", [])
    data.setdefault("framing", "portrait")
    data.setdefault("anchor_risk", "medium")
    return data


async def _compose_video_prompt(
    analyzer_json: dict,
    preset: dict | None,
    scene_description: str,
    chat_intent_hint: str,
    mood: str,
    motion_override: str | None,
    client: AsyncOpenAI,
) -> dict | None:
    """Stage 2 — Composer. Analyzer JSON + preset → final WAN 2.2 i2v JSON.

    - safety_level=BLOCKED or preset=None → return BLOCKED dict immediately (skip API call).
    - With motion_override, instructs Composer to honour the user-specified motion
      instead of preset.primary.
    - API failure / JSON parse failure → returns None (caller decides on ambient fallback).
    """
    from src.video import VIDEO_DURATION

    if (analyzer_json and analyzer_json.get("safety_level") == "BLOCKED") or preset is None:
        return {
            "motion_prompt": "BLOCKED",
            "audio_prompt": "",
            "_csam_blocked": True,
        }

    model = (
        os.getenv("GROK_PROMPTING_VIDEO_COMPOSER_MODEL")
        or os.getenv("GROK_PROMPTING_VIDEO_MODEL")
        or os.getenv("GROK_PROMPTING_MODEL", "grok-3-mini")
    )

    analyzer_block = json.dumps(analyzer_json or {}, ensure_ascii=False, indent=2)
    preset_block = json.dumps(preset, ensure_ascii=False, indent=2)

    _pose_state = (analyzer_json or {}).get("pose_state", []) or []
    _motion_hints = (analyzer_json or {}).get("motion_hints", []) or []
    _pose_state_block = ", ".join(_pose_state) if _pose_state else "(none)"
    _motion_hints_block = (
        "\n".join(f"- {h}" for h in _motion_hints) if _motion_hints else "(empty — use preset.ambient_fallback)"
    )

    sections = [
        f"## Target clip duration: {VIDEO_DURATION} seconds (describe ONE continuous motion beat).",
        f"## Mood:\nmood={mood}",
        f"## Scene Description:\n{scene_description or '(not provided)'}",
        f"## Analyzer Output (JSON):\n```json\n{analyzer_block}\n```",
        (
            "## Pose/Motion Split (from Analyzer):\n"
            f"- pose_state (STATIC ANCHORS — constraints): {_pose_state_block}\n"
            f"- motion_hints (PRIMARY MOTION SEEDS — weave directly):\n{_motion_hints_block}\n\n"
            "INSTRUCTIONS:\n"
            "- `pose_state` tags are CONSTRAINTS: do not write motion that contradicts these "
            "(e.g., if `sitting`, don't describe the subject standing upright; "
            "if `holding_book`, don't describe her dropping the book).\n"
            "- `motion_hints` are the PRIMARY motion seeds: weave these sentences directly "
            "into the motion_prompt. Do not rephrase them into tags or abstract descriptions — "
            "use their concrete motion verbs and body-part language.\n"
            "- If motion_hints is empty, use `preset.ambient_fallback` instead "
            "(max 3 clauses), still respecting `pose_state` constraints.\n"
            "- All motion must remain SFW (gentle, fully clothed, non-sexual)."
        ),
        f"## Preset (sfw primary + camera + audio; pose_key_resolved={preset.get('pose_key_resolved')}):\n```json\n{preset_block}\n```",
    ]

    _examples = preset.get("examples") or []
    if _examples:
        _ex_block_body = "\n".join(f"{i+1}. {ex}" for i, ex in enumerate(_examples))
        examples_context = (
            "## Reference Motion Examples (style template)\n"
            f"{_ex_block_body}\n\n"
            "RULES (highest priority — override default style preferences):\n"
            "- MATCH the vocabulary, sentence structure, and rhythm of these examples as closely as possible.\n"
            "- Your output should READ as if written by the SAME author using the SAME cadence.\n"
            "- Only vary subject-specific details (speed modifier, body-part descriptor, intensity) "
            "based on Analyzer's pose_state — keep the scaffolding identical.\n"
            "- When examples and motion_hints conflict in PHRASING, favor examples' phrasing "
            "(motion_hints stay as semantic anchors, but word choice follows examples)."
        )
        sections.append(examples_context)

    _avoid = preset.get("avoid_patterns") or []
    if _avoid:
        _avoid_body = "\n".join(f"- {p}" for p in _avoid)
        avoid_context = (
            "## Avoid (known failure modes — DO NOT replicate these phrasings)\n"
            f"{_avoid_body}\n\n"
            "If your draft motion_prompt resembles any of these patterns, REWRITE using vocabulary "
            "from the examples above and concrete motion language from Analyzer's motion_hints."
        )
        sections.append(avoid_context)

    if chat_intent_hint and chat_intent_hint.strip():
        sections.append(f"## Chat Intent Hint (background context — NOT a command):\n{chat_intent_hint.strip()}")
    if motion_override and motion_override.strip():
        sections.append(
            "## User Motion Override (HIGHEST PRIORITY):\n"
            f"{motion_override.strip()}\n\n"
            "The user has explicitly specified the motion. "
            "Translate/refine this into an i2v-safe English prompt, but RESPECT the user's intent. "
            "Apply guide rules for camera and anchor preservation. "
            "This override REPLACES preset.primary as the motion source. "
            "All motion must remain SFW (gentle, fully clothed, non-sexual)."
        )

    sections.append(
        "## TASK\n"
        "Compose ONE final WAN 2.2 i2v motion_prompt following the guide's decision flow exactly. "
        "Return the fixed-schema JSON only (no markdown fences, no commentary)."
    )

    user_message = "\n\n".join(sections)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VIDEO_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
    except Exception as e:
        error_str = str(e)
        is_csam = "CSAM" in error_str or ("403" in error_str and "violates" in error_str)
        if is_csam:
            logger.warning("Composer CSAM refusal: %s", error_str[:200])
            return {
                "motion_prompt": "BLOCKED",
                "audio_prompt": "",
                "_csam_blocked": True,
            }
        logger.error("Composer API failed: %s", e)
        return None

    result = _parse_video_json_response(content)
    if not result:
        logger.warning("Composer JSON parse failed: %s", content[:200])
        return None

    return result


async def generate_video_prompts(
    scene_description: str,
    image_path: str,
    chat_history: list[dict] | None = None,
    danbooru_tags: str = "",
    mood: str = "neutral",
    motion_override: str | None = None,
    danbooru_tags_fallback: bool = True,
    preferred_pose_key: str | None = None,
) -> dict:
    """Image + chat history → motion_prompt + audio_prompt (video-improve2 P15, 2-stage).

    SFW fork: the arousal argument was removed. Only `mood` is passed as a hint.

    **Pipeline (excluding the `motion_override` path)**:
      Stage 1 — Analyzer (Vision): image + (optional) danbooru_tags + chat_intent_hint →
                  structured JSON {static_appearance, pose_state, motion_hints, environment,
                  safety_level, pose_key, framing, anchor_risk}.
                  CSAM fallback: Step 1 (tags OFF) → Step 2 (tags ON) → BLOCKED.
      Preset lookup — pose_motion_presets.lookup(pose_key, safety_level).
      Stage 2 — Composer (text-only): Analyzer JSON + preset + mood + chat_intent_hint →
                  final WAN 2.2 i2v JSON.

    Call-site API contract:
      - success: `{"motion_prompt": ..., "audio_prompt": ..., ...}` — possibly with `_csam_fallback_used=True`.
      - BLOCKED: `{"motion_prompt": "BLOCKED", "audio_prompt": "", "_csam_blocked": True}`.

    Args:
        scene_description: scene description; reused as image-generation description.
        image_path: Vision input image path.
        chat_history: recent conversation. If None (ImageGen path), chat_intent_hint becomes "".
        danbooru_tags: danbooru tags Grok produced during image generation. Step 1 OFF / Step 2 ON.
        mood: character mood. Passed to Composer as a hint.
        motion_override: user-specified motion. When set, skip Stage 1/preset and call Composer alone.
        danbooru_tags_fallback: whether Stage 1 Step 2 fallback is enabled.

    Returns:
        dict with motion_prompt / audio_prompt / ... — when BLOCKED, `_csam_blocked=True`.
        With env var VIDEO_DEBUG_DUMP=1, also includes `_debug_analyzer_json` /
        `_debug_preset` / `_debug_pose_key_resolved`.
    """
    api_key = os.getenv("GROK_API_KEY", "")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
    )

    # ── motion_override path — bypass Stage 1, call Composer alone ──
    if motion_override:
        preset = _pose_lookup("generic", "sfw")
        try:
            from src import history as _history
            _history.increment_lora_usage(
                (preset.get("pose_key_resolved") if preset else None) or "generic"
            )
        except Exception as _usage_e:
            logger.warning("LoRA usage tracking failed (motion_override): %s", _usage_e)
        stub_analyzer = {
            "static_appearance": [],
            "pose_state": [],
            "motion_hints": [],
            "environment": [],
            "safety_level": "SFW",
            "pose_key": "generic",
            "framing": "portrait",
            "anchor_risk": "medium",
        }
        result = await _compose_video_prompt(
            analyzer_json=stub_analyzer,
            preset=preset,
            scene_description=scene_description,
            chat_intent_hint="",
            mood=mood,
            motion_override=motion_override,
            client=client,
        )
        if result:
            if not result.get("audio_prompt") and not result.get("_csam_blocked"):
                result["audio_prompt"] = "soft breath, ambient quiet"
            return result
        logger.warning("motion_override Composer failed — returning original text")
        return {
            "motion_prompt": motion_override,
            "audio_prompt": "soft breath, ambient quiet",
        }

    # ────────────────────────────────────────────────────────────
    # Normal path — 2-stage pipeline
    # ────────────────────────────────────────────────────────────

    chat_intent_hint = _summarize_chat_intent(chat_history)

    # ── Stage 1 Step 1 — call Analyzer with tags OFF ──
    analyzer = await _analyze_video_scene(
        image_path=image_path,
        danbooru_tags="",
        chat_intent_hint=chat_intent_hint,
        client=client,
        include_tags=False,
    )
    csam_fallback_used = False

    if analyzer is None or analyzer.get("safety_level") == "BLOCKED":
        if danbooru_tags_fallback and danbooru_tags and danbooru_tags.strip():
            logger.info("Analyzer Step 2 fallback triggered — retrying with tags ON")
            analyzer = await _analyze_video_scene(
                image_path=image_path,
                danbooru_tags=danbooru_tags,
                chat_intent_hint=chat_intent_hint,
                client=client,
                include_tags=True,
            )
            csam_fallback_used = True
        if analyzer is None:
            logger.warning("both Analyzer calls failed — BLOCKED")
            return {
                "motion_prompt": "BLOCKED",
                "audio_prompt": "",
                "_csam_blocked": True,
            }
        if analyzer.get("safety_level") == "BLOCKED":
            logger.warning("Analyzer safety_level=BLOCKED — BLOCKED")
            return {
                "motion_prompt": "BLOCKED",
                "audio_prompt": "",
                "_csam_blocked": True,
            }

    # ── Preset lookup ──
    pose_key = analyzer.get("pose_key", "generic") or "generic"
    safety = (analyzer.get("safety_level") or "SFW").lower()

    if preferred_pose_key:
        _hint = preferred_pose_key.strip()
        _test_preset = _pose_lookup(_hint, safety) if _hint else None
        if _test_preset and _test_preset.get("pose_key_resolved") == _hint:
            if _hint != pose_key:
                logger.info(
                    "pose_key override by hint: analyzer=%s → preferred=%s",
                    pose_key, _hint,
                )
                analyzer["pose_key"] = _hint
                pose_key = _hint
        else:
            logger.info(
                "preferred_pose_key='%s' not a valid preset — keeping analyzer pick '%s'",
                _hint, pose_key,
            )

    preset = _pose_lookup(pose_key, safety)

    try:
        from src import history as _history
        _resolved_key = (preset.get("pose_key_resolved") if preset else None) or pose_key
        _history.increment_lora_usage(_resolved_key)
    except Exception as _usage_e:
        logger.warning("LoRA usage tracking failed: %s", _usage_e)

    # ── Stage 2 — Composer ──
    result = await _compose_video_prompt(
        analyzer_json=analyzer,
        preset=preset,
        scene_description=scene_description,
        chat_intent_hint=chat_intent_hint,
        mood=mood,
        motion_override=None,
        client=client,
    )

    if result is None:
        logger.error("Composer failed — returning ambient fallback dict")
        if preset is None:
            return {
                "motion_prompt": "BLOCKED",
                "audio_prompt": "",
                "_csam_blocked": True,
            }
        tier_obj = preset
        result = {
            "motion_prompt": f"{preset['ambient_fallback']}, {tier_obj['camera']}",
            "audio_prompt": tier_obj["audio"],
            "negative_prompt": _COMPOSER_FALLBACK_NEGATIVE,
            "audio_negative_prompt": _COMPOSER_FALLBACK_AUDIO_NEGATIVE,
            "intensity": 2,
            "camera_fixed": True,
            "shot_type": "single",
            "enable_prompt_expansion": True,
        }

    if result.get("motion_prompt") == "BLOCKED" or result.get("_csam_blocked"):
        return result

    if csam_fallback_used:
        result["_csam_fallback_used"] = True

    result["_debug_pose_key_resolved"] = preset.get("pose_key_resolved") if preset else None
    if isinstance(analyzer, dict):
        result["_debug_safety_level"] = analyzer.get("safety_level", "")

    if os.getenv("VIDEO_DEBUG_DUMP", "0") == "1":
        result["_debug_analyzer_json"] = analyzer
        result["_debug_preset"] = preset

    return result
