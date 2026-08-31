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
from app.auth.cias_service import authenticate_with_cias, check_cias_membership
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
    """
    Login exclusively through CIAS (cias.ai).
    Only verified CIAS members (and admins) are granted access to OMINIS.
    """
    cias_res = await authenticate_with_cias(body.identifier, body.password)

    if not cias_res.is_authenticated:
        # If authentication failed
        status_code = status.HTTP_403_FORBIDDEN if cias_res.error_code == "ACCOUNT_FORBIDDEN" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=cias_res.error_message or "Invalid identifier or password",
        )

    if not cias_res.is_member:
        # Authenticated on CIAS, but not a verified member
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=cias_res.error_message or "Acceso restringido: Sólo miembros de la Red CIAS pueden usar OMINIS.",
        )

    # User is a valid CIAS member. Provision or update user in local OMINIS database
    email = cias_res.email or body.identifier.strip().lower()
    user = await get_user_by_email(db, email)

    if not user:
        # Create local user record
        base_username = _slug_username(email.split("@")[0] or cias_res.name or "member")
        username = await _ensure_unique_username(db, base_username)
        # Assign admin if CIAS role is admin, otherwise researcher
        role = RoleEnum.admin if cias_res.role == "admin" else RoleEnum.researcher
        random_pwd = secrets.token_urlsafe(32)
        user = await create_user(db, username, email, random_pwd, role=role)
        if cias_res.name:
            await update_user(db, user, full_name=cias_res.name)
    else:
        # Update user profile details from CIAS
        if cias_res.name and user.full_name != cias_res.name:
            await update_user(db, user, full_name=cias_res.name)
        if cias_res.role == "admin" and user.role not in (RoleEnum.admin, RoleEnum.superadmin):
            await update_user(db, user, role=RoleEnum.admin)
        if not user.is_active:
            await update_user(db, user, is_active=True)

    token = create_access_token(user.id, user.role.value)
    return AuthResponse(jwt=token, user=user_to_response(user))


@router.post("/api/auth/local/register", response_model=AuthResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Registration is managed exclusively via CIAS."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="El registro de cuentas se realiza exclusivamente a través de la Red CIAS en https://www.cias.ai/auth. Inicia sesión con tu cuenta de miembro una vez creada.",
    )


# ==================== CIAS SSO (Single Sign-On Centralizado) ====================

@router.get("/api/connect/cias")
async def connect_cias_start(request: Request):
    """
    Start CIAS Centralized SSO: redirect user to https://www.cias.ai/sso
    where they authenticate using Google, Didactiva, LinkedIn or CIAS credentials.
    CIAS verifies verified member status and redirects back with a signed SSO authorization code.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    redirect_uri = _get_redirect_uri(request, "cias")
    cias_base = (settings.cias_auth_url or "https://www.cias.ai").rstrip("/")

    params = {
        "client_id": "ominis",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    url = f"{cias_base}/sso?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(key="oauth_state_cias", value=state, httponly=True, max_age=600)
    return response


@router.get("/api/connect/cias/callback", name="cias_oauth_callback")
async def connect_cias_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    CIAS SSO callback: verify SSO code with CIAS provider (/api/sso/verify),
    provision user in Ominis, issue local JWT and redirect to dashboard.
    """
    settings = get_settings()

    if error:
        logger.warning("CIAS SSO error from provider: %s", error)
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=cias_denied",
            status_code=302,
        )

    cookie_state = request.cookies.get("oauth_state_cias")
    if not state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid or missing state")

    response = RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/connect/cias/redirect",
        status_code=302,
    )
    response.delete_cookie("oauth_state_cias")

    if not code:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_code",
            status_code=302,
        )

    redirect_uri = _get_redirect_uri(request, "cias")
    cias_base = (settings.cias_auth_url or "https://www.cias.ai").rstrip("/")
    verify_url = f"{cias_base}/api/sso/verify"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                verify_url,
                json={"code": code, "redirect_uri": redirect_uri},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Ominis-SSO/1.0",
                },
            )
            if resp.status_code != 200:
                logger.warning("CIAS SSO verification failed: %s %s", resp.status_code, resp.text)
                return RedirectResponse(
                    url=f"{settings.frontend_url.rstrip('/')}/login?error=cias_member_required",
                    status_code=302,
                )
            data = resp.json()
            user_data = data.get("user") or {}
        except Exception as e:
            logger.error("Error connecting to CIAS SSO verify endpoint: %s", e)
            return RedirectResponse(
                url=f"{settings.frontend_url.rstrip('/')}/login?error=cias_error",
                status_code=302,
            )

    email = (user_data.get("email") or "").strip().lower()
    if not email:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_email",
            status_code=302,
        )

    name = user_data.get("name") or email.split("@")[0]
    role = user_data.get("role", "user")
    is_member = user_data.get("memberVerified", False) or role == "admin"

    if not is_member:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=cias_member_required",
            status_code=302,
        )

    role_enum = RoleEnum.admin if role == "admin" else RoleEnum.researcher

    user = await get_user_by_email(db, email)
    if not user:
        base_username = _slug_username(email.split("@")[0] or name or "member")
        username = await _ensure_unique_username(db, base_username)
        oauth_password = secrets.token_urlsafe(32)
        user = await create_user(db, username, email, oauth_password, role=role_enum)
        if name:
            await update_user(db, user, full_name=name)
    else:
        if name and user.full_name != name:
            await update_user(db, user, full_name=name)
        if role == "admin" and user.role not in (RoleEnum.admin, RoleEnum.superadmin):
            await update_user(db, user, role=RoleEnum.admin)
        if not user.is_active:
            await update_user(db, user, is_active=True)

    token = create_access_token(user.id, user.role.value)
    user_out = user_to_response(user)
    user_param = urllib.parse.quote(json.dumps(user_out.model_dump()))
    redirect_url = (
        f"{settings.frontend_url.rstrip('/')}/connect/cias/redirect"
        f"?jwt={urllib.parse.quote(token)}&user={user_param}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


# ==================== Google OAuth ====================

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = "openid email profile"


def _slug_username(raw: str, max_len: int = 50) -> str:
    """Build a safe username from a string (e.g. email local part or name)."""
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", raw).strip("_") or "user"
    return s[:max_len] if len(s) > max_len else s


def _get_redirect_uri(request: Request, provider: str) -> str:
    """
    Return redirect_uri for OAuth. Prefers https://ia.ominis.org/api/connect/{provider}/callback
    when request came through frontend proxy or frontend_url is configured.
    """
    settings = get_settings()
    if settings.frontend_url and "localhost" not in settings.frontend_url:
        return f"{settings.frontend_url.rstrip('/')}/api/connect/{provider}/callback"
    if settings.backend_public_url:
        return f"{settings.backend_public_url.rstrip('/')}/v1/api/connect/{provider}/callback"
    return str(request.url_for(f"{provider}_oauth_callback"))


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
    redirect_uri = _get_redirect_uri(request, "google")
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

    redirect_uri = _get_redirect_uri(request, "google")
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

    # Verify if email is a verified CIAS member
    is_cias_member, member_name, member_role = await check_cias_membership(email)

    if not is_cias_member:
        # Check against existing local admins
        user_check = await get_user_by_email(db, email)
        if user_check and user_check.role in (RoleEnum.admin, RoleEnum.superadmin):
            is_cias_member = True
            member_role = "admin"

    if not is_cias_member:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=cias_member_required",
            status_code=302,
        )

    user = await get_user_by_email(db, email)
    role_enum = RoleEnum.admin if member_role == "admin" else RoleEnum.researcher
    name = member_name or userinfo.get("name") or ""

    if not user:
        base_username = _slug_username(userinfo.get("email", "").split("@")[0] or name or "user")
        username = await _ensure_unique_username(db, base_username)
        oauth_password = secrets.token_urlsafe(32)
        user = await create_user(db, username, email, oauth_password, role=role_enum)
        if name:
            await update_user(db, user, full_name=name)
    else:
        if name and user.full_name != name:
            await update_user(db, user, full_name=name)
        if member_role == "admin" and user.role not in (RoleEnum.admin, RoleEnum.superadmin):
            await update_user(db, user, role=RoleEnum.admin)
        if not user.is_active:
            await update_user(db, user, is_active=True)

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


# ==================== Didactiva OAuth ====================

@router.get("/api/connect/didactiva")
async def connect_didactiva_start(request: Request):
    """
    Start Didactiva (Moodle) OAuth: redirect user to Didactiva login, then back to callback.
    Didactiva accounts are verified members of CIAS.
    """
    settings = get_settings()
    if not (settings.didactiva_client_id and settings.didactiva_client_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Didactiva login is not configured",
        )
    state = secrets.token_urlsafe(32)
    redirect_uri = _get_redirect_uri(request, "didactiva")

    params = {
        "client_id": settings.didactiva_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": settings.didactiva_scopes or "user_info",
        "state": state,
    }
    auth_url = settings.didactiva_auth_url or f"{settings.didactiva_base_url.rstrip('/')}/local/oauth2/login.php"
    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(key="oauth_state_didactiva", value=state, httponly=True, max_age=600)
    return response


@router.get("/api/connect/didactiva/callback", name="didactiva_oauth_callback")
async def connect_didactiva_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Didactiva OAuth callback: exchange code for access token, fetch profile, provision user, and redirect to frontend with JWT.
    """
    settings = get_settings()
    if not (settings.didactiva_client_id and settings.didactiva_client_secret):
        raise HTTPException(status_code=503, detail="Didactiva login is not configured")

    if error:
        logger.warning("Didactiva OAuth error: %s", error)
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=didactiva_denied",
            status_code=302,
        )

    cookie_state = request.cookies.get("oauth_state_didactiva")
    if not state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid or missing state")
    response = RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/connect/didactiva/redirect",
        status_code=302,
    )
    response.delete_cookie("oauth_state_didactiva")

    if not code:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_code",
            status_code=302,
        )

    redirect_uri = _get_redirect_uri(request, "didactiva")

    token_url = settings.didactiva_token_url or f"{settings.didactiva_base_url.rstrip('/')}/local/oauth2/token.php"
    userinfo_url = settings.didactiva_userinfo_url or f"{settings.didactiva_base_url.rstrip('/')}/local/oauth2/user_info.php"

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            token_url,
            data={
                "code": code,
                "client_id": settings.didactiva_client_id,
                "client_secret": settings.didactiva_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.warning("Didactiva token exchange failed: %s %s", token_resp.status_code, token_resp.text)
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

        # Attempt to get userinfo via GET and fallback to POST
        userinfo = None
        for ep in [userinfo_url, userinfo_url.replace("/user_info.php", "/userinfo.php")]:
            try:
                resp = await client.get(
                    ep,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if resp.status_code == 200:
                    userinfo = resp.json()
                    break
                # Fallback POST with access_token
                resp_post = await client.post(
                    ep,
                    data={"access_token": access_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                )
                if resp_post.status_code == 200:
                    userinfo = resp_post.json()
                    break
            except Exception as ex:
                logger.warning(f"Error fetching Didactiva userinfo from {ep}: {ex}")

        if not userinfo:
            return RedirectResponse(
                url=f"{settings.frontend_url.rstrip('/')}/login?error=userinfo_failed",
                status_code=302,
            )

    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=no_email",
            status_code=302,
        )

    # Format name
    name = (
        userinfo.get("name")
        or " ".join(
            filter(
                None,
                [
                    userinfo.get("given_name") or userinfo.get("firstname"),
                    userinfo.get("family_name") or userinfo.get("lastname"),
                ],
            )
        )
        or email.split("@")[0]
    ).strip()

    # Didactiva accounts are valid CIAS members. Check if admin on CIAS.
    _, _, member_role = await check_cias_membership(email)
    role_enum = RoleEnum.admin if member_role == "admin" else RoleEnum.researcher

    user = await get_user_by_email(db, email)
    if not user:
        base_username = _slug_username(email.split("@")[0] or name or "member")
        username = await _ensure_unique_username(db, base_username)
        oauth_password = secrets.token_urlsafe(32)
        user = await create_user(db, username, email, oauth_password, role=role_enum)
        if name:
            await update_user(db, user, full_name=name)
    else:
        if name and user.full_name != name:
            await update_user(db, user, full_name=name)
        if member_role == "admin" and user.role not in (RoleEnum.admin, RoleEnum.superadmin):
            await update_user(db, user, role=RoleEnum.admin)
        if not user.is_active:
            await update_user(db, user, is_active=True)

    token = create_access_token(user.id, user.role.value)
    user_out = user_to_response(user)
    user_param = urllib.parse.quote(json.dumps(user_out.model_dump()))
    redirect_url = (
        f"{settings.frontend_url.rstrip('/')}/connect/didactiva/redirect"
        f"?jwt={urllib.parse.quote(token)}&user={user_param}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/api/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password notification: password is authenticated via CIAS."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Las contraseñas se administran exclusivamente desde tu cuenta en CIAS: https://www.cias.ai/cuenta",
    )


@router.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Request password reset via CIAS."""
    return {"ok": True, "message": "Si tu correo corresponde a una cuenta de CIAS, recupérala en https://www.cias.ai/auth"}


@router.post("/api/auth/reset-password", response_model=AuthResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password handled via CIAS."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="La recuperación de contraseña se realiza en https://www.cias.ai/auth",
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
