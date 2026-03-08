import json
from typing import AsyncIterator

import httpx

from app.config import settings

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Yield text tokens from the vLLM OpenAI-compatible streaming API."""
    payload = {
        "model": settings.vllm_model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": 2048,
    }
    url = f"{settings.vllm_base_url}/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(
                        f"LLM API returned {exc.response.status_code} — "
                        f"check VLLM_MODEL_ID or API key"
                    ) from exc

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk["choices"][0]["delta"].get("content") or ""
                    if delta:
                        yield delta
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach LLM endpoint at {settings.vllm_base_url} — "
            f"is the service running?"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"LLM endpoint timed out ({settings.vllm_base_url})"
        ) from exc
