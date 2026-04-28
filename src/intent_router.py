"""이미지 제네레이터 의도 분류 라우터 — Local LLM 사용.

자유 텍스트 입력을 6개 intent로 분류하고 scene/edit_clause를 분리한다.
단순 분류 작업이라 빠른 local LLM(gemma 등)이 적합하며 GPU 사용 미미.

호출자는 `imagegen_message` — @name 파서 / CHAR_NAME_MAP 등 fast-path 이후의
자유 텍스트를 라우터에 전달한다.

llm_queue API 노트:
    `LLMQueue.enqueue()`는 priority 인자를 직접 받지 않고 `task_type`과 `user_id`로
    내부 매핑한다 (`chat`이면 NORMAL, `summary`/`extract`이면 LOW).
    라우터는 캐릭터 대화와 동일한 chat 큐를 쓰지만, 라우터 호출 자체는 짧고
    deterministic (max_tokens=200, JSON 분류) 이라 큐 부하에 영향이 적다.
"""

import json
import logging
import re

from src.llm_queue import llm_queue

logger = logging.getLogger(__name__)

# 라우터가 분류하는 6개 intent
INTENTS = ("NEW", "MODIFY", "EDIT_SAVED", "RECALL", "SCENE", "RESET")

ROUTER_SYSTEM_PROMPT = """\
You are an intent classifier for a Korean image-generator chatbot. Output strict JSON.

CONTEXT inputs (in user message):
- text: Korean text typed by the user (already with @name token stripped if any)
- has_saved_char_ref: true if user referenced a saved character via @name
- has_last_tags: true if a previously-generated image is in the session (modify-mode possible)

CLASSIFY into exactly ONE of these intents:

1. EDIT_SAVED — has_saved_char_ref=true AND text contains modification intent for the saved character (e.g. "의상 바꿔", "머리 갈색으로", "엉덩이 더 크게", "요가팬츠 의상").
   Output: {intent: "EDIT_SAVED", scene_description: "(non-edit part)", edit_clause: "(edit part)"}

2. RECALL — has_saved_char_ref=true AND text is just a scene/pose request without modification (e.g. "카페에서", "해변에서 책 읽기", "").
   Output: {intent: "RECALL", scene_description: "<text as-is>"}

3. RESET — explicit session reset command (e.g. "새캐릭터", "새 캐릭터", "리셋", "reset"). Often accompanies new character description.
   Output: {intent: "RESET", scene_description: "(remaining new-character description after stripping reset keyword)"}

4. NEW — has_saved_char_ref=false AND (has_last_tags=false OR user clearly wants a fresh character with new identity description like "긴머리 오피스룩").
   Output: {intent: "NEW", scene_description: "<text as-is>"}

5. MODIFY — has_saved_char_ref=false AND has_last_tags=true AND user wants to riff/modify the previous image (e.g. "다른 표정으로", "더 밝게", "이번엔 좀 다르게", scene change to existing identity).
   Output: {intent: "MODIFY", scene_description: "<text as-is>"}

6. SCENE — fallback for has_saved_char_ref=false AND has_last_tags=false AND text is just a scene description.
   Output: {intent: "SCENE", scene_description: "<text as-is>"}

DECISION GUIDELINES:
- has_saved_char_ref=true → EDIT_SAVED or RECALL only.
- has_saved_char_ref=false AND text contains "새캐릭터" / "새 캐릭터" / "리셋" / "reset" → RESET.
- has_saved_char_ref=false AND has_last_tags=false → NEW or SCENE (effectively the same downstream — pick NEW for short character description, SCENE for pure scene).
- has_saved_char_ref=false AND has_last_tags=true → MODIFY (default unless explicit RESET).
- When user provides explicit identity description ("긴머리 오피스룩", "검은머리 학생") with last_tags=true and no reset keyword → still MODIFY (it can replace identity within modify mode); prefer NEW only when reset signal is clear.

Edge cases:
- empty text + has_saved_char_ref=true → RECALL with scene=""
- "@h1 의상" (just edit noun, no scene) → EDIT_SAVED, edit_clause="의상", scene=""
- "리셋 긴머리 오피스" → RESET, scene_description="긴머리 오피스"

OUTPUT JSON FORMAT (strict):
{
  "intent": "EDIT_SAVED" | "RECALL" | "NEW" | "MODIFY" | "SCENE" | "RESET",
  "scene_description": "...",
  "edit_clause": "..."         // only for EDIT_SAVED, otherwise empty string ""
}

EXAMPLES:

Input: {"text": "카페에서 책 읽기", "has_saved_char_ref": true, "has_last_tags": false}
Output: {"intent": "RECALL", "scene_description": "카페에서 책 읽기", "edit_clause": ""}

Input: {"text": "의상 검은 정장으로 카페에서", "has_saved_char_ref": true, "has_last_tags": false}
Output: {"intent": "EDIT_SAVED", "scene_description": "카페에서", "edit_clause": "의상 검은 정장으로"}

Input: {"text": "엉덩이 더 작게", "has_saved_char_ref": true, "has_last_tags": false}
Output: {"intent": "EDIT_SAVED", "scene_description": "", "edit_clause": "엉덩이 더 작게"}

Input: {"text": "긴머리 오피스 새캐릭터", "has_saved_char_ref": false, "has_last_tags": true}
Output: {"intent": "RESET", "scene_description": "긴머리 오피스", "edit_clause": ""}

Input: {"text": "다른 표정으로", "has_saved_char_ref": false, "has_last_tags": true}
Output: {"intent": "MODIFY", "scene_description": "다른 표정으로", "edit_clause": ""}

Input: {"text": "긴머리 오피스", "has_saved_char_ref": false, "has_last_tags": false}
Output: {"intent": "NEW", "scene_description": "긴머리 오피스", "edit_clause": ""}

Input: {"text": "해변", "has_saved_char_ref": false, "has_last_tags": true}
Output: {"intent": "MODIFY", "scene_description": "해변", "edit_clause": ""}

Input: {"text": "", "has_saved_char_ref": true, "has_last_tags": false}
Output: {"intent": "RECALL", "scene_description": "", "edit_clause": ""}

OUTPUT JSON ONLY. No explanation.
"""


async def analyze_input_intent(
    text: str,
    has_saved_char_ref: bool,
    has_last_tags: bool,
    user_id: int = 0,
) -> dict:
    """Local LLM으로 자유 텍스트 의도 분류.

    Args:
        text: @name 토큰 strip 후의 자유 텍스트
        has_saved_char_ref: @name으로 저장 캐릭터를 참조했는지
        has_last_tags: 이전 이미지가 세션에 있는지 (modify mode 가능 여부)
        user_id: 큐 큐잉용 (현재 NORMAL 단일 우선순위)

    Returns:
        {intent: str, scene_description: str, edit_clause: str}
        파싱 실패 시 fallback (saved_char_ref면 RECALL, has_last_tags면 MODIFY, 아니면 NEW).
    """
    text = (text or "").strip()

    # Fallback 결정 — LLM 실패 시 사용
    if has_saved_char_ref:
        fallback_intent = "RECALL"
    elif has_last_tags:
        fallback_intent = "MODIFY"
    else:
        fallback_intent = "NEW"
    fallback = {
        "intent": fallback_intent,
        "scene_description": text,
        "edit_clause": "",
    }

    user_msg = json.dumps(
        {
            "text": text,
            "has_saved_char_ref": has_saved_char_ref,
            "has_last_tags": has_last_tags,
        },
        ensure_ascii=False,
    )

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    try:
        # task_type="chat" — NORMAL priority.
        # max_tokens 작게: JSON 분류 결과만 받으면 됨.
        response = await llm_queue.enqueue(
            messages=messages,
            user_id=user_id,
            task_type="chat",
            max_tokens=200,
        )
    except Exception as e:
        logger.error("intent router LLM 호출 실패: %s", e)
        return fallback

    content = (response or "").strip()
    if not content:
        return fallback

    # JSON 파싱 — 마크다운 코드 블록 처리
    json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    raw = json_block.group(1).strip() if json_block else content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 첫 { ~ 마지막 } 구간만 추출
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("intent router JSON 파싱 실패: %s", content[:200])
            return fallback
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning("intent router JSON 파싱 실패: %s", content[:200])
            return fallback

    intent = data.get("intent", "")
    if intent not in INTENTS:
        logger.warning("intent router unknown intent=%r — fallback", intent)
        return fallback

    return {
        "intent": intent,
        "scene_description": (data.get("scene_description") or "").strip(),
        "edit_clause": (data.get("edit_clause") or "").strip(),
    }
