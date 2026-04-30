"""Prompt-injection input filter — regex scan + Prompt Guard API.

Stage 1: block obvious patterns with regexes and strip control signals
Stage 2: detect bypass attempts via the Prompt Guard API
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

# Block patterns (Korean + English)
BLOCK_PATTERNS = [
    # System-prompt extraction attempts
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"시스템\s*프롬프트"),
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"이전\s*지시\s*(사항)?\s*(무시|잊어)", re.IGNORECASE),
    re.compile(r"(show|reveal|print|출력|보여).{0,20}(prompt|지시|instructions?|규칙|설정)", re.IGNORECASE),
    re.compile(r"너의\s*(규칙|지시|설정|프롬프트)"),
    re.compile(r"what\s+(are|is)\s+your\s+(instructions|rules|prompt)", re.IGNORECASE),
    # Role-break attempts
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"너는\s*(이제|지금)\s*(AI|인공지능)"),
    re.compile(r"developer\s*mode", re.IGNORECASE),
    re.compile(r"관리자\s*모드"),
    re.compile(r"act\s+as\s+an?\s+(unrestricted|unfiltered)", re.IGNORECASE),
    re.compile(r"캐릭터\s*(그만|중단|해제|벗어나)"),
    re.compile(r"\bDAN\b"),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(previous|above|system|all)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|previous|your)", re.IGNORECASE),
    re.compile(r"new\s+(role|instruction|personality):", re.IGNORECASE),
    # Block minor / underage content
    re.compile(r"\b(loli|shota|child|children|kid|toddler|infant|underage|minor)\b", re.IGNORECASE),
    re.compile(r"(아동|어린이|미성년|초등학생|중학생|고등학생|소아|유아)", re.IGNORECASE),
    re.compile(r"(여자\s*아이|남자\s*아이|여자애|남자애|꼬마|소녀|소년)", re.IGNORECASE),
    re.compile(r"\b([0-9]|1[0-8])\s*살", re.IGNORECASE),  # block ages 0-18 (allow 19+)
    re.compile(r"\b([0-9]|1[0-7])\s*y\.?o\.?\b", re.IGNORECASE),  # block 0-17 y.o. (allow 18+)
    re.compile(r"\b(young\s*girl|young\s*boy|little\s*girl|little\s*boy)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*y\.?o\.?\s*(girl|boy)\b", re.IGNORECASE),
]

# Signal strip patterns (remove without blocking)
STRIP_PATTERNS = [
    re.compile(r"\[SEND_IMAGE[:\s].*?\]", re.IGNORECASE),
    re.compile(r"\[MOOD:\w+\]", re.IGNORECASE),
    re.compile(r"\[OUTFIT:\s*.+?\]", re.IGNORECASE),
    re.compile(r"\[SEARCH:\s*.+?\]", re.IGNORECASE),
    re.compile(r"\(IMAGE_SENT:\s*.+?\)", re.IGNORECASE),
    # Gemma 4 control tokens
    re.compile(r"<\|turn>"),
    re.compile(r"<turn\|>"),
    re.compile(r"<\|channel>"),
    re.compile(r"<channel\|>"),
    re.compile(r"<\|think\|>"),
    re.compile(r"<\|tool>"),
    re.compile(r"<tool\|>"),
    re.compile(r"<\|tool_call>"),
    re.compile(r"<tool_call\|>"),
    re.compile(r"<\|tool_response>"),
    re.compile(r"<tool_response\|>"),
]

# Prompt Guard API URL — empty by default; the input filter skips the
# remote call when unset, leaving regex-only filtering active.
PROMPT_GUARD_URL = os.getenv("PROMPT_GUARD_URL", "").rstrip("/")
PROMPT_GUARD_THRESHOLD = float(os.getenv("PROMPT_GUARD_THRESHOLD", "0.8"))


# Patterns that detect image requests for someone other than the character
_NON_CHARACTER_IMAGE_PATTERNS = [
    re.compile(r"다른\s*(남자|여자|사람|애)\s*.*(사진|셀카|보여|보내)", re.IGNORECASE),
    re.compile(r"(남자|여자|강아지|고양이|동물|풍경|음식)\s*(사진|셀카)\s*(보여|보내|찍어|만들어)", re.IGNORECASE),
    re.compile(r"너\s*말고.*(사진|셀카|보여|보내)", re.IGNORECASE),
    re.compile(r"(다른|딴)\s*(캐릭터|인물).*(사진|셀카|보여|보내)", re.IGNORECASE),
]


def is_non_character_image_request(text: str) -> bool:
    """Detect image requests aimed at someone other than the active character."""
    for pattern in _NON_CHARACTER_IMAGE_PATTERNS:
        if pattern.search(text):
            logger.info("[security] non-character image request detected: %s", text[:100])
            return True
    return False


# Trigger keywords for Prompt Guard — call the API only when one of these appears.
# Korean keywords are intentional and must match user input verbatim.
_SUSPICIOUS_KEYWORDS = [
    "역할", "캐릭터", "AI", "인공지능", "시스템", "프롬프트", "설정",
    "규칙", "지시", "모드", "prompt", "system", "instruction", "ignore",
    "override", "developer", "admin", "jailbreak", "DAN", "pretend",
    "act as", "role", "character", "rule",
]


def _has_suspicious_keyword(text: str) -> bool:
    """Return True if the input contains a keyword that warrants a Prompt Guard call."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _SUSPICIOUS_KEYWORDS)


def check_regex(text: str) -> tuple[bool, str]:
    """Detect obvious prompt-injection attempts via regex patterns.

    Returns:
        (blocked, matched_pattern)
    """
    for pattern in BLOCK_PATTERNS:
        if pattern.search(text):
            logger.warning("[security] regex block: pattern=%s user_text=%s", pattern.pattern, text[:100])
            return True, pattern.pattern
    return False, ""


def strip_signals(text: str) -> str:
    """Strip internal control signals and control tokens from user input."""
    for pattern in STRIP_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


async def check_prompt_guard(text: str) -> tuple[bool, float]:
    """Use the Prompt Guard API to decide whether the input is an injection attempt.

    Returns:
        (blocked, score). When PROMPT_GUARD_URL is unset the call is skipped
        and the input is treated as not blocked (regex filtering still runs).
    """
    if not PROMPT_GUARD_URL:
        return False, 0.0
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{PROMPT_GUARD_URL}/check",
                json={"text": text, "threshold": PROMPT_GUARD_THRESHOLD},
            )
            resp.raise_for_status()
            data = resp.json()
            if data["blocked"]:
                logger.warning("[security] Prompt Guard block: score=%.4f text=%s", data["score"], text[:100])
            return data["blocked"], data["score"]
    except Exception as e:
        logger.error("[security] Prompt Guard API failure: %s", e)
        return False, 0.0  # On API failure, fail open (favor availability)


async def filter_input(text: str) -> tuple[str, bool, str]:
    """Filter a user input through all stages.

    Returns:
        (sanitized_text, blocked, reason)
        - if blocked is True the caller should stop handling the message
        - if blocked is False the caller should proceed with sanitized_text
    """
    # Stage 1: strip control signals
    sanitized = strip_signals(text)

    # Stage 2: regex block
    regex_blocked, pattern = check_regex(sanitized)
    if regex_blocked:
        return sanitized, True, "regex"

    # Stage 3: Prompt Guard API — only when a suspicious keyword is present
    if _has_suspicious_keyword(sanitized):
        guard_blocked, score = await check_prompt_guard(sanitized)
        if guard_blocked:
            return sanitized, True, "prompt_guard"

    return sanitized, False, ""
