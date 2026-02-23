"""
API Key authentication middleware.
Validates the X-API-Key header for programmatic access to query endpoints.
"""

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that require API key auth (when no JWT is present)
API_KEY_PATHS = [
    "/v1/query",
    "/v1/query-stream",
    "/v1/liveavatar/chat/completions",
    "/v1/chat/completions",
]


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that allows API key authentication for query endpoints.
    If a Bearer token is present, it takes precedence (handled by auth dependencies).
    If an X-API-Key header is present, validate and inject user info.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Only check API key paths
        path = request.url.path
        if not any(path.startswith(p) for p in API_KEY_PATHS):
            return await call_next(request)

        # API key can be in X-API-Key or in Authorization: Bearer <key> (e.g. LibreChat).
        # Do not treat Bearer tokens that look like JWTs as API keys (ia.ominis.org sends JWT).
        api_key_header = request.headers.get("X-API-Key", "").strip()
        if not api_key_header:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                # JWT has three base64 parts separated by dots; API keys do not
                if token.count(".") == 2:
                    return await call_next(request)
                api_key_header = token

        if not api_key_header:
            return await call_next(request)

        # Validate the API key
        try:
            from app.database import async_session
            from app.api_keys.service import validate_api_key

            async with async_session() as db:
                api_key = await validate_api_key(db, api_key_header)

            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid or expired API key"},
                )

            # Store validated key info in request state for downstream use
            request.state.api_key_id = api_key.id
            request.state.api_key_user_id = api_key.user_id

        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "API key validation failed"},
            )

        return await call_next(request)
