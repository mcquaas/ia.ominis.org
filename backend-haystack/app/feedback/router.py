"""
Feedback endpoints: submit thumbs up/down and list for admins.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user, get_optional_user
from app.auth.models import RoleEnum, User
from app.database import get_db
from app.feedback.models import MessageFeedback
from app.feedback.schemas import FeedbackCreate, FeedbackList, FeedbackOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

REASON_LABELS = {
    "incorrecta_o_incompleta": "Incorrecta o incompleta",
    "no_es_lo_que_pedi": "No es lo que pedí",
    "lento_o_con_errores": "Lento o con errores",
    "estilo_o_tono": "Estilo o tono",
    "problema_seguridad_legal": "Problema de seguridad o legal",
    "otra": "Otra opción",
}


@router.post("", response_model=FeedbackOut)
async def create_feedback(
    body: FeedbackCreate,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback for a message. Auth optional (anonymous feedback allowed)."""
    feedback = MessageFeedback(
        message_id=body.message_id,
        conversation_id=body.conversation_id,
        user_id=user.id if user else None,
        rating=body.rating,
        reason_category=body.reason_category,
        reason_text=body.reason_text,
        content_preview=body.content_preview,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    out = FeedbackOut.model_validate(feedback)
    if feedback.user_id and user:
        out.user_email = user.email
    return out


@router.get("", response_model=FeedbackList)
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    rating: str | None = Query(None, pattern="^(positive|negative)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all feedback (admin and superadmin only)."""
    if user.role not in (RoleEnum.admin, RoleEnum.superadmin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    # Build query with optional join for user email
    stmt = select(MessageFeedback).order_by(MessageFeedback.created_at.desc())
    if rating:
        stmt = stmt.where(MessageFeedback.rating == rating)

    count_stmt = select(func.count()).select_from(MessageFeedback)
    if rating:
        count_stmt = count_stmt.where(MessageFeedback.rating == rating)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    stmt = stmt.options(selectinload(MessageFeedback.user))
    result = await db.execute(stmt)
    items = result.scalars().all()

    out_list = []
    for f in items:
        o = FeedbackOut.model_validate(f)
        if f.user:
            o.user_email = f.user.email
        out_list.append(o)

    return FeedbackList(data=out_list, total=total)
