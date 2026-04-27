"""프롬프트 인젝션 입력 필터 — 정규식 스캔 + Prompt Guard API.

1단계: 정규식으로 명확한 패턴 차단 + 시그널 strip
2단계: Prompt Guard API로 우회 시도 탐지
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

# 차단 패턴 (한글 + 영어)
BLOCK_PATTERNS = [
    # 시스템 프롬프트 탈취
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"시스템\s*프롬프트"),
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"이전\s*지시\s*(사항)?\s*(무시|잊어)", re.IGNORECASE),
    re.compile(r"(show|reveal|print|출력|보여).{0,20}(prompt|지시|instructions?|규칙|설정)", re.IGNORECASE),
    re.compile(r"너의\s*(규칙|지시|설정|프롬프트)"),
    re.compile(r"what\s+(are|is)\s+your\s+(instructions|rules|prompt)", re.IGNORECASE),
    # 역할 이탈
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
    # 아동/미성년 콘텐츠 차단
    re.compile(r"\b(loli|shota|child|children|kid|toddler|infant|underage|minor)\b", re.IGNORECASE),
    re.compile(r"(아동|어린이|미성년|초등학생|중학생|고등학생|소아|유아)", re.IGNORECASE),
    re.compile(r"(여자\s*아이|남자\s*아이|여자애|남자애|꼬마|소녀|소년)", re.IGNORECASE),
    re.compile(r"\b([0-9]|1[0-8])\s*살", re.IGNORECASE),  # 0~18살 차단 (19+는 허용)
    re.compile(r"\b([0-9]|1[0-7])\s*y\.?o\.?\b", re.IGNORECASE),  # 0~17yo 차단 (18+는 허용)
    re.compile(r"\b(young\s*girl|young\s*boy|little\s*girl|little\s*boy)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*y\.?o\.?\s*(girl|boy)\b", re.IGNORECASE),
]

# 시그널 strip 패턴 (차단하지 않고 제거만)
STRIP_PATTERNS = [
    re.compile(r"\[SEND_IMAGE[:\s].*?\]", re.IGNORECASE),
    re.compile(r"\[MOOD:\w+\]", re.IGNORECASE),
    re.compile(r"\[OUTFIT:\s*.+?\]", re.IGNORECASE),
    re.compile(r"\[SEARCH:\s*.+?\]", re.IGNORECASE),
    re.compile(r"\(IMAGE_SENT:\s*.+?\)", re.IGNORECASE),
    # Gemma 4 컨트롤 토큰
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

# Prompt Guard API URL
PROMPT_GUARD_URL = os.getenv("PROMPT_GUARD_URL", "http://192.168.86.250:8081")
PROMPT_GUARD_THRESHOLD = float(os.getenv("PROMPT_GUARD_THRESHOLD", "0.8"))


# 캐릭터 외 이미지 요청 감지 패턴
_NON_CHARACTER_IMAGE_PATTERNS = [
    re.compile(r"다른\s*(남자|여자|사람|애)\s*.*(사진|셀카|보여|보내)", re.IGNORECASE),
    re.compile(r"(남자|여자|강아지|고양이|동물|풍경|음식)\s*(사진|셀카)\s*(보여|보내|찍어|만들어)", re.IGNORECASE),
    re.compile(r"너\s*말고.*(사진|셀카|보여|보내)", re.IGNORECASE),
    re.compile(r"(다른|딴)\s*(캐릭터|인물).*(사진|셀카|보여|보내)", re.IGNORECASE),
]


def is_non_character_image_request(text: str) -> bool:
    """캐릭터 본인이 아닌 이미지 요청인지 감지한다."""
    for pattern in _NON_CHARACTER_IMAGE_PATTERNS:
        if pattern.search(text):
            logger.info("[security] 캐릭터 외 이미지 요청 감지: %s", text[:100])
            return True
    return False


# Prompt Guard 호출 트리거 키워드 — 이 키워드가 있을 때만 Prompt Guard API 호출
_SUSPICIOUS_KEYWORDS = [
    "역할", "캐릭터", "AI", "인공지능", "시스템", "프롬프트", "설정",
    "규칙", "지시", "모드", "prompt", "system", "instruction", "ignore",
    "override", "developer", "admin", "jailbreak", "DAN", "pretend",
    "act as", "role", "character", "rule",
]


def _has_suspicious_keyword(text: str) -> bool:
    """Prompt Guard 호출이 필요한 의심 키워드가 있는지 확인."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _SUSPICIOUS_KEYWORDS)


def check_regex(text: str) -> tuple[bool, str]:
    """정규식 패턴으로 명확한 인젝션 시도를 감지한다.

    Returns:
        (blocked, matched_pattern)
    """
    for pattern in BLOCK_PATTERNS:
        if pattern.search(text):
            logger.warning("[security] 정규식 차단: pattern=%s user_text=%s", pattern.pattern, text[:100])
            return True, pattern.pattern
    return False, ""


def strip_signals(text: str) -> str:
    """유저 입력에서 내부 제어 시그널과 컨트롤 토큰을 제거한다."""
    for pattern in STRIP_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


async def check_prompt_guard(text: str) -> tuple[bool, float]:
    """Prompt Guard API로 인젝션 여부를 판단한다.

    Returns:
        (blocked, score)
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{PROMPT_GUARD_URL}/check",
                json={"text": text, "threshold": PROMPT_GUARD_THRESHOLD},
            )
            resp.raise_for_status()
            data = resp.json()
            if data["blocked"]:
                logger.warning("[security] Prompt Guard 차단: score=%.4f text=%s", data["score"], text[:100])
            return data["blocked"], data["score"]
    except Exception as e:
        logger.error("[security] Prompt Guard API 실패: %s", e)
        return False, 0.0  # API 실패 시 통과 (가용성 우선)


async def filter_input(text: str) -> tuple[str, bool, str]:
    """유저 입력을 필터링한다.

    Returns:
        (sanitized_text, blocked, reason)
        - blocked=True이면 메시지 처리 중단
        - blocked=False이면 sanitized_text로 진행
    """
    # 1단계: 시그널 strip
    sanitized = strip_signals(text)

    # 2단계: 정규식 차단
    regex_blocked, pattern = check_regex(sanitized)
    if regex_blocked:
        return sanitized, True, "regex"

    # 3단계: Prompt Guard API — 의심 키워드가 있을 때만 호출
    if _has_suspicious_keyword(sanitized):
        guard_blocked, score = await check_prompt_guard(sanitized)
        if guard_blocked:
            return sanitized, True, "prompt_guard"

    return sanitized, False, ""
