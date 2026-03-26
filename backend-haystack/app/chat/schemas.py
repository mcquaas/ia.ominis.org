"""
Pydantic schemas for the chat/conversation endpoints.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ---------- ChatMessage ----------

class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[list] = None
    sources_not_used: Optional[list] = None
    has_images: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def unpack_stored_sources(cls, data: Any) -> Any:
        """DB may store {"used": [...], "not_used": [...]} in the sources JSON column."""
        if isinstance(data, dict):
            src = data.get("sources")
            if isinstance(src, dict) and "used" in src:
                return {
                    **data,
                    "sources": src.get("used"),
                    "sources_not_used": src.get("not_used"),
                }
            return data
        src = getattr(data, "sources", None)
        if isinstance(src, dict) and "used" in src:
            return {
                "id": data.id,
                "role": data.role,
                "content": data.content,
                "sources": src.get("used"),
                "sources_not_used": src.get("not_used"),
                "has_images": data.has_images,
                "created_at": data.created_at,
            }
        return data


class ChatMessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)
    sources: Optional[list] = None
    sources_not_used: Optional[list] = None
    has_images: bool = False


# ---------- Conversation ----------

class ConversationOut(BaseModel):
    id: int
    uuid: str
    title: str
    is_saved: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[ChatMessageOut] = []


class ConversationCreate(BaseModel):
    title: Optional[str] = None  # Auto-generated if not provided


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    is_saved: Optional[bool] = None


class ConversationList(BaseModel):
    data: list[ConversationOut]
    total: int


class AddMessagesRequest(BaseModel):
    """Add one or more messages to a conversation."""
    messages: list[ChatMessageCreate] = Field(..., min_length=1)
