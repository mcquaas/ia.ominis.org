"""
Rate limiting middleware.
In-memory store (use Redis in production for multi-instance deployments).
"""

import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter.
    Tracks requests per IP or API key within a sliding window.
    """

    def __init__(self, app):
        super().__init__(app)
        self.max_requests = settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_window_seconds
        # {identifier: [timestamp, timestamp, ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_identifier(self, request: Request) -> str:
        """Get the rate limit identifier (API key or IP address)."""
        # Check for API key first
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"key:{api_key[:20]}"

        # Fall back to IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    def _clean_old_entries(self, identifier: str, now: float):
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[identifier] = [
            t for t in self._requests[identifier] if t > cutoff
        ]

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for health checks and OPTIONS
        if request.url.path.endswith("/health") or request.method == "OPTIONS":
            return await call_next(request)

        now = time.time()
        identifier = self._get_identifier(request)

        # Clean old entries
        self._clean_old_entries(identifier, now)

        current_count = len(self._requests[identifier])

        # Set rate limit headers
        remaining = max(0, self.max_requests - current_count)
        reset_time = int(now + self.window_seconds)

        if current_count >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {self.max_requests} per {self.window_seconds}s",
                },
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(self.window_seconds),
                },
            )

        # Record this request
        self._requests[identifier].append(now)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response
