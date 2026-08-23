"""Fetch organizations from All.Can Strapi REST API."""

from __future__ import annotations

from typing import Any

import httpx


def _flatten_strapi_entry(item: dict) -> dict[str, Any]:
    if "attributes" in item and isinstance(item.get("attributes"), dict):
        base = {"id": item.get("id")}
        base.update(item["attributes"])
        return base
    return item


async def fetch_organizations_all_pages(base: str, token: str, max_rows: int = 500) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    page_size = min(200, max_rows)
    async with httpx.AsyncClient(timeout=60.0) as client:
        while len(out) < max_rows:
            params: list[tuple[str, str]] = [
                ("pagination[page]", str(page)),
                ("pagination[pageSize]", str(page_size)),
                ("sort[0]", "state:asc"),
                ("sort[1]", "name:asc"),
            ]
            url = f"{base.rstrip('/')}/api/organizations"
            r = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            payload = r.json()
            raw = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(raw, list) or not raw:
                break
            for item in raw:
                if isinstance(item, dict):
                    out.append(_flatten_strapi_entry(item))
            if len(raw) < page_size:
                break
            page += 1
    return out[:max_rows]


async def fetch_organization_total_count(base: str, token: str) -> int | None:
    """Return Strapi pagination total for organizations (first page only)."""
    base = base.rstrip("/")
    async with httpx.AsyncClient(timeout=45.0) as client:
        url = f"{base}/api/organizations"
        params = [("pagination[page]", "1"), ("pagination[pageSize]", "1")]
        r = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        meta = payload.get("meta") or {}
        pagination = meta.get("pagination") or {}
        total = pagination.get("total")
        if isinstance(total, int):
            return total
        return None
