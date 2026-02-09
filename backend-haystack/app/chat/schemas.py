"""
Pydantic schemas for the chat/conversation endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------- ChatMessage ----------

class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[list] = None
    has_images: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)
    sources: Optional[list] = None
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
