"""Grok Web Search 클라이언트.

텔레그램 챗봇에서 웹 검색 결과를 가져오기 위한 모듈.
Grok Responses API (web_search tool) → 프롬프트 주입 파이프라인.
인메모리 rate limiting (글로벌 월간 + 유저별 일일) + LRU 캐시.
API 키 미설정 또는 GROK_SEARCH_ENABLED=0 이면 비활성화 (빈 문자열 반환).

SFW fork: 검색 결과는 SFW로 필터링하도록 시스템 프롬프트가 명시한다.
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

# ── 환경변수 설정 ──────────────────────────────────────────────
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_MODEL_NAME = os.getenv("GROK_MODEL_NAME", "grok-3-mini")
GROK_SEARCH_MODEL = os.getenv("GROK_SEARCH_MODEL", GROK_MODEL_NAME)
GROK_SEARCH_ENABLED = os.getenv("GROK_SEARCH_ENABLED", "1") == "1"
GROK_SEARCH_MONTHLY_LIMIT = int(os.getenv("GROK_SEARCH_MONTHLY_LIMIT", "500"))
GROK_SEARCH_PER_USER_DAILY = int(os.getenv("GROK_SEARCH_PER_USER_DAILY", "10"))

# ── API 설정 ──────────────────────────────────────────────────
_API_URL = "https://api.x.ai/v1/responses"
_TIMEOUT = 60  # web_search tool 응답 시간 안전마진 (15초로는 부족 — chat 검색 timeout 발생)
_LOCATION_TIMEOUT = 60
_MAX_QUERY_LEN = 200
_MAX_TOKENS = 400
_CACHE_TTL = 30 * 60  # 30분

# ── 시스템 프롬프트 ──────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a real-time information assistant for a Korean chatbot. "
    "Search the web and provide a concise answer in Korean (2-3 sentences). "
    "Focus on the most relevant and current facts. "
    "Do NOT include URLs. Just state the key facts naturally. "
    "Filter out adult/NSFW content from search results. Return only family-friendly, SFW results. "
    "Keep your answer under 150 words."
)

# ── 인메모리 카운터 + 캐시 ────────────────────────────────────
# 글로벌 월간 사용량: {"2026-04": 123, ...}
_monthly_count: dict[str, int] = {}

# 유저별 일일 사용량: {(user_id, "2026-04-18"): 5, ...}
_daily_user_count: dict[tuple[int, str], int] = {}

# 검색 캐시: {normalized_query: {"result": str, "timestamp": float}}
_search_cache: dict[str, dict] = {}


def _now_month() -> str:
    """현재 월 키 반환 (YYYY-MM)."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _now_date() -> str:
    """현재 날짜 키 반환 (YYYY-MM-DD)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _normalize_query(query: str) -> str:
    """캐시 키용 정규화: 공백 제거 + 소문자."""
    return query.strip().lower()


def _check_cache(normalized: str) -> str | None:
    """캐시에서 결과 조회. 만료 시 삭제 후 None 반환."""
    entry = _search_cache.get(normalized)
    if entry is None:
        return None
    if time.time() - entry["timestamp"] > _CACHE_TTL:
        del _search_cache[normalized]
        return None
    return entry["result"]


def _save_cache(normalized: str, result: str) -> None:
    """결과를 캐시에 저장."""
    _search_cache[normalized] = {
        "result": result,
        "timestamp": time.time(),
    }


def _check_global_limit() -> bool:
    """글로벌 월간 한도 확인. 초과 시 False."""
    month = _now_month()
    count = _monthly_count.get(month, 0)
    if count >= GROK_SEARCH_MONTHLY_LIMIT:
        logger.warning("Grok Search 월간 한도 초과: %d/%d (%s)", count, GROK_SEARCH_MONTHLY_LIMIT, month)
        return False
    return True


def _check_user_limit(user_id: int) -> bool:
    """유저별 일일 한도 확인. 초과 시 False."""
    if user_id == 0:
        return True
    date = _now_date()
    key = (user_id, date)
    count = _daily_user_count.get(key, 0)
    if count >= GROK_SEARCH_PER_USER_DAILY:
        logger.warning("Grok Search 유저 일일 한도 초과: user=%d count=%d/%d (%s)", user_id, count, GROK_SEARCH_PER_USER_DAILY, date)
        return False
    return True


def _increment_counters(user_id: int) -> None:
    """API 호출 성공 후 카운터 증가."""
    month = _now_month()
    _monthly_count[month] = _monthly_count.get(month, 0) + 1

    if user_id != 0:
        date = _now_date()
        key = (user_id, date)
        _daily_user_count[key] = _daily_user_count.get(key, 0) + 1


def _extract_text_from_response(data: dict) -> str:
    """Grok Responses API 응답에서 텍스트 추출."""
    output = data.get("output", [])
    for item in output:
        if item.get("type") == "message":
            content = item.get("content", [])
            for block in content:
                if block.get("type") == "output_text":
                    return block.get("text", "").strip()
    return ""


async def search(query: str, user_id: int = 0) -> str:
    """Grok Responses API (web_search)로 웹 검색 후 요약 반환.

    Args:
        query: 검색 쿼리
        user_id: 텔레그램 유저 ID (rate limiting 용, 0이면 유저 제한 무시)

    Returns:
        검색 결과 요약 (한국어, ~400 토큰 이내) 또는 빈 문자열
    """
    # 마스터 스위치 확인
    if not GROK_SEARCH_ENABLED or not GROK_API_KEY:
        return ""

    # 쿼리 정리
    query = query.strip()
    if not query:
        return ""
    query = query[:_MAX_QUERY_LEN]
    normalized = _normalize_query(query)

    # 1. 캐시 확인 (캐시 히트는 rate limit에 포함 안됨)
    cached = _check_cache(normalized)
    if cached is not None:
        logger.debug("Grok Search 캐시 히트: %s", normalized[:50])
        return cached

    # 2. 글로벌 월간 한도 확인
    if not _check_global_limit():
        return ""

    # 3. 유저 일일 한도 확인
    if not _check_user_limit(user_id):
        return ""

    # 4. Grok Responses API 호출 (web_search tool)
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
                logger.error("Grok Search HTTP 에러: status=%d body=%s", resp.status_code, resp.text[:500])
                return ""

            try:
                data = resp.json()
            except Exception:
                logger.error("Grok Search JSON 파싱 실패: body=%s", resp.text[:500])
                return ""

    except Exception as e:
        logger.error("Grok Search API 호출 실패: %s", e)
        return ""

    # 결과 텍스트 추출
    result = _extract_text_from_response(data)
    if not result:
        logger.debug("Grok Search 결과 없음: %s", query[:50])
        return ""

    # 카운터 증가 (API 성공 시)
    _increment_counters(user_id)
    logger.info("Grok Search 성공: query='%s' → %d자 응답", query[:50], len(result))

    # 토큰 예산 확인
    if count_tokens(result) > _MAX_TOKENS:
        # 문장 단위로 자르기
        sentences = result.split(". ")
        while sentences and count_tokens(". ".join(sentences)) > _MAX_TOKENS:
            sentences.pop()
        result = ". ".join(sentences)

    # 캐시 저장
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
    """snake_case 로케이션 키를 검색 쿼리용 문자열로 변환."""
    return location_key.strip().replace("_", " ").lower()


def _extract_location_json(text: str) -> dict | None:
    """Grok 응답에서 JSON 추출 (```json ... ``` 펜스 및 bare 객체 지원)."""
    if not text:
        return None
    # ```json ... ``` 또는 ``` ... ``` 블록
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
    """로케이션 키에 대한 description + danbooru_background을 반환.

    플로우:
      1. history.get_location_context() 캐시 우선 조회 (글로벌 캐시).
      2. 캐시 미스 시 Grok Responses API (web_search tool) 호출.
      3. 결과를 history.save_location_context()로 upsert.

    유저별 일일 한도는 체크하지 않음 (글로벌 캐시 — 유저 예산과 무관).
    글로벌 월간 한도만 체크한다.

    Returns:
        {"description": str, "danbooru_background": str} 또는 None
    """
    if not location_key:
        return None
    key = history._normalize_location_key(location_key)
    if not key:
        return None

    # 1. 캐시 확인 — 모든 유저가 공유하는 글로벌 캐시
    cached = history.get_location_context(key)
    if cached:
        logger.debug("Location cache hit: %s", key)
        return cached

    # 마스터 스위치 확인
    if not GROK_SEARCH_ENABLED or not GROK_API_KEY:
        logger.info("Location research skipped (disabled or no API key): %s", key)
        return None

    # 글로벌 월간 한도만 체크 (유저별 일일 한도는 건너뜀 — 글로벌 캐시)
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

    # 월간 카운터 증가 (유저 per-day는 증가시키지 않음 — 글로벌 캐시)
    month = _now_month()
    _monthly_count[month] = _monthly_count.get(month, 0) + 1

    # DB 저장
    try:
        history.save_location_context(key, parsed["description"], parsed["danbooru_background"])
    except Exception as e:
        logger.error("Location save failed (%s): %s", key, e)
        # 저장 실패해도 결과는 반환

    logger.info("Location research success: key=%s desc_len=%d bg=%s",
                key, len(parsed["description"]), parsed["danbooru_background"][:80])
    return parsed
