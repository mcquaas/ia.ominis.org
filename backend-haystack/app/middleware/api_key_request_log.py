"""
Log last few HTTP request/response bodies for API-key-authenticated calls
(/v1/query, stream, chat completions) so the dashboard can show recent activity.
"""

import json
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from app.middleware.api_key_auth import API_KEY_PATHS

logger = logging.getLogger(__name__)


class APIKeyRequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        api_key_id = getattr(request.state, "api_key_id", None)
        path = request.url.path

        if api_key_id is None or request.method != "POST":
            return await call_next(request)

        if not any(path.startswith(p) for p in API_KEY_PATHS):
            return await call_next(request)

        full_body = await request.body()

        async def receive():
            return {"type": "http.request", "body": full_body, "more_body": False}

        request = Request(request.scope, receive)

        response = await call_next(request)

        stream_note = json.dumps(
            {
                "_note": "Respuesta en streaming (text/event-stream). El cuerpo completo no se registra aquí.",
                "path": path,
            },
            ensure_ascii=False,
            indent=2,
        )

        if isinstance(response, StreamingResponse):
            try:
                from app.api_keys.request_log_service import record_api_key_exchange
                from app.database import async_session

                async with async_session() as db:
                    await record_api_key_exchange(
                        db,
                        api_key_id=api_key_id,
                        method=request.method,
                        path=path,
                        status_code=response.status_code,
                        request_body_bytes=full_body,
                        response_body_text=stream_note,
                        response_truncated=False,
                        stream_response=True,
                    )
            except Exception as e:
                logger.warning("API key request log (stream) failed: %s", e)
            return response

        chunks: list[bytes] = []
        try:
            async for part in response.body_iterator:
                chunks.append(part)
        except Exception as e:
            logger.warning("API key log: could not read response body: %s", e)
            return response

        raw_resp = b"".join(chunks)

        from app.api_keys.request_log_service import MAX_RESPONSE_BYTES, record_api_key_exchange
        from app.database import async_session

        resp_trunc = len(raw_resp) > MAX_RESPONSE_BYTES
        log_slice = raw_resp[:MAX_RESPONSE_BYTES] if resp_trunc else raw_resp
        try:
            resp_text = log_slice.decode("utf-8")
        except UnicodeDecodeError:
            resp_text = log_slice.decode("utf-8", errors="replace")

        try:
            async with async_session() as db:
                await record_api_key_exchange(
                    db,
                    api_key_id=api_key_id,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    request_body_bytes=full_body,
                    response_body_text=resp_text,
                    response_truncated=resp_trunc,
                    stream_response=False,
                )
        except Exception as e:
            logger.warning("API key request log failed: %s", e)

        hdrs = {k: v for k, v in response.headers.items()}
        hdrs.pop("content-length", None)
        return Response(
            content=raw_resp,
            status_code=response.status_code,
            headers=hdrs,
            media_type=response.media_type,
        )
