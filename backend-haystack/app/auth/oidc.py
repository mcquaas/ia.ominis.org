"""
OpenID Connect provider for LibreChat (and other OIDC clients).
Registration and login stay on ia.ominis.org; this allows chat.ominis.org to
delegate auth to the same user base.
"""

import logging
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import create_access_token, decode_access_token, get_user_by_id
from app.config import get_settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oidc", tags=["oidc"])

# In-memory store: code -> (user_id, redirect_uri, client_id, expires_at, issuer)
_oidc_codes: dict[str, tuple[int, str, str, float, str]] = {}
_CODE_TTL_SECONDS = 300


def _get_issuer(request: Optional[Request] = None) -> str:
    """Issuer base URL; use request path so /v1/oauth2 returns oauth2 issuer."""
    s = get_settings()
    base = (s.backend_public_url or "").strip().rstrip("/") or "http://localhost:8000"
    if request and "/oauth2" in (request.url.path or ""):
        return f"{base}/v1/oauth2"
    return f"{base}/v1/oidc"


def _clean_expired_codes() -> None:
    now = time.time()
    expired = [c for c, v in _oidc_codes.items() if v[3] < now]
    for c in expired:
        del _oidc_codes[c]


def _issuer_from_entry(entry: tuple) -> str:
    return entry[4] if len(entry) > 4 else _get_issuer(None)


def _validate_client_id(client_id: str) -> bool:
    """Check that client_id is registered (for authorize step; no secret in URL)."""
    s = get_settings()
    return (s.oidc_librechat_client_id or "").strip() == client_id


def _validate_client(client_id: str, client_secret: str) -> bool:
    """Full validation with secret (for token exchange)."""
    s = get_settings()
    return (
        (s.oidc_librechat_client_id or "").strip() == client_id
        and (s.oidc_librechat_client_secret or "").strip() == client_secret
    )


def _create_id_token(user_id: int, email: str, name: str, client_id: str, issuer: Optional[str] = None) -> str:
    """Build an OIDC id_token JWT (iss, sub, aud, exp, iat, email, name)."""
    from jose import jwt

    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.jwt_expiration_minutes)
    payload = {
        "iss": issuer or _get_issuer(None),
        "sub": str(user_id),
        "aud": client_id,
        "exp": exp,
        "iat": now,
        "email": email or "",
        "name": name or "",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


@router.get("/.well-known/openid-configuration")
async def openid_configuration(request: Request):
    """OIDC discovery document."""
    issuer = _get_issuer(request)
    base = issuer.rstrip("/")
    return JSONResponse({
        "issuer": issuer,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "jwks_uri": f"{base}/jwks",
        "scopes_supported": ["openid", "profile", "email"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [get_settings().jwt_algorithm],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
    })


@router.get("/authorize")
async def oidc_authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query("openid profile email"),
    state: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Authorization endpoint. If no `token` in query, redirect to ia.ominis.org login
    with next=this URL. After login, frontend redirects back with token=JWT; we then
    issue a code and redirect to LibreChat.
    """
    settings = get_settings()
    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type must be code")

    if not _validate_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # Allowed redirect URIs (LibreChat may use /oauth/callback or /oauth/openid/callback)
    allowed = [s.strip() for s in (settings.oidc_librechat_redirect_uris or "").split(",") if s.strip()]
    if not allowed:
        allowed = [
            "https://chat.ominis.org/oauth/openid/callback",
            "https://chat.ominis.org/oauth/callback",
        ]
    if redirect_uri not in allowed:
        logger.warning("OIDC redirect_uri not allowed: %s", redirect_uri)
        raise HTTPException(status_code=400, detail="redirect_uri not allowed")

    # No token: send user to login on ia.ominis.org; next = this URL so they come back with token
    if not token:
        current_url = str(request.url)
        login_url = f"{settings.frontend_url.rstrip('/')}/login?next={urllib.parse.quote(current_url)}"
        return RedirectResponse(url=login_url, status_code=302)

    # Validate JWT from frontend (user just logged in on ia.ominis.org)
    payload = decode_access_token(token)
    if not payload:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=invalid_token&next={urllib.parse.quote(str(request.url))}",
            status_code=302,
        )
    user_id = int(payload.get("sub", 0))
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        return RedirectResponse(
            url=f"{settings.frontend_url.rstrip('/')}/login?error=user_inactive",
            status_code=302,
        )

    # Create one-time code and redirect to LibreChat (store issuer so id_token matches /oidc vs /oauth2)
    _clean_expired_codes()
    code = secrets.token_urlsafe(32)
    issuer = _get_issuer(request)
    _oidc_codes[code] = (user.id, redirect_uri, client_id, time.time() + _CODE_TTL_SECONDS, issuer)

    sep = "&" if "?" in redirect_uri else "?"
    out = f"{redirect_uri}{sep}code={urllib.parse.quote(code)}"
    if state:
        out += f"&state={urllib.parse.quote(state)}"
    return RedirectResponse(url=out, status_code=302)


@router.post("/token")
async def oidc_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code for id_token and access_token. Accepts application/x-www-form-urlencoded."""
    try:
        body = await request.form()
    except Exception:
        body = {}
    grant_type = body.get("grant_type")
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    client_id = body.get("client_id")
    client_secret = body.get("client_secret")
    if grant_type != "authorization_code" or not code or not redirect_uri or not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Invalid token request")

    if not _validate_client(client_id, client_secret):
        raise HTTPException(status_code=401, detail="Invalid client")

    _clean_expired_codes()
    entry = _oidc_codes.pop(code, None)
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    user_id, stored_redirect_uri, stored_client_id, _, _ = entry
    if stored_redirect_uri != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    email = user.email or ""
    name = user.full_name or user.username or ""
    issuer = _issuer_from_entry(entry)
    id_token = _create_id_token(user.id, email, name, stored_client_id, issuer=issuer)
    access_token = create_access_token(user.id, user.role.value)

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": get_settings().jwt_expiration_minutes * 60,
        "id_token": id_token,
    })


@router.get("/userinfo")
async def oidc_userinfo(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return user info for the Bearer token (our JWT)."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth[7:].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = int(payload.get("sub", 0))
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return JSONResponse({
        "sub": str(user.id),
        "email": user.email or "",
        "name": user.full_name or user.username or "",
    })


@router.get("/jwks")
async def jwks():
    """JWKS endpoint (optional). LibreChat may use id_token verification; we use HS256 with shared secret so JWKS is not required for that."""
    return JSONResponse({"keys": []})


# LibreChat may call /v1/oauth2/authorize instead of /v1/oidc/authorize; expose same endpoints under /oauth2
router_oauth2 = APIRouter(prefix="/oauth2", tags=["oidc"])
router_oauth2.get("/.well-known/openid-configuration")(openid_configuration)
router_oauth2.get("/authorize")(oidc_authorize)
router_oauth2.post("/token")(oidc_token)
router_oauth2.get("/userinfo")(oidc_userinfo)
router_oauth2.get("/jwks")(jwks)
