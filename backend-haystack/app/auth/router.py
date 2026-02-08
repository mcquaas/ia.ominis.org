"""
Authentication routes.
Paths match the Strapi-compatible format the frontend expects:
  /v1/api/auth/local, /v1/api/users/me, etc.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import RoleEnum, User
from app.auth.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RoleOut,
    UpdateUserRequest,
    UserOut,
    UserUsageOut,
)
from app.auth.service import (
    create_access_token,
    create_user,
    delete_user,
    get_all_users,
    get_user_by_email,
    get_user_by_identifier,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    update_user,
    verify_password,
)
from app.admin.models import QueryLog
from app.database import get_db
from app.chat.models import Conversation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


# --- Helpers ---

def _role_id(role: RoleEnum) -> int:
    """Map role enum to a numeric ID matching frontend expectations."""
    return {"researcher": 1, "developer": 2, "admin": 3, "superadmin": 4}.get(role.value, 1)


_ROLE_DISPLAY_NAMES = {
    "researcher": "Investigador/a",
    "developer": "Desarrollador/a",
    "admin": "Administrador/a",
    "superadmin": "Super Admin",
}


def user_to_response(user: User) -> UserOut:
    """Convert a User ORM model to the frontend-expected UserOut schema."""
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=RoleOut(
            id=_role_id(user.role),
            name=_ROLE_DISPLAY_NAMES.get(user.role.value, user.role.value.capitalize()),
            type=user.role.value,
        ),
        full_name=user.full_name,
        institution=user.institution,
        bio=user.bio,
        confirmed=True,
        blocked=not user.is_active,
        createdAt=user.created_at.isoformat() if user.created_at else "",
        updatedAt=user.updated_at.isoformat() if user.updated_at else "",
    )


# ==================== Authentication ====================


@router.post("/api/auth/local", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email/username and password."""
    user = await get_user_by_identifier(db, body.identifier)

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid identifier or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(user.id, user.role.value)
    return AuthResponse(jwt=token, user=user_to_response(user))


@router.post("/api/auth/local/register", response_model=AuthResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user (defaults to researcher role)."""
    # Check existing
    if await get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already taken",
        )
    if await get_user_by_username(db, body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken",
        )

    user = await create_user(db, body.username, body.email, body.password)
    token = create_access_token(user.id, user.role.value)
    return AuthResponse(jwt=token, user=user_to_response(user))


@router.post("/api/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if body.password != body.passwordConfirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password confirmation does not match",
        )

    if not verify_password(body.currentPassword, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = hash_password(body.password)
    await db.commit()
    return {"ok": True}


@router.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Request a password reset.
    In production, this would send an email with a reset code.
    For now, returns ok regardless (to not leak whether email exists).
    """
    # TODO: Implement email sending with reset code
    logger.info(f"Password reset requested for: {body.email}")
    return {"ok": True}


@router.post("/api/auth/reset-password", response_model=AuthResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Reset password with a code.
    TODO: Validate the code against stored reset tokens.
    """
    if body.password != body.passwordConfirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password confirmation does not match",
        )

    # TODO: Look up the user by the reset code
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Password reset via code not yet implemented. Contact admin.",
    )


# ==================== User Profile ====================


@router.get("/api/users/me", response_model=UserOut)
async def get_me(
    populate: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's profile."""
    return user_to_response(current_user)


@router.get("/api/users/me/usage", response_model=UserUsageOut)
async def get_my_usage(
    period: str = Query("month"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage stats for the current user."""
    now = datetime.now(timezone.utc)
    period_map = {
        "day": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
    }
    delta = period_map.get(period, timedelta(days=30))
    start_date = now - delta

    total_queries_result = await db.execute(
        select(func.count())
        .select_from(QueryLog)
        .where(QueryLog.user_id == current_user.id)
        .where(QueryLog.created_at >= start_date)
    )
    total_queries = total_queries_result.scalar() or 0

    tokens_result = await db.execute(
        select(func.sum(QueryLog.tokens_used))
        .where(QueryLog.user_id == current_user.id)
        .where(QueryLog.created_at >= start_date)
    )
    total_tokens = tokens_result.scalar() or 0

    conv_result = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.user_id == current_user.id)
        .where(Conversation.created_at >= start_date)
    )
    total_investigations = conv_result.scalar() or 0

    return UserUsageOut(
        period=period,
        startDate=start_date.isoformat(),
        endDate=now.isoformat(),
        totalQueries=total_queries,
        totalTokens=total_tokens,
        totalInvestigations=total_investigations,
    )


@router.put("/api/users/{user_id}", response_model=UserOut)
async def update_user_endpoint(
    user_id: int,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a user. Users can update themselves; superadmins can update anyone.
    """
    if current_user.id != user_id and current_user.role != RoleEnum.superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update another user's profile",
        )

    target_user = await get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)

    # Only superadmins can change roles and block status
    if "role" in update_data and current_user.role != RoleEnum.superadmin:
        del update_data["role"]
    if "blocked" in update_data:
        if current_user.role != RoleEnum.superadmin:
            raise HTTPException(status_code=403, detail="Only superadmins can block users")
        update_data["is_active"] = not update_data.pop("blocked")

    # Map role string to enum
    if "role" in update_data:
        try:
            update_data["role"] = RoleEnum(update_data["role"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role")

    updated = await update_user(db, target_user, **update_data)
    return user_to_response(updated)


# ==================== User Management (SuperAdmin) ====================


@router.get("/api/users", response_model=list[UserOut])
async def list_users(
    populate: Optional[str] = Query(None),
    _: User = Depends(require_role(RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """List all users (SuperAdmin only)."""
    users = await get_all_users(db)
    return [user_to_response(u) for u in users]


@router.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_role(RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (SuperAdmin only)."""
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    target_user = await get_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    await delete_user(db, target_user)
