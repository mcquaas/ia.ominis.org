"""Persist last few API-key HTTP exchanges for the dashboard."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys.models import APIKeyRequestLog

logger = logging.getLogger(__name__)

KEEP_LAST = 5
MAX_REQUEST_BYTES = 500_000
MAX_RESPONSE_BYTES = 500_000


def _bytes_to_log_text(raw: bytes, max_bytes: int) -> tuple[str, bool]:
    truncated = len(raw) > max_bytes
    chunk = raw[:max_bytes] if truncated else raw
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        text = chunk.decode("utf-8", errors="replace")
    return text, truncated


def _pretty_json_if_possible(text: str) -> str:
    t = text.strip()
    if not t:
        return text
    try:
        parsed = json.loads(t)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError, ValueError):
        return text


async def record_api_key_exchange(
    db: AsyncSession,
    *,
    api_key_id: int,
    method: str,
    path: str,
    status_code: int,
    request_body_bytes: bytes,
    response_body_text: str | None,
    response_truncated: bool,
    stream_response: bool,
) -> None:
    req_text, req_trunc = _bytes_to_log_text(request_body_bytes, MAX_REQUEST_BYTES)
    req_text = _pretty_json_if_possible(req_text)

    resp_text = response_body_text
    if resp_text is not None:
        resp_text = _pretty_json_if_possible(resp_text)

    row = APIKeyRequestLog(
        api_key_id=api_key_id,
        created_at=datetime.now(timezone.utc),
        method=method[:16],
        path=path[:512],
        status_code=status_code,
        request_body=req_text or None,
        response_body=resp_text,
        request_truncated=req_trunc,
        response_truncated=response_truncated,
        stream_response=stream_response,
    )
    db.add(row)
    await db.flush()

    r = await db.execute(
        select(APIKeyRequestLog.id)
        .where(APIKeyRequestLog.api_key_id == api_key_id)
        .order_by(APIKeyRequestLog.created_at.desc())
    )
    ids = [x[0] for x in r.all()]
    if len(ids) > KEEP_LAST:
        to_drop = ids[KEEP_LAST:]
        await db.execute(delete(APIKeyRequestLog).where(APIKeyRequestLog.id.in_(to_drop)))

    await db.commit()


async def list_recent_for_key(
    db: AsyncSession,
    api_key_id: int,
    *,
    limit: int = KEEP_LAST,
) -> list[APIKeyRequestLog]:
    r = await db.execute(
        select(APIKeyRequestLog)
        .where(APIKeyRequestLog.api_key_id == api_key_id)
        .order_by(APIKeyRequestLog.created_at.desc())
        .limit(limit)
    )
    return list(r.scalars().all())
