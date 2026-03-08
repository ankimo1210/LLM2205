import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.llm_client import stream_chat
from app.models import Conversation, Message
from app.schemas import ChatRequest

router = APIRouter()


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
    messages: list[dict] = [{"role": "system", "content": settings.system_prompt}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.message})

    conversation_id = conv.id
    user_message = request.message

    # ── SSE generator ────────────────────────────────────────────────────
    async def generate():
        full_response: list[str] = []

        yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id})}\n\n"

        try:
            async for token in stream_chat(messages):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

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
                    ),
                ]
            )
            save_db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
