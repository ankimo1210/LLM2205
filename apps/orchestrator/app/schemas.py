from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    model: str | None = None
    # 空メッセージ・空白のみを拒否（API 422 として返す）
    message: str = Field(..., min_length=1)

    @field_validator("message")
    @classmethod
    def strip_and_require(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    role: str
    content: str
    created_at: datetime
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class UsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ConversationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    created_at: datetime
    usage: UsageOut | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
