"""
MessageFeedback model for storing thumbs up/down and optional reason on chat responses.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating = Column(String(10), nullable=False)  # "positive" | "negative"
    reason_category = Column(String(100), nullable=True)  # preset option
    reason_text = Column(Text, nullable=True)  # free-form details
    content_preview = Column(String(500), nullable=True)  # first 500 chars for admin display
    model_name = Column(String(100), nullable=True)  # LLM used at time of response
    query_title = Column(String(500), nullable=True)  # conversation title or query summary
    sources_json = Column(JSONB, nullable=True)  # RAG/web/PubMed sources used for the response

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    message = relationship("ChatMessage", backref="feedback", foreign_keys=[message_id])
    conversation = relationship("Conversation", backref="feedback", foreign_keys=[conversation_id])
    user = relationship("User", backref="feedback", foreign_keys=[user_id])
