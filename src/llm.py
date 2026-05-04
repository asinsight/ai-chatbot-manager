import os
import re
import httpx


# Strip thought / channel / harmony special tokens that some LLMs leak into output.
# Covers <|channel|>...<|message|>, <think>...</think>, <thought>...</thought>,
# and any bare <|...|> Harmony-style markers that survive the chat template.
_THOUGHT_BLOCK = re.compile(
    r"<\|channel\|>.*?(?:<\|message\|>|<\|return\|>|<\|end\|>|$)",
    re.DOTALL | re.IGNORECASE,
)
_THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_THOUGHT_BLOCK2 = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)
_HARMONY_TOKEN = re.compile(r"<\|[^|<>]{0,40}\|>")


def _sanitize_llm_output(text: str) -> str:
    if not text:
        return text
    text = _THOUGHT_BLOCK.sub("", text)
    text = _THINK_BLOCK.sub("", text)
    text = _THOUGHT_BLOCK2.sub("", text)
    text = _HARMONY_TOKEN.sub("", text)
    return text.strip()


async def chat_completion(messages: list[dict], max_tokens: int = 250) -> str:
    """Request a chat completion through the Open WebUI API."""
    url = os.getenv("OPENWEBUI_URL", "").rstrip("/")
    api_key = os.getenv("OPENWEBUI_API_KEY", "")
    model = os.getenv("MODEL_NAME", "")

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            api_path = os.getenv("LLM_API_PATH", "/api/chat/completions")
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = await client.post(
                f"{url}{api_path}",
                headers=headers,
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
            )
            resp.raise_for_status()
            data = resp.json()
            return _sanitize_llm_output(data["choices"][0]["message"]["content"])
    except httpx.HTTPStatusError as e:
        import logging
        logging.getLogger(__name__).error("LLM HTTP error: status=%s body=%s", e.response.status_code, e.response.text[:500])
        return f"[error] LLM response failed: {e}"
    except Exception as e:
        return f"[error] LLM response failed: {e}"
