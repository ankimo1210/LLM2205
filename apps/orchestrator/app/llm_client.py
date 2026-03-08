import json
from typing import AsyncIterator

import httpx

from app.config import settings


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Yield text tokens from the vLLM OpenAI-compatible streaming API."""
    payload = {
        "model": settings.vllm_model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)) as client:
        async with client.stream(
            "POST",
            f"{settings.vllm_base_url}/v1/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()

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
