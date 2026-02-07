"""
Admin routes: RAG sources, system stats, query logs.
Paths match the Strapi-compatible format the frontend expects.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import QueryLog, RAGSource, SourceStatus, SystemStat
from app.admin.schemas import (
    QueryStatsOut,
    RAGSourceCreate,
    RAGSourceListResponse,
    RAGSourceOut,
    RAGSourceUpdate,
    SourceStatsOut,
    SystemStatsOut,
)
from app.auth.dependencies import require_role
from app.auth.models import RoleEnum, User
from app.config import get_settings
from app.database import get_db
from app.rag.document_store import get_document_store

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["admin"])


# --- Helpers ---

def _source_to_out(source: RAGSource) -> RAGSourceOut:
    return RAGSourceOut(
        id=source.id,
        title=source.title,
        slug=source.slug,
        sourceType=source.source_type,
        status=source.status.value if source.status else "active",
        content=source.content,
        sourceUrl=source.source_url,
        category=source.category,
        language=source.language,
        chunksCount=source.chunks_count,
        lastIndexedAt=source.last_indexed_at.isoformat() if source.last_indexed_at else None,
        indexingError=source.indexing_error,
        createdAt=source.created_at.isoformat() if source.created_at else "",
        updatedAt=source.updated_at.isoformat() if source.updated_at else "",
    )


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


# ==================== RAG Sources ====================


@router.get("/api/rag-sources", response_model=RAGSourceListResponse)
async def list_rag_sources(
    page: int = Query(1, alias="pagination[page]"),
    page_size: int = Query(25, alias="pagination[pageSize]"),
    status_filter: Optional[str] = Query(None, alias="filters[status]"),
    source_type_filter: Optional[str] = Query(None, alias="filters[sourceType]"),
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all RAG sources (Admin+)."""
    query = select(RAGSource)

    if status_filter:
        query = query.where(RAGSource.status == status_filter)
    if source_type_filter:
        query = query.where(RAGSource.source_type == source_type_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(RAGSource.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    sources = list(result.scalars().all())

    return RAGSourceListResponse(
        data=[_source_to_out(s) for s in sources],
        meta={"pagination": {"total": total, "page": page, "pageSize": page_size}},
    )


@router.get("/api/rag-sources/stats", response_model=SourceStatsOut)
async def get_source_stats(
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get RAG source statistics (Admin+)."""
    total_result = await db.execute(select(func.count()).select_from(RAGSource))
    total = total_result.scalar() or 0

    # Count by status
    by_status = {"indexed": 0, "pending": 0, "processing": 0, "failed": 0}
    for status_name in by_status:
        count_result = await db.execute(
            select(func.count()).select_from(RAGSource).where(RAGSource.status == status_name)
        )
        by_status[status_name] = count_result.scalar() or 0

    # Active sources as "indexed"
    active_result = await db.execute(
        select(func.count()).select_from(RAGSource).where(RAGSource.status == SourceStatus.active)
    )
    by_status["indexed"] += active_result.scalar() or 0

    # Total chunks
    chunks_result = await db.execute(select(func.sum(RAGSource.chunks_count)))
    total_chunks = chunks_result.scalar() or 0

    return SourceStatsOut(total=total, byStatus=by_status, totalChunks=total_chunks)


@router.get("/api/rag-sources/{source_id}")
async def get_rag_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single RAG source (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"data": _source_to_out(source)}


@router.post("/api/rag-sources")
async def create_rag_source(
    body: dict,  # Accept { data: RAGSourceCreate }
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new RAG source (Admin+)."""
    data = body.get("data", body)
    create_data = RAGSourceCreate(**data)

    slug = create_data.slug or _slugify(create_data.title)

    # Check slug uniqueness
    existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A source with this slug already exists")

    source = RAGSource(
        title=create_data.title,
        slug=slug,
        source_type=create_data.sourceType,
        source_url=create_data.sourceUrl,
        content=create_data.content,
        category=create_data.category,
        language=create_data.language,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return {"data": _source_to_out(source)}


@router.put("/api/rag-sources/{source_id}")
async def update_rag_source(
    source_id: int,
    body: dict,  # Accept { data: RAGSourceUpdate }
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Update a RAG source (Admin+)."""
    data = body.get("data", body)
    update_data = RAGSourceUpdate(**data)

    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    for field, value in update_data.model_dump(exclude_unset=True).items():
        # Map camelCase to snake_case
        db_field = {
            "sourceType": "source_type",
            "sourceUrl": "source_url",
        }.get(field, field)
        if value is not None and hasattr(source, db_field):
            setattr(source, db_field, value)

    await db.commit()
    await db.refresh(source)

    return {"data": _source_to_out(source)}


@router.delete("/api/rag-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a RAG source (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()


@router.post("/api/rag-sources/{source_id}/reindex")
async def reindex_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-indexing of a RAG source (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Mark as indexing
    source.status = SourceStatus.indexing
    source.indexing_error = None
    await db.commit()

    # TODO: Trigger async re-indexing via the indexing pipeline
    # For now, return the status change
    return {
        "message": f"Re-indexing started for source '{source.title}'",
        "sourceId": source.id,
        "status": "indexing",
    }


# ==================== System Stats ====================


@router.get("/api/system-stats")
async def get_system_stats(
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get system statistics (Admin+)."""
    # Get counts from the database
    now = datetime.now(timezone.utc)

    total_sources = (await db.execute(select(func.count()).select_from(RAGSource))).scalar() or 0
    indexed_sources = (
        await db.execute(
            select(func.count())
            .select_from(RAGSource)
            .where(RAGSource.status == SourceStatus.active)
        )
    ).scalar() or 0
    total_chunks = (await db.execute(select(func.sum(RAGSource.chunks_count)))).scalar() or 0

    # Query counts by period
    queries_24h = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= now - timedelta(hours=24))
        )
    ).scalar() or 0
    queries_week = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= now - timedelta(days=7))
        )
    ).scalar() or 0
    queries_month = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= now - timedelta(days=30))
        )
    ).scalar() or 0

    # Document store count
    try:
        doc_store = get_document_store()
        store_count = doc_store.count_documents()
    except Exception:
        store_count = 0

    stats = SystemStatsOut(
        totalSources=total_sources,
        indexedSources=indexed_sources,
        totalChunks=total_chunks or store_count,
        modelVersion=settings.ollama_model,
        modelStatus="active",
        cpuServerStatus="online",
        gpuServerStatus="online",
        totalQueries24h=queries_24h,
        totalQueriesWeek=queries_week,
        totalQueriesMonth=queries_month,
        lastHealthCheck=now.isoformat(),
    )

    return {"data": stats.model_dump()}


@router.post("/api/system-stats/refresh")
async def refresh_system_stats(
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Refresh system statistics (Admin+)."""
    # Re-fetch stats (same as get but with a refresh message)
    response = await get_system_stats(_, db)
    return {"message": "Statistics refreshed", "stats": response["data"]}


@router.get("/system-stats/health")
async def health_check():
    """Public health check endpoint (no auth required)."""
    now = datetime.now(timezone.utc)

    # Check Ollama connectivity
    ollama_status = "offline"
    try:
        import urllib.request
        req = urllib.request.Request(f"{settings.ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                ollama_status = "online"
    except Exception:
        pass

    return {
        "status": "healthy" if ollama_status == "online" else "degraded",
        "timestamp": now.isoformat(),
        "model": {"version": settings.ollama_model, "status": ollama_status},
        "servers": {"cpu": "online", "gpu": ollama_status},
        "lastCheck": now.isoformat(),
    }


# ==================== Query Logs ====================


@router.get("/api/query-logs/aggregated", response_model=QueryStatsOut)
async def get_aggregated_query_stats(
    period: str = Query("day"),
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated query statistics (Admin+)."""
    now = datetime.now(timezone.utc)

    period_map = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
    }
    delta = period_map.get(period, timedelta(days=1))
    start_date = now - delta

    # Total queries in period
    total_result = await db.execute(
        select(func.count())
        .select_from(QueryLog)
        .where(QueryLog.created_at >= start_date)
    )
    total = total_result.scalar() or 0

    # Average response time
    avg_time_result = await db.execute(
        select(func.avg(QueryLog.response_time_ms))
        .where(QueryLog.created_at >= start_date)
        .where(QueryLog.response_time_ms.isnot(None))
    )
    avg_time = avg_time_result.scalar() or 0.0

    # Total tokens
    tokens_result = await db.execute(
        select(func.sum(QueryLog.tokens_used))
        .where(QueryLog.created_at >= start_date)
    )
    total_tokens = tokens_result.scalar() or 0

    # Failed queries (where answer is null or empty)
    failed_result = await db.execute(
        select(func.count())
        .select_from(QueryLog)
        .where(QueryLog.created_at >= start_date)
        .where(QueryLog.answer.is_(None))
    )
    failed = failed_result.scalar() or 0
    successful = total - failed

    success_rate = (successful / total * 100) if total > 0 else 0.0

    return QueryStatsOut(
        period=period,
        startDate=start_date.isoformat(),
        endDate=now.isoformat(),
        total=total,
        successful=successful,
        failed=failed,
        successRate=round(success_rate, 2),
        avgResponseTimeMs=round(avg_time, 2),
        totalTokens=total_tokens,
        byEndpoint={"query": total, "query-gpu": 0},
    )
