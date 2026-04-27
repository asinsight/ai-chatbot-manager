import json
import logging
import os
import re

from openai import AsyncOpenAI

from src.llm_queue import llm_queue

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "Summarize the following conversation in 3-5 sentences in English.\n"
    "Focus on: emotional changes, important events, relationship progress, and key decisions.\n"
    "Do not include greetings or filler. Be concise and factual."
)

def _build_extract_prompt() -> str:
    """EXTRACT_PROMPT를 런타임에 빌드한다 (canonical key 목록 동적 주입)."""
    from src.profile_keys import get_canonical_keys
    canonical = ", ".join(get_canonical_keys())
    return f"""\
Analyze the following conversation and extract structured information.
Respond with ONLY a JSON object in this exact format:
{{
    "relationship": "Describe the current relationship state between the user and character in 1-2 sentences. If no relationship info, use empty string.",
    "events": ["List important events that happened (max 3). Each event is one short sentence. If none, use empty array."],
    "user_info": {{
        "key": "value"
    }}
}}

For user_info, use ONLY these canonical keys: {canonical}.
Do NOT invent new keys. If information doesn't fit an existing key, pick the CLOSEST match (e.g., favorite food → "food", hometown → "location").
Values should be concise strings.
Only include keys where information is explicitly stated or strongly implied. Do not guess or fabricate.
If no user info found, use empty object {{}}.\
"""

FALLBACK_MESSAGE = "(summary unavailable)"

EXTRACT_FALLBACK = {"relationship": "", "events": [], "user_info": {}}


def _format_messages(messages: list[dict]) -> str:
    """메시지 리스트를 텍스트로 변환"""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


async def _call_provider(
    system_prompt: str,
    user_message: str,
    provider: str,
) -> str:
    """LLM 프로바이더를 호출하여 텍스트 응답을 반환하는 공통 헬퍼.

    Args:
        system_prompt: 시스템 프롬프트
        user_message: 유저 메시지 (대화 내용 등)
        provider: "local" (Open WebUI) 또는 "grok"

    Returns:
        LLM 응답 텍스트. 실패 시 예외를 그대로 전파한다.
    """
    if provider == "grok":
        api_key = os.getenv("GROK_API_KEY", "")
        model = os.getenv("GROK_MODEL_NAME", "grok-3-mini")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""
    else:
        # local — LLM 큐 경유 (낮은 우선순위)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await llm_queue.enqueue(messages, task_type="summary")


def _parse_json(text: str) -> dict | None:
    """LLM 응답에서 JSON 객체를 추출하여 파싱한다.

    ```json ... ``` 블록 → raw { ... } 순서로 시도.
    """
    # ```json ... ``` 블록 추출 시도
    json_block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if json_block:
        text_to_parse = json_block.group(1).strip()
    else:
        # JSON 객체 직접 추출 시도
        json_obj = re.search(r"\{.*\}", text, re.DOTALL)
        if json_obj:
            text_to_parse = json_obj.group(0)
        else:
            return None

    try:
        return json.loads(text_to_parse)
    except json.JSONDecodeError:
        return None


async def summarize_messages(
    messages: list[dict],
    provider: str | None = None,
) -> str:
    """대화 히스토리를 요약한다.

    Args:
        messages: 대화 메시지 리스트 [{"role": "user"/"assistant", "content": "..."}]
        provider: "local" (Open WebUI) 또는 "grok". None이면 환경변수 참조.

    Returns:
        영어 요약 문자열. 실패 시 fallback 메시지.
    """
    if provider is None:
        provider = os.getenv("SUMMARY_PROVIDER", "local")

    if not messages:
        return FALLBACK_MESSAGE

    text = _format_messages(messages)

    try:
        if provider == "grok":
            logger.info("Grok API로 요약 생성 중 (%d개 메시지)", len(messages))
        else:
            logger.info("Open WebUI API로 요약 생성 중 (%d개 메시지)", len(messages))

        summary = await _call_provider(SUMMARY_PROMPT, text, provider)

        if not summary.strip():
            logger.warning("요약 결과가 비어 있음")
            return FALLBACK_MESSAGE

        logger.info("요약 생성 완료 (%d자)", len(summary))
        return summary.strip()

    except Exception as e:
        logger.error("요약 생성 실패 (provider=%s): %s", provider, e)
        return FALLBACK_MESSAGE


async def extract_memory_and_profile(
    messages: list[dict],
    existing_summary: str = "",
    provider: str = None,
) -> dict:
    """대화에서 장기 기억(관계/이벤트)과 유저 프로필 정보를 추출한다.

    Args:
        messages: 대화 메시지 리스트 [{"role": "user"/"assistant", "content": "..."}]
        existing_summary: 기존 요약 (있으면 컨텍스트로 앞에 추가)
        provider: "local" (Open WebUI) 또는 "grok". None이면 환경변수 참조.

    Returns:
        {
            "relationship": "current relationship state..." or "",
            "events": ["event1", "event2", ...],
            "user_info": {"name": "...", "nickname": "...", "likes": "...", ...}
        }
    """
    if provider is None:
        provider = os.getenv("SUMMARY_PROVIDER", "local")

    if not messages:
        return EXTRACT_FALLBACK.copy()

    text = _format_messages(messages)

    # 기존 요약이 있으면 컨텍스트로 앞에 추가
    if existing_summary:
        text = f"## Previous summary:\n{existing_summary}\n\n## Conversation:\n{text}"

    try:
        if provider == "grok":
            logger.info("Grok API로 메모리/프로필 추출 중 (%d개 메시지)", len(messages))
        else:
            logger.info("Open WebUI API로 메모리/프로필 추출 중 (%d개 메시지)", len(messages))

        raw_response = await _call_provider(_build_extract_prompt(), text, provider)

        if not raw_response.strip():
            logger.warning("메모리/프로필 추출 결과가 비어 있음")
            return EXTRACT_FALLBACK.copy()

        parsed = _parse_json(raw_response)
        if parsed is None:
            logger.warning("메모리/프로필 JSON 파싱 실패: %s", raw_response[:200])
            return EXTRACT_FALLBACK.copy()

        # 기대하는 키 검증 및 기본값 보장
        result = {
            "relationship": parsed.get("relationship", ""),
            "events": parsed.get("events", []),
            "user_info": parsed.get("user_info", {}),
        }

        # relationship은 문자열이어야 함
        if not isinstance(result["relationship"], str):
            result["relationship"] = ""

        # events는 리스트여야 함
        if not isinstance(result["events"], list):
            result["events"] = []

        # user_info는 딕셔너리여야 함
        if not isinstance(result["user_info"], dict):
            result["user_info"] = {}

        logger.info(
            "메모리/프로필 추출 완료 (relationship=%s, events=%d, user_info_keys=%d)",
            bool(result["relationship"]),
            len(result["events"]),
            len(result["user_info"]),
        )
        return result

    except Exception as e:
        logger.error("메모리/프로필 추출 실패 (provider=%s): %s", provider, e)
        return EXTRACT_FALLBACK.copy()
