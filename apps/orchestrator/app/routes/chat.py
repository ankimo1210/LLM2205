import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.llm_client import chat_json, fetch_models, stream_chat
from app.models import Conversation, Message
from app.schemas import ChatRequest
from app.web_search import search_web

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Tool-call decision prompt ────────────────────────────────────────────────
_TOOL_DECISION_PROMPT = """\
You have access to a web_search tool.
Given the user's message, decide whether you need to search the web to answer.

Rules:
- If the question requires up-to-date information, recent events, specific facts \
you are unsure about, or the user explicitly asks to search, respond with a search action.
- If you can answer confidently from your training data, respond with an answer action.

Respond with ONLY a JSON object (no markdown, no explanation):
- To search: {"action":"web_search","query":"<search query>"}
- To answer directly: {"action":"answer"}
"""


def _parse_tool_decision(text: str) -> dict:
    """Best-effort extraction of the JSON decision from LLM output."""
    # Try direct parse first
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find a JSON object in the text
    match = re.search(r"\{[^}]+\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Default: no search needed
    return {"action": "answer"}


@router.get("/models")
async def list_models():
    """Proxy the OpenAI-compatible /v1/models and return a simplified list."""
    try:
        data = await fetch_models()
    except Exception as exc:
        logger.warning("Failed to fetch model list: %s", exc)
        return {
            "data": [],
            "default_model": settings.vllm_model_id,
            "error": "Cannot reach model listing endpoint",
        }
    return {"data": data, "default_model": settings.vllm_model_id}


@router.post("/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    # ── Resolve or create conversation ───────────────────────────────────
    if request.conversation_id:
        conv = db.get(Conversation, request.conversation_id)
        if conv is None:
            conv = Conversation(
                id=request.conversation_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(conv)
            db.commit()
    else:
        conv = Conversation(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc))
        db.add(conv)
        db.commit()

    # ── Build message list from history ──────────────────────────────────
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
        .all()
    )
    messages: list[dict] = [{"role": "system", "content": settings.get_system_prompt()}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.message})

    conversation_id = conv.id
    user_message = request.message
    selected_model = request.model or settings.vllm_model_id

    # ── SSE generator ────────────────────────────────────────────────────
    async def generate():
        full_response: list[str] = []
        usage_data: dict | None = None
        sources: list[dict] = []

        yield (
            f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id, 'model': selected_model})}\n\n"
        )

        # ── Step 1: Decide if web search is needed ───────────────────────
        search_results: list[dict] = []
        final_messages = list(messages)  # copy for potential augmentation

        try:
            decision_messages = [
                {"role": "system", "content": _TOOL_DECISION_PROMPT},
                {"role": "user", "content": user_message},
            ]
            raw_decision = await chat_json(
                decision_messages, model=selected_model, max_tokens=128
            )
            decision = _parse_tool_decision(raw_decision)
            logger.info("Tool decision: %s", decision)
        except Exception as exc:
            logger.warning("Tool decision call failed, skipping search: %s", exc)
            decision = {"action": "answer"}

        # ── Step 2: Execute web search if requested ──────────────────────
        if decision.get("action") == "web_search" and decision.get("query"):
            search_query = decision["query"]
            yield f"data: {json.dumps({'type': 'tool', 'tool': 'web_search', 'query': search_query})}\n\n"

            try:
                search_results = await search_web(search_query, top_k=5)
            except Exception as exc:
                logger.warning("Web search failed: %s", exc)
                search_results = []

            if search_results:
                sources = [
                    {"title": r["title"], "url": r["url"]} for r in search_results
                ]
                yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

                # Augment the conversation with search context
                context_parts = []
                for i, r in enumerate(search_results, 1):
                    context_parts.append(
                        f"[{i}] {r['title']}\n    URL: {r['url']}\n    {r['snippet']}"
                    )
                search_context = "\n\n".join(context_parts)
                augmented_system = (
                    f"{settings.get_system_prompt()}\n\n"
                    f"The following web search results are provided for reference. "
                    f"Use them to answer the user's question. "
                    f"Cite sources using [1], [2], etc. when referencing information.\n\n"
                    f"--- Web Search Results ---\n{search_context}\n--- End Results ---"
                )
                final_messages[0] = {"role": "system", "content": augmented_system}

        # ── Step 3: Stream the final answer ──────────────────────────────
        try:
            async for item in stream_chat(final_messages, model=selected_model):
                if isinstance(item, dict) and "usage" in item:
                    usage_data = item["usage"]
                else:
                    full_response.append(item)
                    yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        # Extract usage numbers
        prompt_tokens = (usage_data or {}).get("prompt_tokens")
        completion_tokens = (usage_data or {}).get("completion_tokens")
        total_tokens = (usage_data or {}).get("total_tokens")

        # Save both turns after streaming completes (use a fresh session)
        assistant_content = "".join(full_response)
        with SessionLocal() as save_db:
            save_db.add_all(
                [
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role="user",
                        content=user_message,
                        created_at=datetime.now(timezone.utc),
                    ),
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role="assistant",
                        content=assistant_content,
                        created_at=datetime.now(timezone.utc),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    ),
                ]
            )
            save_db.commit()

        done_payload: dict = {"type": "done"}
        if usage_data:
            done_payload["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        if sources:
            done_payload["sources"] = sources
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
