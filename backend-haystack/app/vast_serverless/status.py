"""Optional diagnostics: list Vast Serverless endpoints and worker counts (uses vastai SDK on the dedicated loop)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import get_settings
from app.vast_serverless.runner import submit

logger = logging.getLogger(__name__)


def _api_key() -> str:
    s = get_settings()
    return (getattr(s, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()


async def _list_endpoints_async() -> dict[str, Any]:
    from vastai import Serverless

    key = _api_key()
    if not key:
        return {"error": "no_api_key", "endpoints": []}

    async with Serverless(api_key=key) as client:
        eps = await client.get_endpoints()
        out: list[dict[str, Any]] = []
        for ep in eps:
            row: dict[str, Any] = {"name": ep.name, "id": ep.id}
            try:
                workers = await client.get_endpoint_workers(ep)
                row["workers"] = len(workers) if workers else 0
            except Exception as ex:
                row["workers_error"] = str(ex)[:200]
                row["workers"] = None
            out.append(row)
        return {"endpoints": out}


def list_vast_serverless_endpoints_sync(timeout: float = 35.0) -> dict[str, Any]:
    """Sync wrapper for admin/diagnostics."""
    try:
        return submit(_list_endpoints_async(), timeout=timeout)
    except Exception as e:
        logger.warning("Vast Serverless list failed: %s", e)
        return {"error": str(e), "endpoints": []}
