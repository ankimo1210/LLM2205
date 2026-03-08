import uuid


def test_list_conversations_empty_or_list(client):
    resp = client.get("/conversations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_conversation_not_found(client):
    resp = client.get(f"/conversations/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Conversation not found"


def test_list_and_get_conversation(client):
    # Direct DB insert to verify the read endpoints work without calling /chat
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.models import Conversation, Message

    conv_id = str(uuid.uuid4())
    with SessionLocal() as db:
        conv = Conversation(id=conv_id, created_at=datetime.now(timezone.utc))
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role="user",
            content="Hello",
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([conv, msg])
        db.commit()

    # List should now contain the conversation
    resp = client.get("/conversations")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert conv_id in ids

    # Detail should return with messages
    resp = client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert len(data["messages"]) == 1
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello"
