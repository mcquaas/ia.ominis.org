"""Authenticated search over All.Can organizations (Strapi REST)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_settings
from app.allcan_directory.strapi_client import fetch_organizations_all_pages
from app.directory_semantic import (
    allcan_org_blob,
    allcan_row_matches_filters,
    build_allcan_query_text,
    semantic_rank_by_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["allcan-directory"])


class AllCanSearchResponse(BaseModel):
    data: list[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)
    semantic: bool = False


@router.get("/allcan-directory/search", response_model=AllCanSearchResponse)
async def search_allcan_organizations(
    q: str = Query(default="", max_length=400),
    org_type: str = Query(default="", max_length=200, alias="type"),
    state: str = Query(default="", max_length=200),
    specialty: str = Query(default="", max_length=200),
    city: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=200),
    semantic: bool = Query(
        default=True,
        description="Rank by multilingual semantic similarity across name, specialty, location, etc.",
    ),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    settings = get_settings()
    base = (getattr(settings, "allcan_strapi_url", None) or "").strip().rstrip("/")
    token = (getattr(settings, "allcan_strapi_api_token", None) or "").strip()
    if not base or not token:
        return AllCanSearchResponse(data=[], meta={"error": "allcan_not_configured"}, semantic=False)

    try:
        rows = await fetch_organizations_all_pages(base, token, max_rows=500)
    except Exception as e:
        logger.warning("All.Can fetch error: %s", e)
        return AllCanSearchResponse(data=[], meta={"error": str(e)}, semantic=False)

    has_filter = bool(
        (q or "").strip()
        or (org_type or "").strip()
        or (state or "").strip()
        or (specialty or "").strip()
        or (city or "").strip()
    )

    if has_filter:
        filtered = [
            r for r in rows if allcan_row_matches_filters(r, q, org_type, state, specialty, city)
        ]
    else:
        filtered = list(rows)

    if semantic and has_filter and filtered:
        blobs = [allcan_org_blob(r) for r in filtered]
        qtext = build_allcan_query_text(q, org_type, state, specialty, city)
        try:
            ranked = await asyncio.to_thread(semantic_rank_by_query, qtext, blobs, len(blobs))
            order = [i for i, _ in ranked]
            filtered = [filtered[i] for i in order if i < len(filtered)]
        except Exception as e:
            logger.warning("All.Can semantic rank failed: %s", e)

    total = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

    return AllCanSearchResponse(
        data=page_rows,
        meta={
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "pageCount": (total + page_size - 1) // page_size if page_size else 1,
                "total": total,
            },
        },
        semantic=semantic,
    )
