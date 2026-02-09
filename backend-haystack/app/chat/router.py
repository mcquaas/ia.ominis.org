"""
CRUD endpoints for conversations and chat messages.
"""

import logging
import uuid as uuid_module

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat.models import ChatMessage, Conversation
from app.chat.schemas import (
    AddMessagesRequest,
    ChatMessageOut,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    ConversationUpdate,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ─── helpers ────────────────────────────────────────────────────────

def _auto_title(content: str, max_len: int = 60) -> str:
    """Fallback: truncate first line as title."""
    import re
    first_line = content.strip().split("\n")[0].strip()
    first_line = re.sub(r"\[\d+ imágenes? adjuntas?:[^\]]*\]", "", first_line).strip()
    if len(first_line) > max_len:
        return first_line[:max_len].rsplit(" ", 1)[0] + "…"
    return first_line or "Nuevo trabajo"


async def _llm_title(user_content: str, assistant_content: str = "") -> str:
    """Use the LLM to generate a concise 5-8 word title for the conversation."""
    try:
        from app.rag.pipeline import get_pipeline_manager
        from haystack.dataclasses import ChatMessage as HayChatMessage

        manager = get_pipeline_manager()
        generator = manager.get_generator()

        messages = [
            HayChatMessage.from_system(
                "Genera un título MUY corto (5-8 palabras máximo) que resuma esta conversación. "
                "Solo responde con el título, sin comillas, sin puntuación final, sin explicación."
            ),
            HayChatMessage.from_user(
                f"Usuario: {user_content[:300]}\n"
                f"{'Asistente: ' + assistant_content[:200] if assistant_content else ''}"
            ),
        ]

        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generator.run(messages=messages, generation_kwargs={"num_predict": 30}),
        )
        replies = result.get("replies", [])
        title = replies[0].text.strip() if replies else ""
        # Clean up: remove quotes, trailing period, limit length
        title = title.strip('"\'').rstrip(".").strip()
        # Remove any non-Latin characters (CJK, Arabic, etc.)
        import re
        title = re.sub(r'[\u2E80-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF\u0600-\u06FF\u0E00-\u0E7F]+', '', title).strip()
        if title and 3 < len(title) < 80:
            return title
    except Exception as e:
        logger.warning(f"LLM title generation failed: {e}")

    return _auto_title(user_content)


async def _get_conversation_or_404(
    conversation_id: int,
    user: User,
    db: AsyncSession,
    *,
    load_messages: bool = False,
) -> Conversation:
    """Fetch a conversation ensuring it belongs to the current user."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    )
    if load_messages:
        stmt = stmt.options(selectinload(Conversation.messages))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


# ─── CRUD ───────────────────────────────────────────────────────────

@router.get("", response_model=ConversationList)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user (newest first)."""
    # Count
    count_stmt = select(func.count()).select_from(Conversation).where(
        Conversation.user_id == user.id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    return ConversationList(
        data=[ConversationOut.model_validate(c) for c in conversations],
        total=total,
    )


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    conv = Conversation(
        uuid=str(uuid_module.uuid4()),
        user_id=user.id,
        title=body.title or "Nuevo trabajo",
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    # Return with empty messages
    return ConversationDetail.model_validate({**conv.__dict__, "messages": []})


@router.get("/uuid/{conversation_uuid}", response_model=ConversationDetail)
async def get_conversation_by_uuid(
    conversation_uuid: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation by its UUID (for shareable URLs)."""
    stmt = select(Conversation).where(
        Conversation.uuid == conversation_uuid,
        Conversation.user_id == user.id,
    )
    stmt = stmt.options(selectinload(Conversation.messages))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationDetail.model_validate(conv)


@router.delete("/purge")
async def purge_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all conversations (and messages) for the current user."""
    count_stmt = select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
    total = (await db.execute(count_stmt)).scalar() or 0

    await db.execute(delete(Conversation).where(Conversation.user_id == user.id))
    await db.commit()
    return {"deleted": total}


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all its messages."""
    conv = await _get_conversation_or_404(conversation_id, user, db, load_messages=True)
    return ConversationDetail.model_validate(conv)


@router.put("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: int,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update conversation title or saved status."""
    conv = await _get_conversation_or_404(conversation_id, user, db)

    if body.title is not None:
        conv.title = body.title
    if body.is_saved is not None:
        conv.is_saved = body.is_saved

    await db.commit()
    await db.refresh(conv)
    return ConversationOut.model_validate(conv)


@router.post("/{conversation_id}/regenerate-title", response_model=ConversationOut)
async def regenerate_title(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate the conversation title using the LLM."""
    conv = await _get_conversation_or_404(conversation_id, user, db, load_messages=True)

    # Get first user and assistant messages
    user_content = ""
    assistant_content = ""
    for msg in conv.messages:
        if msg.role == "user" and not user_content:
            user_content = msg.content
        elif msg.role == "assistant" and not assistant_content:
            assistant_content = msg.content
        if user_content and assistant_content:
            break

    if user_content:
        new_title = await _llm_title(user_content, assistant_content[:200])
        conv.title = new_title
        await db.commit()
        await db.refresh(conv)

    return ConversationOut.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    conv = await _get_conversation_or_404(conversation_id, user, db)
    await db.delete(conv)
    await db.commit()


@router.post("/{conversation_id}/messages", response_model=list[ChatMessageOut])
async def add_messages(
    conversation_id: int,
    body: AddMessagesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add messages to a conversation. Auto-generates title from first user message if still default."""
    conv = await _get_conversation_or_404(conversation_id, user, db)

    new_msgs: list[ChatMessage] = []
    for msg_data in body.messages:
        msg = ChatMessage(
            conversation_id=conv.id,
            role=msg_data.role,
            content=msg_data.content,
            sources=msg_data.sources,
            has_images=msg_data.has_images,
        )
        db.add(msg)
        new_msgs.append(msg)

    # Auto-generate title using LLM if title is still default
    if conv.title == "Nuevo trabajo":
        first_user = next((m for m in body.messages if m.role == "user"), None)
        first_assistant = next((m for m in body.messages if m.role == "assistant"), None)
        if first_user:
            try:
                conv.title = await _llm_title(
                    first_user.content,
                    first_assistant.content[:200] if first_assistant else "",
                )
            except Exception:
                conv.title = _auto_title(first_user.content)

    await db.commit()
    for msg in new_msgs:
        await db.refresh(msg)

    return [ChatMessageOut.model_validate(m) for m in new_msgs]
