import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.llm_client import fetch_models, stream_chat
from app.models import Conversation, Message
from app.schemas import ChatRequest

router = APIRouter()
logger = logging.getLogger(__name__)


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

        yield (
            f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id, 'model': selected_model})}\n\n"
        )

        try:
            async for item in stream_chat(messages, model=selected_model):
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
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
