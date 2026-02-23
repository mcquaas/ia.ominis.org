"""
Authentication routes.
Paths match the format the frontend expects:
  /v1/api/auth/local, /v1/api/users/me, etc.
"""

import json
import logging
import re
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
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
from app.config import get_settings
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


# ==================== Google OAuth ====================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = "openid email profile"


def _slug_username(raw: str, max_len: int = 50) -> str:
    """Build a safe username from a string (e.g. email local part or name)."""
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", raw).strip("_") or "user"
    return s[:max_len] if len(s) > max_len else s


async def _ensure_unique_username(db: AsyncSession, base: str) -> str:
    """Return base or base_N so the username is unique."""
    username = base[:100]
    n = 0
    while await get_user_by_username(db, username):
        n += 1
        username = f"{base[:90]}_{n}"
    return username


@router.get("/api/connect/google")
async def connect_google_start(request: Request):
    """
    Start Google OAuth: redirect user to Google consent, then back to callback.
    Frontend sends users here (e.g. from "Continuar con Google" on login).
    """
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured",
        )
    state = secrets.token_urlsafe(32)
    callback_url = request.url_for("google_oauth_callback")
    if settings.backend_public_url:
        base = settings.backend_public_url.rstrip("/")
        redirect_uri = f"{base}/v1/api/connect/google/callback"
    else:
        redirect_uri = str(callback_url)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=600)
    return response


@router.get("/api/connect/google/callback", name="google_oauth_callback")
async def connect_google_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Google OAuth callback: exchange code for tokens, get user info, create or find user, redirect to frontend with JWT.
    """
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Google login is not configured")

    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=google_denied",
            status_code=302,
        )

    cookie_state = request.cookies.get("oauth_state")
    if not state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid or missing state")
    response = RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/connect/google/redirect",
        status_code=302,
    )
    response.delete_cookie("oauth_state")

    if not code:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_code",
            status_code=302,
        )

    if settings.backend_public_url:
        base = settings.backend_public_url.rstrip("/")
        redirect_uri = f"{base}/v1/api/connect/google/callback"
    else:
        redirect_uri = str(request.url_for("google_oauth_callback"))
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.warning("Google token exchange failed: %s %s", token_resp.status_code, token_resp.text)
            return RedirectResponse(
                url=f"{settings.frontend_url.rstrip('/')}/login?error=token_exchange_failed",
                status_code=302,
            )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse(
                url=f"{settings.frontend_url.rstrip('/')}/login?error=no_token",
                status_code=302,
            )
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.warning("Google userinfo failed: %s", userinfo_resp.status_code)
            return RedirectResponse(
                url=f"{settings.frontend_url.rstrip('/')}/login?error=userinfo_failed",
                status_code=302,
            )
        userinfo = userinfo_resp.json()

    email = userinfo.get("email")
    if not email:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_email",
            status_code=302,
        )

    user = await get_user_by_email(db, email)
    if not user:
        name = userinfo.get("name") or ""
        base_username = _slug_username(userinfo.get("email", "").split("@")[0] or name or "user")
        username = await _ensure_unique_username(db, base_username)
        oauth_password = secrets.token_urlsafe(32)
        user = await create_user(db, username, email, oauth_password)
        if name:
            await update_user(db, user, full_name=name)

    if not user.is_active:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=account_blocked",
            status_code=302,
        )

    token = create_access_token(user.id, user.role.value)
    user_out = user_to_response(user)
    user_param = urllib.parse.quote(json.dumps(user_out.model_dump()))
    redirect_url = (
        f"{settings.frontend_url.rstrip('/')}/connect/google/redirect"
        f"?jwt={urllib.parse.quote(token)}&user={user_param}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


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
