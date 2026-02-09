"""Pydantic schemas for feedback endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


REASON_CATEGORIES = [
    "incorrecta_o_incompleta",
    "no_es_lo_que_pedi",
    "lento_o_con_errores",
    "estilo_o_tono",
    "problema_seguridad_legal",
    "otra",
]


class FeedbackCreate(BaseModel):
    """Submit feedback for a message."""
    message_id: Optional[int] = None
    conversation_id: Optional[int] = None
    rating: str = Field(..., pattern="^(positive|negative)$")
    reason_category: Optional[str] = None
    reason_text: Optional[str] = None
    content_preview: Optional[str] = Field(None, max_length=500)
    model_name: Optional[str] = Field(None, max_length=100)
    query_title: Optional[str] = Field(None, max_length=500)
    sources: Optional[list[dict[str, Any]]] = None  # RAG/web/PubMed sources used for response


class FeedbackOut(BaseModel):
    id: int
    message_id: Optional[int] = None
    conversation_id: Optional[int] = None
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    rating: str
    reason_category: Optional[str] = None
    reason_text: Optional[str] = None
    content_preview: Optional[str] = None
    model_name: Optional[str] = None
    query_title: Optional[str] = None
    sources: Optional[list[dict[str, Any]]] = None  # RAG/web/PubMed sources used for response

    model_config = {"from_attributes": True}


class FeedbackList(BaseModel):
    data: list[FeedbackOut]
    total: int
