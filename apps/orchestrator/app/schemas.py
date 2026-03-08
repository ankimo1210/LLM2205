from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
