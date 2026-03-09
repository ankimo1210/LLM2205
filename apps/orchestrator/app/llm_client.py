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


async def chat_json(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 256,
) -> str:
    """Single-shot (non-streaming) chat completion. Returns the full text."""
    payload = {
        "model": model or settings.vllm_model_id,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    url = _completions_url()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        body = resp.json()
    return body["choices"][0]["message"]["content"]


async def stream_chat(
    messages: list[dict],
    model: str | None = None,
) -> AsyncIterator[str | dict]:
    """Yield text tokens from the vLLM OpenAI-compatible streaming API.

    Text tokens are yielded as plain str.
    When the stream ends, a dict ``{"usage": {...}}`` is yielded if the
    backend returned usage information in the final chunk.
    """
    payload = {
        "model": model or settings.vllm_model_id,
        "messages": messages,
        "stream": True,
        "max_tokens": 2048,
        "stream_options": {"include_usage": True},
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

                usage_data: dict | None = None

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

                    # Capture usage from final chunk
                    if chunk.get("usage"):
                        usage_data = chunk["usage"]

                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content") or ""
                        if delta:
                            yield delta

                if usage_data:
                    yield {"usage": usage_data}
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Cannot reach LLM endpoint at {url} — "
            f"is the service running?"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"LLM endpoint timed out ({url})"
        ) from exc
