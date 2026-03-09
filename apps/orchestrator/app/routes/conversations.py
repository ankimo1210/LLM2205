from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Conversation, Message
from app.schemas import ConversationDetail, ConversationOut, UsageOut

router = APIRouter()


def _usage_subquery(db: Session):
    """Return a subquery that sums token counts per conversation."""
    return (
        db.query(
            Message.conversation_id,
            func.coalesce(func.sum(Message.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(Message.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(Message.total_tokens), 0).label("total_tokens"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )


def _build_usage(row) -> UsageOut | None:
    """Build UsageOut from a joined row, or None if all zeros."""
    pt = row.prompt_tokens if hasattr(row, "prompt_tokens") else 0
    ct = row.completion_tokens if hasattr(row, "completion_tokens") else 0
    tt = row.total_tokens if hasattr(row, "total_tokens") else 0
    if pt == 0 and ct == 0 and tt == 0:
        return None
    return UsageOut(prompt_tokens=pt, completion_tokens=ct, total_tokens=tt)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    usage_sq = _usage_subquery(db)
    rows = (
        db.query(
            Conversation,
            usage_sq.c.prompt_tokens,
            usage_sq.c.completion_tokens,
            usage_sq.c.total_tokens,
        )
        .outerjoin(usage_sq, Conversation.id == usage_sq.c.conversation_id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    result = []
    for conv, pt, ct, tt in rows:
        pt, ct, tt = pt or 0, ct or 0, tt or 0
        usage = UsageOut(prompt_tokens=pt, completion_tokens=ct, total_tokens=tt) if (pt or ct or tt) else None
        result.append(ConversationOut(
            id=conv.id,
            created_at=conv.created_at,
            usage=usage,
        ))
    return result


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str, db: Session = Depends(get_db)):
    stmt = (
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.messages))
    )
    conv = db.scalars(stmt).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Compute usage sum
    usage_row = (
        db.query(
            func.coalesce(func.sum(Message.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(Message.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(Message.total_tokens), 0).label("total_tokens"),
        )
        .filter(Message.conversation_id == conv_id)
        .first()
    )
    usage = _build_usage(usage_row) if usage_row else None

    return ConversationDetail(
        id=conv.id,
        created_at=conv.created_at,
        messages=conv.messages,
        usage=usage,
    )
