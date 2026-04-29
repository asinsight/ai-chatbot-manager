"""Image-generator intent-classification router — runs on a local LLM.

Classifies free-text input into one of six intents and splits scene /
edit_clause from the prompt. Classification is light enough that a fast
local LLM (e.g. gemma) works fine and GPU usage stays minimal.

Caller is `imagegen_message` — it passes the free text that remains after
the @name parser and CHAR_NAME_MAP fast paths.

llm_queue API note:
    `LLMQueue.enqueue()` does not take a priority argument directly; it derives
    priority from `task_type` and `user_id` (`chat` → NORMAL, `summary` /
    `extract` → LOW). The router uses the same chat queue as character chat
    but its own calls are short and deterministic (max_tokens=200, JSON
    classification), so queue pressure stays low.
"""

import json
import logging
import re

from src.llm_queue import llm_queue

logger = logging.getLogger(__name__)

# The six intents this router classifies into
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
    """Classify free-text intent using a local LLM.

    Args:
        text: free text after the @name token has been stripped
        has_saved_char_ref: True if the user referenced a saved character via @name
        has_last_tags: True if a previous image is in the session (modify mode possible)
        user_id: used for queue routing (currently a single NORMAL priority)

    Returns:
        {intent: str, scene_description: str, edit_clause: str}
        On parse failure, falls back to RECALL if saved_char_ref, MODIFY if
        has_last_tags, else NEW.
    """
    text = (text or "").strip()

    # Fallback decision — used on LLM failure
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
        # Keep max_tokens small: only the JSON classification result is needed.
        response = await llm_queue.enqueue(
            messages=messages,
            user_id=user_id,
            task_type="chat",
            max_tokens=200,
        )
    except Exception as e:
        logger.error("intent router LLM call failed: %s", e)
        return fallback

    content = (response or "").strip()
    if not content:
        return fallback

    # JSON parsing — handle markdown code blocks
    json_block = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    raw = json_block.group(1).strip() if json_block else content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Extract only the substring from the first { to the last }
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("intent router JSON parse failed: %s", content[:200])
            return fallback
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning("intent router JSON parse failed: %s", content[:200])
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
