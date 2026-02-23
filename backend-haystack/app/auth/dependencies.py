"""
FastAPI dependencies for authentication and authorization.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RoleEnum, User
from app.auth.service import decode_access_token, get_user_by_id
from app.database import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = int(payload.get("sub", 0))
    user = await get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None if not authenticated. Also accepts API key (e.g. chat.ominis.org)."""
    if credentials:
        try:
            return await get_current_user(credentials, db)
        except HTTPException:
            pass  # Not a valid JWT; may be API key set by middleware (Bearer <api_key>)
    # Chat.ominis.org and other API-key callers: treat valid API key as authenticated user
    api_key_user_id = getattr(request.state, "api_key_user_id", None)
    if api_key_user_id is not None:
        user = await get_user_by_id(db, api_key_user_id)
        if user and user.is_active:
            return user
    return None


def require_role(*roles: RoleEnum):
    """
    Dependency factory that checks if the user has one of the required roles.
    Supports role hierarchy: superadmin > admin > researcher.
    """

    ROLE_HIERARCHY = {
        RoleEnum.researcher: 0,
        RoleEnum.developer: 1,
        RoleEnum.admin: 2,
        RoleEnum.superadmin: 3,
    }

    async def _check_role(user: User = Depends(get_current_user)) -> User:
        # The minimum required level is the lowest of the allowed roles
        min_level = min(ROLE_HIERARCHY[r] for r in roles)
        user_level = ROLE_HIERARCHY.get(user.role, -1)

        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check_role
