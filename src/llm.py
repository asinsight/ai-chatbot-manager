import os
import httpx


async def chat_completion(messages: list[dict], max_tokens: int = 250) -> str:
    """Open WebUI API로 채팅 완성 요청"""
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
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        import logging
        logging.getLogger(__name__).error("LLM HTTP 에러: status=%s body=%s", e.response.status_code, e.response.text[:500])
        return f"[오류] LLM 응답 실패: {e}"
    except Exception as e:
        return f"[오류] LLM 응답 실패: {e}"
