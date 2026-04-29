"""Grok Web Search client.

Module that fetches web-search results for the Telegram chatbot.
Grok Responses API (web_search tool) → prompt-injection pipeline.
In-memory rate limiting (global monthly + per-user daily) + LRU cache.
Disabled (returns empty string) if the API key is unset or GROK_SEARCH_ENABLED=0.

SFW fork: the system prompt explicitly tells Grok to filter results to SFW only.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import httpx

from src import history
from src.token_counter import count_tokens

logger = logging.getLogger(__name__)

# ── Env-var configuration ────────────────────────────────────
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_MODEL_NAME = os.getenv("GROK_MODEL_NAME", "grok-3-mini")
GROK_SEARCH_MODEL = os.getenv("GROK_SEARCH_MODEL", GROK_MODEL_NAME)
GROK_SEARCH_ENABLED = os.getenv("GROK_SEARCH_ENABLED", "1") == "1"
GROK_SEARCH_MONTHLY_LIMIT = int(os.getenv("GROK_SEARCH_MONTHLY_LIMIT", "500"))
GROK_SEARCH_PER_USER_DAILY = int(os.getenv("GROK_SEARCH_PER_USER_DAILY", "10"))

# ── API configuration ────────────────────────────────────────
_API_URL = "https://api.x.ai/v1/responses"
_TIMEOUT = 60  # safety margin for web_search response (15s wasn't enough — chat search timeouts)
_LOCATION_TIMEOUT = 60
_MAX_QUERY_LEN = 200
_MAX_TOKENS = 400
_CACHE_TTL = 30 * 60  # 30 minutes

# ── System prompt ────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a real-time information assistant for a Korean chatbot. "
    "Search the web and provide a concise answer in Korean (2-3 sentences). "
    "Focus on the most relevant and current facts. "
    "Do NOT include URLs. Just state the key facts naturally. "
    "Filter out adult/NSFW content from search results. Return only family-friendly, SFW results. "
    "Keep your answer under 150 words."
)

# ── In-memory counters + cache ───────────────────────────────
# Global monthly usage: {"2026-04": 123, ...}
_monthly_count: dict[str, int] = {}

# Per-user daily usage: {(user_id, "2026-04-18"): 5, ...}
_daily_user_count: dict[tuple[int, str], int] = {}

# Search cache: {normalized_query: {"result": str, "timestamp": float}}
_search_cache: dict[str, dict] = {}


def _now_month() -> str:
    """Return the current month key (YYYY-MM)."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _now_date() -> str:
    """Return the current date key (YYYY-MM-DD)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _normalize_query(query: str) -> str:
    """Normalize for cache key: strip + lowercase."""
    return query.strip().lower()


def _check_cache(normalized: str) -> str | None:
    """Look up a cached result. Evicts and returns None if expired."""
    entry = _search_cache.get(normalized)
    if entry is None:
        return None
    if time.time() - entry["timestamp"] > _CACHE_TTL:
        del _search_cache[normalized]
        return None
    return entry["result"]


def _save_cache(normalized: str, result: str) -> None:
    """Store a result in the cache."""
    _search_cache[normalized] = {
        "result": result,
        "timestamp": time.time(),
    }


def _check_global_limit() -> bool:
    """Check the global monthly limit. Returns False if exceeded."""
    month = _now_month()
    count = _monthly_count.get(month, 0)
    if count >= GROK_SEARCH_MONTHLY_LIMIT:
        logger.warning("Grok Search monthly limit exceeded: %d/%d (%s)", count, GROK_SEARCH_MONTHLY_LIMIT, month)
        return False
    return True


def _check_user_limit(user_id: int) -> bool:
    """Check the per-user daily limit. Returns False if exceeded."""
    if user_id == 0:
        return True
    date = _now_date()
    key = (user_id, date)
    count = _daily_user_count.get(key, 0)
    if count >= GROK_SEARCH_PER_USER_DAILY:
        logger.warning("Grok Search per-user daily limit exceeded: user=%d count=%d/%d (%s)", user_id, count, GROK_SEARCH_PER_USER_DAILY, date)
        return False
    return True


def _increment_counters(user_id: int) -> None:
    """Increment counters after a successful API call."""
    month = _now_month()
    _monthly_count[month] = _monthly_count.get(month, 0) + 1

    if user_id != 0:
        date = _now_date()
        key = (user_id, date)
        _daily_user_count[key] = _daily_user_count.get(key, 0) + 1


def _extract_text_from_response(data: dict) -> str:
    """Extract the text payload from a Grok Responses API response."""
    output = data.get("output", [])
    for item in output:
        if item.get("type") == "message":
            content = item.get("content", [])
            for block in content:
                if block.get("type") == "output_text":
                    return block.get("text", "").strip()
    return ""


async def search(query: str, user_id: int = 0) -> str:
    """Run a web search via the Grok Responses API (web_search) and return a summary.

    Args:
        query: search query
        user_id: Telegram user id (used for rate limiting; 0 disables per-user limit)

    Returns:
        Search result summary (Korean, within ~400 tokens), or an empty string.
    """
    # Master switch check
    if not GROK_SEARCH_ENABLED or not GROK_API_KEY:
        return ""

    # Normalize the query
    query = query.strip()
    if not query:
        return ""
    query = query[:_MAX_QUERY_LEN]
    normalized = _normalize_query(query)

    # 1. Cache check (cache hits are not counted against the rate limit)
    cached = _check_cache(normalized)
    if cached is not None:
        logger.debug("Grok Search cache hit: %s", normalized[:50])
        return cached

    # 2. Global monthly limit
    if not _check_global_limit():
        return ""

    # 3. Per-user daily limit
    if not _check_user_limit(user_id):
        return ""

    # 4. Grok Responses API call (web_search tool)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROK_SEARCH_MODEL,
                    "tools": [{"type": "web_search"}],
                    "input": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.3,
                    "max_output_tokens": 300,
                },
            )

            if resp.status_code != 200:
                logger.error("Grok Search HTTP error: status=%d body=%s", resp.status_code, resp.text[:500])
                return ""

            try:
                data = resp.json()
            except Exception:
                logger.error("Grok Search JSON parse failed: body=%s", resp.text[:500])
                return ""

    except Exception as e:
        logger.error("Grok Search API call failed: %s", e)
        return ""

    # Extract the result text
    result = _extract_text_from_response(data)
    if not result:
        logger.debug("Grok Search no result: %s", query[:50])
        return ""

    # Increment counters on API success
    _increment_counters(user_id)
    logger.info("Grok Search success: query='%s' → %d-char response", query[:50], len(result))

    # Enforce the token budget
    if count_tokens(result) > _MAX_TOKENS:
        # Truncate sentence-by-sentence
        sentences = result.split(". ")
        while sentences and count_tokens(". ".join(sentences)) > _MAX_TOKENS:
            sentences.pop()
        result = ". ".join(sentences)

    # Save to cache
    _save_cache(normalized, result)

    return result


# ── Location Research (P10 Phase 2) ──────────────────────────

_LOCATION_SYSTEM_PROMPT = (
    "You are a research assistant for a SFW Korean roleplay chatbot. "
    "Research the given location and return strictly a JSON object with two fields: "
    '"description" (2-3 Korean sentences describing atmosphere, props, and mood for a roleplay scene) and '
    '"danbooru_background" (15-20 comma-separated English danbooru tags for image-generation background). '
    "The danbooru_background MUST include: "
    "(a) specific furniture/props with material or style (e.g., queen_bed not just bed, oak_nightstand, red_velvet_curtain), "
    "(b) explicit color palette (wall color, floor color, accent color), "
    "(c) time-of-day indicator ONLY (nighttime, daytime, evening, dawn — time words only; NOT brightness descriptors), "
    "(d) materials/textures (wooden_floor, marble_countertop, brick_wall). "
    "These details should make the scene VISUALLY CONSISTENT across regenerations — the same location should look like the same room. "
    "CRITICAL — ALL LIGHTING/LAMP/AMBIENT TAGS ARE STRICTLY FORBIDDEN (NO EXCEPTIONS): "
    "never include any tag containing `lighting`, ending with `_light` or `_lights`, "
    "or containing `glow`, `ambient`, `ambience`, `ambiance`, `shadow`, `shadows`, `dappled`, `fluorescent`, `atmosphere`, `steamy`, "
    "`lamp`, `lamps`, `spotlight`, `spotlights`, "
    "or explicit lighting descriptors like `sunlight`, `natural_light`, `soft_light`, `warm_lighting`, `dim_lighting`, `bright_lighting`, `mood_lighting`, `candlelight`, `moonlight`, `balanced_color_grading`, `warm_orange_lighting`, `neon_lights`, `colorful_lights`, `stage_lights`, `studio_lighting`, `studio_lights`, `softbox`, `reflector`, `disco_ball`, `strobe_lights`, `blue_lighting`. "
    "Physical lamps (brass_bedside_lamp, floor_lamp, pendant_lights, etc.) are ALSO FORBIDDEN — do NOT include any lamp/light object either. "
    "Avoid NSFW-only locations (love hotels, motels in adult contexts). Prefer wholesome locations (cafés, parks, bookshops, etc.). "
    "Do NOT include any prose outside the JSON. No markdown fences, no explanation."
)


def _humanize_location_key(location_key: str) -> str:
    """Convert a snake_case location key into a search-query string."""
    return location_key.strip().replace("_", " ").lower()


def _extract_location_json(text: str) -> dict | None:
    """Extract JSON from a Grok response (supports ```json ... ``` fences and bare objects)."""
    if not text:
        return None
    # ```json ... ``` or ``` ... ``` block
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
    else:
        obj = re.search(r"\{.*\}", text, re.DOTALL)
        if not obj:
            return None
        candidate = obj.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    desc = (data.get("description") or "").strip()
    bg = (data.get("danbooru_background") or "").strip()
    if not desc or not bg:
        return None
    return {"description": desc, "danbooru_background": bg}


async def search_location(location_key: str) -> dict | None:
    """Return the description + danbooru_background for a location key.

    Flow:
      1. Look up history.get_location_context() in the (global) cache first.
      2. On cache miss, call the Grok Responses API (web_search tool).
      3. Upsert the result into history.save_location_context().

    Per-user daily limit is not enforced (this is a global cache and is
    therefore unrelated to a user's budget). Only the global monthly limit applies.

    Returns:
        {"description": str, "danbooru_background": str} or None
    """
    if not location_key:
        return None
    key = history._normalize_location_key(location_key)
    if not key:
        return None

    # 1. Cache check — global cache shared across all users
    cached = history.get_location_context(key)
    if cached:
        logger.debug("Location cache hit: %s", key)
        return cached

    # Master switch check
    if not GROK_SEARCH_ENABLED or not GROK_API_KEY:
        logger.info("Location research skipped (disabled or no API key): %s", key)
        return None

    # Only the global monthly limit (per-user daily limit is skipped — this is a global cache)
    if not _check_global_limit():
        logger.warning("Location research skipped (monthly global limit): %s", key)
        return None

    humanized = _humanize_location_key(key)
    user_query = (
        f"Research the typical atmosphere, props, and visual details of the location: "
        f"\"{humanized}\".\n"
        "Return JSON only with this schema: "
        '{"description": "2-3 Korean sentences describing atmosphere/props/mood for a roleplay scene", '
        '"danbooru_background": "15-20 comma-separated English danbooru tags for image generation background, '
        'including specific furniture with materials, color palette, time-of-day, and textures for visual consistency. '
        'DO NOT include any lighting/atmosphere/color-grading tags — see the FORBIDDEN list in system prompt."}'
    )

    logger.info("Location research start: key=%s (humanized='%s')", key, humanized)

    try:
        async with httpx.AsyncClient(timeout=_LOCATION_TIMEOUT) as client:
            resp = await client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROK_MODEL_NAME,
                    "tools": [{"type": "web_search"}],
                    "input": [
                        {"role": "system", "content": _LOCATION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_query},
                    ],
                    "temperature": 0.3,
                    "max_output_tokens": 500,
                },
            )
            if resp.status_code != 200:
                logger.error("Location research HTTP error: status=%d body=%s", resp.status_code, resp.text[:300])
                return None
            try:
                data = resp.json()
            except Exception:
                logger.error("Location research JSON decode failed: body=%s", resp.text[:300])
                return None
    except Exception as e:
        logger.error("Location research API call failed (%s): %s: %s", key, type(e).__name__, e)
        return None

    raw_text = _extract_text_from_response(data)
    parsed = _extract_location_json(raw_text)
    if not parsed:
        logger.warning("Location research parse failed: key=%s raw=%s", key, raw_text[:200])
        return None

    # Increment the monthly counter (we do not increment per-user daily — this is a global cache)
    month = _now_month()
    _monthly_count[month] = _monthly_count.get(month, 0) + 1

    # Save to DB
    try:
        history.save_location_context(key, parsed["description"], parsed["danbooru_background"])
    except Exception as e:
        logger.error("Location save failed (%s): %s", key, e)
        # Return the result even if the save failed

    logger.info("Location research success: key=%s desc_len=%d bg=%s",
                key, len(parsed["description"]), parsed["danbooru_background"][:80])
    return parsed
