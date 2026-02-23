"""
API Key management routes.
Paths match the format the frontend expects.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys.models import APIKey, APIKeyStatus
from app.api_keys.schemas import (
    APIKeyOut,
    APIKeyPermissions,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
)
from app.api_keys.service import (
    create_api_key,
    get_api_key_by_id,
    get_user_api_keys,
    revoke_api_key,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api-keys"])


# --- Helpers ---

def _key_to_out(key: APIKey) -> APIKeyOut:
    """Convert an APIKey ORM model to the frontend-expected schema."""
    try:
        perms = json.loads(key.permissions) if key.permissions else {}
    except (json.JSONDecodeError, TypeError):
        perms = {}

    return APIKeyOut(
        id=key.id,
        name=key.name,
        keyPrefix=key.key_prefix,
        status=key.status.value if key.status else "active",
        permissions=APIKeyPermissions(
            query=perms.get("query", True),
            queryGpu=perms.get("queryGpu", True),
            sources=perms.get("sources", False),
        ),
        rateLimit=100,
        rateLimitWindow="minute",
        requestsCount=str(key.request_count),
        lastUsedAt=key.last_used_at.isoformat() if key.last_used_at else None,
        expiresAt=key.expires_at.isoformat() if key.expires_at else None,
        createdAt=key.created_at.isoformat() if key.created_at else "",
    )


# ==================== Routes ====================


@router.get("/api/api-keys")
async def list_api_keys(
    populate: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's API keys."""
    keys = await get_user_api_keys(db, current_user.id)
    return {"data": [_key_to_out(k) for k in keys]}


@router.post("/api/api-keys", response_model=CreateAPIKeyResponse)
async def create_key(
    body: dict,  # Accept { data: CreateAPIKeyRequest }
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key for the current user."""
    data = body.get("data", body)
    request = CreateAPIKeyRequest(**data)

    # Parse expiration
    expires_at = None
    if request.expiresAt:
        try:
            expires_at = datetime.fromisoformat(request.expiresAt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiration date format")

    permissions = request.permissions.model_dump() if request.permissions else None

    api_key, full_key = await create_api_key(
        db=db,
        user_id=current_user.id,
        name=request.name,
        permissions=permissions,
        expires_at=expires_at,
    )

    return CreateAPIKeyResponse(
        data=_key_to_out(api_key),
        apiKey=full_key,
        message="Store this API key securely. It will not be shown again.",
    )


@router.post("/api/api-keys/{key_id}/revoke")
async def revoke_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    api_key = await get_api_key_by_id(db, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Users can only revoke their own keys (unless superadmin)
    if api_key.user_id != current_user.id and current_user.role.value != "superadmin":
        raise HTTPException(status_code=403, detail="Cannot revoke another user's API key")

    await revoke_api_key(db, api_key)
    return {"message": "API key revoked", "status": "revoked"}


@router.get("/api/api-keys/{key_id}/usage")
async def get_key_usage(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get API key usage statistics."""
    api_key = await get_api_key_by_id(db, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if api_key.user_id != current_user.id and current_user.role.value != "superadmin":
        raise HTTPException(status_code=403, detail="Cannot view another user's API key usage")

    return {
        "id": api_key.id,
        "name": api_key.name,
        "requestsCount": str(api_key.request_count),
        "lastUsedAt": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "rateLimit": 100,
        "rateLimitWindow": "minute",
        "status": api_key.status.value,
    }


@router.post("/api/api-keys/validate")
async def validate_key(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate an API key (public endpoint, used by external services).
    Expects: {"apiKey": "ominis_..."}
    """
    from app.api_keys.service import validate_api_key as validate_fn

    api_key_str = body.get("apiKey", "")
    if not api_key_str:
        raise HTTPException(status_code=400, detail="apiKey is required")

    api_key = await validate_fn(db, api_key_str)
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    try:
        perms = json.loads(api_key.permissions) if api_key.permissions else {}
    except (json.JSONDecodeError, TypeError):
        perms = {}

    return {
        "valid": True,
        "userId": api_key.user_id,
        "permissions": perms,
        "keyPrefix": api_key.key_prefix,
    }
