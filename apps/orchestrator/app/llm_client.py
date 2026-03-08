import json
from typing import AsyncIterator

import httpx

from app.config import settings

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


def _base_url() -> str:
    """Return the normalised base URL (without trailing /v1)."""
    base = settings.vllm_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def _completions_url() -> str:
    """Build the chat completions URL, normalising a trailing /v1."""
    return f"{_base_url()}/v1/chat/completions"


async def fetch_models() -> list[dict]:
    """Fetch the model list from the OpenAI-compatible /v1/models endpoint."""
    url = f"{_base_url()}/v1/models"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.json()
    return [{"id": m["id"]} for m in body.get("data", [])]


async def stream_chat(
    messages: list[dict],
    model: str | None = None,
) -> AsyncIterator[str]:
    """Yield text tokens from the vLLM OpenAI-compatible streaming API."""
    payload = {
        "model": model or settings.vllm_model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": 2048,
    }
    url = _completions_url()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(
                        f"LLM API returned {exc.response.status_code} "
                        f"at {url} — check VLLM_MODEL_ID or API key"
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
            f"Cannot reach LLM endpoint at {url} — "
            f"is the service running?"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"LLM endpoint timed out ({url})"
        ) from exc
