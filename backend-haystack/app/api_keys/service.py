"""
API Key service: create, validate, revoke.
Uses the same ominis_<64-hex> format as the existing Strapi implementation.
"""

import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys.models import APIKey, APIKeyStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_key, key_hash, key_prefix).
    Format: ominis_<64-hex-characters>
    """
    raw = secrets.token_hex(32)  # 64 hex chars
    full_key = f"ominis_{raw}"
    key_hash = pwd_context.hash(full_key)
    key_prefix = f"ominis_{raw[:8]}"
    return full_key, key_hash, key_prefix


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return pwd_context.verify(plain_key, hashed_key)


async def create_api_key(
    db: AsyncSession,
    user_id: int,
    name: str,
    permissions: Optional[dict] = None,
    expires_at: Optional[datetime] = None,
) -> tuple[APIKey, str]:
    """
    Create a new API key for a user.
    Returns (api_key_model, full_key_string).
    """
    full_key, key_hash, key_prefix = generate_api_key()

    permissions_json = json.dumps(permissions or {"query": True, "queryGpu": True, "sources": False})

    api_key = APIKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user_id,
        permissions=permissions_json,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return api_key, full_key


async def validate_api_key(db: AsyncSession, plain_key: str) -> Optional[APIKey]:
    """
    Validate an API key by prefix lookup + bcrypt verification.
    Returns the APIKey model if valid, None otherwise.
    """
    if not plain_key.startswith("ominis_"):
        return None

    # Extract prefix for lookup (ominis_ + first 8 hex chars)
    prefix = f"ominis_{plain_key[7:15]}"

    result = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == prefix,
            APIKey.status == APIKeyStatus.active,
        )
    )
    candidates = list(result.scalars().all())

    for candidate in candidates:
        if verify_api_key(plain_key, candidate.key_hash):
            # Check expiration
            if candidate.expires_at and candidate.expires_at < datetime.now(timezone.utc):
                candidate.status = APIKeyStatus.expired
                await db.commit()
                return None

            # Update usage stats
            candidate.request_count += 1
            candidate.last_used_at = datetime.now(timezone.utc)
            await db.commit()

            return candidate

    return None


async def revoke_api_key(db: AsyncSession, api_key: APIKey) -> None:
    """Revoke an API key."""
    api_key.status = APIKeyStatus.revoked
    await db.commit()


async def get_user_api_keys(db: AsyncSession, user_id: int) -> list[APIKey]:
    """Get all API keys for a user."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc())
    )
    return list(result.scalars().all())


async def get_api_key_by_id(db: AsyncSession, key_id: int) -> Optional[APIKey]:
    """Get an API key by its ID."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    return result.scalar_one_or_none()
