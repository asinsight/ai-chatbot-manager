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
    """Build EXTRACT_PROMPT at runtime (injects the canonical-key list dynamically)."""
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
    """Convert a messages list into a plain-text transcript."""
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
    """Common helper that invokes an LLM provider and returns the text response.

    Args:
        system_prompt: system prompt
        user_message: user message (e.g. the conversation transcript)
        provider: "local" (Open WebUI) or "grok"

    Returns:
        LLM response text. Propagates the underlying exception on failure.
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
        # local — go through the LLM queue (low priority)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await llm_queue.enqueue(messages, task_type="summary")


def _parse_json(text: str) -> dict | None:
    """Parse a JSON object out of an LLM response.

    Tries ```json ... ``` fenced blocks first, then a raw { ... } substring.
    """
    # Try to extract a ```json ... ``` fenced block first
    json_block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if json_block:
        text_to_parse = json_block.group(1).strip()
    else:
        # Fall back to extracting a raw JSON object directly
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
    """Summarize a conversation history.

    Args:
        messages: list of conversation messages [{"role": "user"/"assistant", "content": "..."}]
        provider: "local" (Open WebUI) or "grok". If None, reads the env var.

    Returns:
        English summary string. Returns the fallback message on failure.
    """
    if provider is None:
        provider = os.getenv("SUMMARY_PROVIDER", "local")

    if not messages:
        return FALLBACK_MESSAGE

    text = _format_messages(messages)

    try:
        if provider == "grok":
            logger.info("summarizing via Grok API (%d messages)", len(messages))
        else:
            logger.info("summarizing via Open WebUI API (%d messages)", len(messages))

        summary = await _call_provider(SUMMARY_PROMPT, text, provider)

        if not summary.strip():
            logger.warning("summary result is empty")
            return FALLBACK_MESSAGE

        logger.info("summary generated (%d chars)", len(summary))
        return summary.strip()

    except Exception as e:
        logger.error("summary generation failed (provider=%s): %s", provider, e)
        return FALLBACK_MESSAGE


async def extract_memory_and_profile(
    messages: list[dict],
    existing_summary: str = "",
    provider: str = None,
) -> dict:
    """Extract long-term memory (relationship/events) and user profile from a conversation.

    Args:
        messages: list of conversation messages [{"role": "user"/"assistant", "content": "..."}]
        existing_summary: previous summary (prepended as extra context if provided)
        provider: "local" (Open WebUI) or "grok". If None, reads the env var.

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

    # If a prior summary exists, prepend it as extra context
    if existing_summary:
        text = f"## Previous summary:\n{existing_summary}\n\n## Conversation:\n{text}"

    try:
        if provider == "grok":
            logger.info("extracting memory/profile via Grok API (%d messages)", len(messages))
        else:
            logger.info("extracting memory/profile via Open WebUI API (%d messages)", len(messages))

        raw_response = await _call_provider(_build_extract_prompt(), text, provider)

        if not raw_response.strip():
            logger.warning("memory/profile extract result is empty")
            return EXTRACT_FALLBACK.copy()

        parsed = _parse_json(raw_response)
        if parsed is None:
            logger.warning("memory/profile JSON parse failed: %s", raw_response[:200])
            return EXTRACT_FALLBACK.copy()

        # Validate expected keys and ensure defaults
        result = {
            "relationship": parsed.get("relationship", ""),
            "events": parsed.get("events", []),
            "user_info": parsed.get("user_info", {}),
        }

        # relationship must be a string
        if not isinstance(result["relationship"], str):
            result["relationship"] = ""

        # events must be a list
        if not isinstance(result["events"], list):
            result["events"] = []

        # user_info must be a dict
        if not isinstance(result["user_info"], dict):
            result["user_info"] = {}

        logger.info(
            "memory/profile extracted (relationship=%s, events=%d, user_info_keys=%d)",
            bool(result["relationship"]),
            len(result["events"]),
            len(result["user_info"]),
        )
        return result

    except Exception as e:
        logger.error("memory/profile extraction failed (provider=%s): %s", provider, e)
        return EXTRACT_FALLBACK.copy()
