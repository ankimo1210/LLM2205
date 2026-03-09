import uuid
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Conversation, Message


def test_message_usage_columns_saved(client):
    """Usage columns on Message can be saved and read back."""
    conv_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.add(Conversation(id=conv_id, created_at=datetime.now(timezone.utc)))
        db.add(Message(
            id=msg_id,
            conversation_id=conv_id,
            role="assistant",
            content="Hello",
            created_at=datetime.now(timezone.utc),
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        ))
        db.commit()

    resp = client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    msgs = data["messages"]
    assert len(msgs) == 1
    assert msgs[0]["prompt_tokens"] == 100
    assert msgs[0]["completion_tokens"] == 50
    assert msgs[0]["total_tokens"] == 150


def test_conversation_detail_returns_usage_sum(client):
    """GET /conversations/{id} returns aggregated usage across messages."""
    conv_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.add(Conversation(id=conv_id, created_at=datetime.now(timezone.utc)))
        # User message (no usage)
        db.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="user",
            content="Hi",
            created_at=datetime.now(timezone.utc),
        ))
        # First assistant reply
        db.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="assistant",
            content="Hello!",
            created_at=datetime.now(timezone.utc),
            prompt_tokens=50,
            completion_tokens=20,
            total_tokens=70,
        ))
        # Second assistant reply
        db.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="assistant",
            content="How can I help?",
            created_at=datetime.now(timezone.utc),
            prompt_tokens=80,
            completion_tokens=30,
            total_tokens=110,
        ))
        db.commit()

    resp = client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["usage"] is not None
    assert data["usage"]["prompt_tokens"] == 130
    assert data["usage"]["completion_tokens"] == 50
    assert data["usage"]["total_tokens"] == 180


def test_conversation_list_includes_usage(client):
    """GET /conversations includes usage for each conversation."""
    conv_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.add(Conversation(id=conv_id, created_at=datetime.now(timezone.utc)))
        db.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="assistant",
            content="Reply",
            created_at=datetime.now(timezone.utc),
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
        ))
        db.commit()

    resp = client.get("/conversations")
    assert resp.status_code == 200
    convs = resp.json()
    matched = [c for c in convs if c["id"] == conv_id]
    assert len(matched) == 1
    assert matched[0]["usage"] is not None
    assert matched[0]["usage"]["total_tokens"] == 300


def test_conversation_no_usage_returns_null(client):
    """Conversation with no usage data returns usage=null."""
    conv_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.add(Conversation(id=conv_id, created_at=datetime.now(timezone.utc)))
        db.add(Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="user",
            content="Hi",
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

    resp = client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["usage"] is None
