"""
Admin routes: RAG sources, file upload, indexing, system stats, query logs.
Paths match the format the frontend expects.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status  # Query used for research-instances
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import ChatDefaults, LLMModelConfig, QueryLog, RAGSource, SiteConfig, SourceStatus, SystemStat
from app.admin.query_series import build_query_series
from app.admin.schemas import (
    AnalyticalQueryRequest,
    BatchReindexRequest,
    BatchReindexResponse,
    ChunkListResponse,
    ChunkOut,
    DatasetIndexRequest,
    DatasetIndexResponse,
    DatasetPreviewRequest,
    DatasetPreviewResponse,
    DatasetResourceItem,
    UrlsBatchRequest,
    UrlsBatchResponse,
    FileUploadResponse,
    QuerySeriesOut,
    QueryStatsOut,
    RAGSourceCreate,
    RAGSourceListResponse,
    RAGSourceOut,
    RAGSourceUpdate,
    ScrapeIndexRequest,
    ScrapeIndexResponse,
    ScrapePreviewResponse,
    ScrapeUrlRequest,
    ScrapedPdfItem,
    ScrapedFileItem,
    SourceStatsOut,
    StoreStatsOut,
    SystemStatsOut,
    TainacanImportRequest,
    TainacanImportResponse,
    TainacanPreviewResponse,
    DatosGobMxImportRequest,
    DatosGobMxImportResponse,
    DatosGobMxPreviewResponse,
    LLMListModelsRequest,
    LLMModelConfigOut,
    LLMModelConfigUpdate,
    VisionLlmConfigOut,
    VisionLlmConfigUpdate,
)
from app.admin.research_instances import (
    get_research_instance_status,
    start_research_instance,
    stop_research_instance,
)
from app.admin.llm_instances import (
    LlmInstanceKey,
    get_llm_instance_status,
    start_llm_instance,
    stop_llm_instance,
)
from app.admin.server_groups import get_ecosystem_servers_checklist, get_servers_status
from app.allcan_directory.strapi_client import fetch_organization_total_count
from app.doctor_directory.models import DoctorDirectoryProfile, DoctorDirectoryScrapeRun, DoctorScrapeStatus
from app.admin.dashboard_helpers import (
    fetch_clinicaltrials_study_count,
    fetch_pubmed_record_count,
    server_row_level,
    source_level_ok_count,
)
from app.auth.dependencies import require_role
from app.auth.models import RoleEnum, User
from app.admin.llm_crypto import decrypt_credentials_blob, merge_credential_patch
from app.admin.llm_list_models import list_models_for_provider
from app.admin.llm_provider_registry import list_provider_ids
from app.config import get_settings, get_model_registry, invalidate_model_registry, normalize_public_model_id
from app.database import get_db
from app.rag.document_store import get_document_store

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["admin"])

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm", ".csv", ".xlsx", ".xls", ".sav", ".zip"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_CRAWL_PAGES = 50

# Dashboard logical IDs for Modo Investigación (OpenScholar) backend mapping — stored in llm_model_config, not chat registry
RESEARCH_ROUTING_MODEL_IDS = frozenset({"research-8k", "research-128k"})


def _mapped_default_model_availability(
    health: dict,
    default_model_id: str,
    cfg_row: LLMModelConfig | None,
) -> tuple[bool, str]:
    """Whether the chat default model can be served, and a short Spanish detail string."""
    mid = normalize_public_model_id(default_model_id or "ominis-2.0")
    sum_ = health.get("inference_summary") or {}
    ollama_def = (sum_.get("ollama_default") or "").lower()
    clinic_on = (sum_.get("ollama_clinic") or "").lower() == "online"

    if mid in RESEARCH_ROUTING_MODEL_IDS:
        ri = get_research_instance_status()
        vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
        if mid == "research-8k":
            vast_ok = bool((getattr(settings, "vast_serverless_openscholar_endpoint", "") or "").strip() and vk)
            run = (ri.get("openscholar") or "").lower() == "running"
            if vast_ok or run:
                return True, "Vast 8K" if vast_ok and not run else "GPU EC2 8K activo"
            return False, "Investigación 8K sin GPU ni Vast"
        vast_ok = bool((getattr(settings, "vast_serverless_openscholar_128k_endpoint", "") or "").strip() and vk)
        run = (ri.get("openscholar_128k") or "").lower() == "running"
        if vast_ok or run:
            return True, "Vast 128K" if vast_ok and not run else "GPU EC2 128K activo"
        return False, "Investigación 128K sin GPU ni Vast"

    provider = (cfg_row.llm_provider or "ominis").strip().lower() if cfg_row else "ominis"
    if provider != "ominis":
        keys = _provider_keys_present(cfg_row)
        if keys.get(provider, False):
            return True, f"API ({provider})"
        if any(keys.values()):
            return True, "API (credenciales de otro proveedor)"
        return False, f"Sin credenciales {provider}"

    if ollama_def in ("online", "serverless") or clinic_on:
        return True, "Ollama/Vast" if ollama_def in ("online", "serverless") else "Ollama clínica"
    if int(sum_.get("third_party_models") or 0) > 0:
        return True, "Ruta API de respaldo"
    return False, "Sin Ollama ni API"


def _provider_keys_present(row: LLMModelConfig | None) -> dict[str, bool]:
    keys = ["ominis", "openai", "google", "deepseek", "claude"]
    if not row or not getattr(row, "provider_credentials_enc", None):
        return {k: False for k in keys}
    creds = decrypt_credentials_blob(row.provider_credentials_enc)
    return {k: bool((creds.get(k) or "").strip()) for k in keys}


def _effective_llm_provider(row: LLMModelConfig | None, cfg) -> str:
    if row and getattr(row, "llm_provider", None):
        return str(row.llm_provider)
    if getattr(cfg, "use_anthropic", False):
        return "claude"
    pid = getattr(cfg, "llm_provider", "") or ""
    if pid and pid != "ominis":
        return pid
    if getattr(cfg, "use_openai", False):
        return "openai"
    return "ominis"


def _vision_provider_keys_present(row: SiteConfig | None) -> dict[str, bool]:
    keys = ["ominis", "openai", "google", "deepseek", "claude"]
    if not row or not getattr(row, "vision_credentials_enc", None):
        return {k: False for k in keys}
    creds = decrypt_credentials_blob(row.vision_credentials_enc)
    return {k: bool((creds.get(k) or "").strip()) for k in keys}


def _backend_type_for_cfg(cfg) -> str:
    if getattr(cfg, "use_anthropic", False):
        return "anthropic"
    if getattr(cfg, "use_openai", False):
        return "openai"
    return "ollama"


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
        description=source.description,
        publisher=source.publisher,
        documentDate=source.document_date,
        taxonomy=source.taxonomy,
        chunksCount=source.chunks_count,
        lastIndexedAt=source.last_indexed_at.isoformat() if source.last_indexed_at else None,
        indexingError=source.indexing_error,
        createdAt=source.created_at.isoformat() if source.created_at else "",
        updatedAt=source.updated_at.isoformat() if source.updated_at else "",
    )


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from text, truncated to fit VARCHAR(255)."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:240]


def _safe_title(text: str, max_len: int = 250) -> str:
    """Truncate a title to fit VARCHAR(255) safely."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


# Crawl: fetch seed URLs and same-domain links (for urls-batch with crawl=True)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _html_to_text(html: str) -> str:
    t = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<style[^>]*>.*?</style>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:300_000]


def _crawl_urls_sync(seed_urls: list[str], max_pages: int) -> list[dict]:
    """Fetch seed URLs and optionally same-domain links; return list of {url, title, text}."""
    to_fetch: set[str] = set()
    for u in seed_urls:
        u = (u or "").strip()
        if not u or not u.startswith(("http://", "https://")):
            continue
        to_fetch.add(u)
    results: list[dict] = []
    fetched: set[str] = set()
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while to_fetch and len(results) < max_pages:
            url = to_fetch.pop()
            if url in fetched:
                continue
            fetched.add(url)
            try:
                r = client.get(url)
                r.raise_for_status()
                body = r.text
            except Exception as e:
                logger.warning("Crawl fetch %s: %s", url[:60], e)
                continue
            ct = r.headers.get("content-type", "")
            if "text/html" not in ct:
                continue
            text = _html_to_text(body)
            if len(text) < 50:
                continue
            title = urlparse(url).path.rstrip("/").split("/")[-1] or url[:80]
            results.append({"url": url, "title": title, "text": text[:300_000]})
            # Discover same-domain links
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            for m in _HREF_RE.finditer(body):
                href = m.group(1).strip().split("#")[0].split("?")[0]
                if not href or href.startswith(("mailto:", "tel:")):
                    continue
                try:
                    full = urljoin(url, href)
                    if urlparse(full).netloc.lower() == netloc and full not in fetched:
                        to_fetch.add(full)
                except Exception:
                    pass
    return results


async def _extract_and_save_metadata(source_id: int, kwargs: dict):
    """
    Use the LLM to extract metadata (title, publisher, date, description)
    from the indexed document content and save to the RAGSource record.
    Best-effort: failures don't affect the indexing status.
    """
    from app.database import async_session

    try:
        from app.rag.metadata_extractor import extract_document_metadata
        from app.rag.pipeline import get_pipeline_manager

        manager = get_pipeline_manager()
        generator = manager.get_generator()

        # Collect a content snippet for analysis
        content_snippet = ""

        # Try to get content from the source record or from kwargs
        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if not source:
                return

            if source.content:
                content_snippet = source.content[:2500]

        # If no content stored, try to get it from pgvector chunks
        if not content_snippet:
            from app.rag.indexing import get_source_chunks
            chunks = await asyncio.to_thread(get_source_chunks, source_id, limit=5, offset=0)
            if chunks:
                content_snippet = "\n\n".join([(c.content or "")[:500] for c in chunks])

        if not content_snippet:
            return

        url = kwargs.get("url", "") or kwargs.get("source_url", "")
        filename = ""
        if "file_path" in kwargs:
            filename = Path(kwargs["file_path"]).name

        meta = await extract_document_metadata(
            content_snippet=content_snippet,
            url=url,
            filename=filename,
            generator=generator,
        )

        # Also extract taxonomy (researcher classification)
        from app.rag.metadata_extractor import extract_taxonomy

        taxonomy = {}
        try:
            taxonomy = await extract_taxonomy(
                content_snippet=content_snippet,
                url=url,
                title=meta.get("title", ""),
                generator=generator,
            )
        except Exception as e:
            logger.warning(f"Taxonomy extraction failed for source {source_id}: {e}")

        if meta or taxonomy:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    if meta:
                        if meta.get("title") and (not source.title or len(source.title) < 5):
                            source.title = _safe_title(meta["title"])
                        if meta.get("publisher") and not source.publisher:
                            source.publisher = meta["publisher"][:250]
                        if meta.get("document_date") and not source.document_date:
                            source.document_date = meta["document_date"][:100]
                        if meta.get("description") and not source.description:
                            source.description = meta["description"][:500]
                    if taxonomy:
                        source.taxonomy = taxonomy
                    await db.commit()
                    logger.info(f"Metadata saved for source {source_id}: {meta.get('title', '')[:40]}")

    except Exception as e:
        logger.warning(f"Metadata extraction failed for source {source_id}: {e}")


async def _run_indexing_in_background(source_id: int, method: str, **kwargs):
    """
    Run indexing in a background thread and update the RAGSource record.
    method: 'file', 'text', or 'url'
    """
    from app.database import async_session

    try:
        meta = kwargs.get("meta", {})
        taxonomy = kwargs.get("taxonomy") or meta.get("taxonomy")

        if method == "file":
            from app.rag.indexing import index_file_with_meta
            if taxonomy:
                meta = {**meta, "taxonomy": taxonomy}
            chunks = await asyncio.to_thread(
                index_file_with_meta,
                file_path=kwargs["file_path"],
                source_id=source_id,
                meta=meta,
            )
        elif method == "text":
            from app.rag.indexing import index_raw_text
            chunks = await asyncio.to_thread(
                index_raw_text,
                content=kwargs["content"],
                source_id=source_id,
                title=kwargs.get("title", ""),
                url=kwargs.get("url", ""),
                source_type=kwargs.get("rag_source_type", "rag"),
                category=kwargs.get("category", ""),
                language=kwargs.get("language", "es"),
                taxonomy=taxonomy,
            )
        elif method == "url":
            from app.rag.indexing import index_from_url
            chunks = await index_from_url(
                url=kwargs["url"],
                source_id=source_id,
                title=kwargs.get("title", ""),
                category=kwargs.get("category", ""),
                language=kwargs.get("language", "es"),
                taxonomy=taxonomy,
            )
        else:
            raise ValueError(f"Unknown indexing method: {method}")

        # Update the source record
        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if source:
                source.status = SourceStatus.active
                source.chunks_count = chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Source {source_id} indexed: {chunks} chunks")

    except Exception as e:
        logger.error(f"Indexing failed for source {source_id}: {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    source.status = SourceStatus.error
                    source.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update source status: {db_err}")

        # Clean up temp file on error too
        if method == "file" and "file_path" in kwargs:
            Path(kwargs["file_path"]).unlink(missing_ok=True)
        return

    # Post-success only: must never set status=error (e.g. SAV parquet or temp cleanup failing).
    try:
        await _extract_and_save_metadata(source_id, kwargs)
    except Exception as e:
        logger.warning(f"Post-index metadata extraction for source {source_id}: {e}")

    try:
        if method == "file" and "file_path" in kwargs:
            fp = Path(kwargs["file_path"])
            if fp.suffix.lower() == ".sav" and get_settings().analytical_data_dir:
                from app.rag.analytical import save_sav_as_parquet

                await asyncio.to_thread(save_sav_as_parquet, str(fp), source_id)
            fp.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Post-index file cleanup / SAV export for source {source_id}: {e}")


# ==================== RAG Sources ====================


@router.get("/api/rag-sources", response_model=RAGSourceListResponse)
async def list_rag_sources(
    page: int = Query(1, alias="pagination[page]"),
    page_size: int = Query(25, alias="pagination[pageSize]"),
    status_filter: Optional[str] = Query(None, alias="filters[status]"),
    source_type_filter: Optional[str] = Query(None, alias="filters[sourceType]"),
    taxonomy_filter: Optional[str] = Query(None, alias="filters[taxonomy]"),
    search: Optional[str] = Query(None, alias="filters[search]"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """List all RAG sources (Admin+). Supports taxonomy and text search filters."""
    query = select(RAGSource)

    if status_filter:
        query = query.where(RAGSource.status == status_filter)
    if source_type_filter:
        query = query.where(RAGSource.source_type == source_type_filter)

    # Taxonomy filter: JSON like {"institucion":["SSA","IMSS"],"tipo_documento":["guia_clinica"]}
    # Each dimension: source must have at least one of the filter values (OR within dimension)
    if taxonomy_filter:
        try:
            tax = json.loads(taxonomy_filter)
            if isinstance(tax, dict):
                for dim, values in tax.items():
                    if values and isinstance(values, list):
                        if len(values) == 1:
                            query = query.where(RAGSource.taxonomy.op("@>")({dim: values}))
                        else:
                            # OR: taxonomy contains any of the values
                            dim_conds = [RAGSource.taxonomy.op("@>")({dim: [v]}) for v in values]
                            query = query.where(or_(*dim_conds))
        except (json.JSONDecodeError, TypeError):
            pass

    # Text search in title, description, publisher (coalesce nulls for ILIKE)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                RAGSource.title.ilike(term),
                func.coalesce(RAGSource.description, "").ilike(term),
                func.coalesce(RAGSource.publisher, "").ilike(term),
            )
        )

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


@router.get("/api/rag-sources/taxonomy-schema")
async def get_taxonomy_schema(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """Return the taxonomy dimensions and valid values for researcher classification."""
    from app.rag.taxonomy import RAG_TAXONOMY
    return {"taxonomy": RAG_TAXONOMY}


@router.get("/api/rag-sources/taxonomy-stats")
async def get_taxonomy_stats(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated counts by taxonomy dimensions (institucion, tipo_documento)."""
    result = {}
    for dim in ("institucion", "tipo_documento"):
        # Safe: dim is from fixed set
        sql = text(f"""
            SELECT v AS value, count(*)::int AS cnt
            FROM rag_sources,
                 jsonb_array_elements_text(taxonomy->'{dim}') AS v
            WHERE taxonomy IS NOT NULL
              AND taxonomy->'{dim}' IS NOT NULL
              AND jsonb_typeof(taxonomy->'{dim}') = 'array'
            GROUP BY v
            ORDER BY cnt DESC
        """)
        rows = (await db.execute(sql)).fetchall()
        result[dim] = {r.value: r.cnt for r in rows}
    return {"taxonomyStats": result}


@router.get("/api/rag-sources/stats", response_model=SourceStatsOut)
async def get_source_stats(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Get RAG source statistics (Admin+)."""
    total_result = await db.execute(select(func.count()).select_from(RAGSource))
    total = total_result.scalar() or 0

    by_status = {"indexed": 0, "pending": 0, "processing": 0, "failed": 0}
    for status_name in by_status:
        count_result = await db.execute(
            select(func.count()).select_from(RAGSource).where(RAGSource.status == status_name)
        )
        by_status[status_name] = count_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).select_from(RAGSource).where(RAGSource.status == SourceStatus.active)
    )
    by_status["indexed"] += active_result.scalar() or 0

    chunks_result = await db.execute(select(func.sum(RAGSource.chunks_count)))
    total_chunks = chunks_result.scalar() or 0

    return SourceStatsOut(total=total, byStatus=by_status, totalChunks=total_chunks)


@router.get("/api/rag-sources/store-stats", response_model=StoreStatsOut)
async def get_store_stats_endpoint(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """Get document store statistics (Admin+)."""
    from app.rag.indexing import get_store_stats
    stats = get_store_stats()
    return StoreStatsOut(**stats)


# ==================== Tainacan Import ====================


@router.get("/api/rag-sources/tainacan-preview", response_model=TainacanPreviewResponse)
async def tainacan_preview(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """Preview Tainacan collection — shows item count and file type breakdown."""
    from app.rag.tainacan_importer import preview_collection

    try:
        result = await preview_collection()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Tainacan data: {e}")

    return TainacanPreviewResponse(
        totalItems=result["totalItems"],
        indexableFiles=result["indexableFiles"],
        metadataOnly=result["metadataOnly"],
        byExtension=result["byExtension"],
    )


@router.post("/api/rag-sources/tainacan-import", response_model=TainacanImportResponse)
async def tainacan_import(
    body: TainacanImportRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Import all items from Tainacan collection 97 into the RAG system.
    Creates a RAGSource for each item and triggers background indexing.
    """
    from app.rag.tainacan_importer import fetch_all_items

    try:
        items = await fetch_all_items(max_items=body.maxItems)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Tainacan data: {e}")

    if not items:
        raise HTTPException(status_code=404, detail="No items found in Tainacan collection")

    # Check existing sources to skip duplicates
    existing_tainacan_ids = set()
    if body.skipExisting:
        result = await db.execute(
            select(RAGSource).where(RAGSource.source_type == "tainacan")
        )
        for source in result.scalars().all():
            existing_tainacan_ids.add(source.slug)

    queued = 0
    skipped = 0

    # Process in batches to avoid overwhelming the DB
    BATCH_SIZE = 50
    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start : batch_start + BATCH_SIZE]
        batch_sources = []

        for item in batch:
            title = _safe_title(item.get("title", "Untitled"))
            slug = _slugify(title)
            tainacan_id = item.get("tainacan_id")

            # Skip if already imported
            tainacan_slug = f"tainacan-{tainacan_id}"
            if body.skipExisting and (slug in existing_tainacan_ids or tainacan_slug in existing_tainacan_ids):
                skipped += 1
                continue

            # Ensure unique slug
            existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
            if existing.scalar_one_or_none():
                slug = tainacan_slug

            existing2 = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
            if existing2.scalar_one_or_none():
                slug = f"{tainacan_slug}-{int(time.time())}"

            download_url = item.get("download_url", "")
            meta_info = item.get("meta", {})

            source = RAGSource(
                title=title,
                slug=slug,
                source_type="tainacan",
                source_url=download_url,
                content=meta_info.get("description", "")[:5000] if meta_info.get("description") else None,
                status=SourceStatus.indexing,
                category=body.category or meta_info.get("taxonomy", "tainacan"),
                language=body.language,
            )
            db.add(source)
            await db.flush()

            batch_sources.append((source.id, item))
            existing_tainacan_ids.add(slug)
            queued += 1

        await db.commit()

        # Launch background tasks for this batch
        for source_id, item in batch_sources:
            asyncio.create_task(_run_tainacan_item_index(source_id, item))

        logger.info(f"Tainacan import: queued batch {batch_start}-{batch_start + len(batch)}, "
                     f"total queued={queued}, skipped={skipped}")

    return TainacanImportResponse(
        message=f"Queued {queued} items for indexing from Tainacan ({skipped} skipped as existing)",
        totalQueued=queued,
        skipped=skipped,
    )


# ==================== datos.gob.mx (CKAN) metadata import ====================


@router.get("/api/rag-sources/datos-gob-mx-preview", response_model=DatosGobMxPreviewResponse)
async def datos_gob_mx_preview(
    group: str = Query(default="salud", max_length=64),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """
    Preview CKAN datasets in a group (default: salud) via datos.gob.mx API.
    Indexing uses metadata + resource URLs only (not CSV row content).
    """
    from app.rag.datos_gob_mx import preview_group

    try:
        result = await preview_group(group_name=group.strip() or "salud", sample_size=12)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch datos.gob.mx CKAN: {e}") from e

    return DatosGobMxPreviewResponse(
        totalPackages=result["totalPackages"],
        groupName=result["groupName"],
        groupTitle=result["groupTitle"],
        totalResourcesSample=result["totalResourcesSample"],
        resourceFormatsSample=result["resourceFormatsSample"],
        sampleTitles=result["sampleTitles"],
    )


@router.post("/api/rag-sources/datos-gob-mx-import", response_model=DatosGobMxImportResponse)
async def datos_gob_mx_import(
    body: DatosGobMxImportRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Import CKAN dataset metadata from datos.gob.mx into RAG (one RAG source per dataset).
    Does not download CSV/XLS content — only descriptions and download links for retrieval.
    """
    from app.rag.datos_gob_mx import fetch_packages_for_group, portal_dataset_url

    group = (body.group or "salud").strip() or "salud"
    try:
        packages = await fetch_packages_for_group(group_name=group, max_items=body.maxItems)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch datos.gob.mx CKAN: {e}") from e

    if not packages:
        raise HTTPException(status_code=404, detail="No datasets returned for this CKAN group")

    existing_slugs: set[str] = set()
    if body.skipExisting:
        result = await db.execute(select(RAGSource).where(RAGSource.source_type == "datos_gob_mx"))
        for source in result.scalars().all():
            existing_slugs.add(source.slug)

    queued = 0
    skipped = 0
    BATCH_SIZE = 40

    for batch_start in range(0, len(packages), BATCH_SIZE):
        batch = packages[batch_start : batch_start + BATCH_SIZE]
        batch_sources: list[tuple[int, dict]] = []

        for pkg in batch:
            name = (pkg.get("name") or "").strip() or pkg.get("id", "")
            slug = _slugify(f"dgmx-{group}-{name}")[:255]
            if not slug or slug == "dgmx":
                slug = _slugify(f"dgmx-{group}-{pkg.get('id', uuid.uuid4().hex)[:16]}")[:255]

            if body.skipExisting and slug in existing_slugs:
                skipped += 1
                continue

            existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            title = _safe_title(pkg.get("title") or name or "Dataset")
            notes = (pkg.get("notes") or "").strip()
            org = pkg.get("organization") or {}
            portal_url = portal_dataset_url(pkg)

            source = RAGSource(
                title=title,
                slug=slug,
                source_type="datos_gob_mx",
                source_url=portal_url,
                content=notes[:5000] if notes else None,
                status=SourceStatus.indexing,
                category=body.category,
                language=body.language,
                publisher=(org.get("title") or "")[:255] if org.get("title") else None,
                description=notes[:2000] if notes else None,
                document_date=(pkg.get("metadata_modified") or "")[:100] or None,
            )
            db.add(source)
            await db.flush()
            batch_sources.append((source.id, pkg))
            existing_slugs.add(slug)
            queued += 1

        await db.commit()

        for source_id, pkg in batch_sources:
            asyncio.create_task(
                _run_datos_gob_mx_dataset_index(
                    source_id,
                    pkg,
                    category=body.category,
                    language=body.language,
                    ckan_group=group,
                )
            )

        logger.info(
            "datos.gob.mx import: batch %s-%s queued=%s total_queued=%s skipped=%s",
            batch_start,
            batch_start + len(batch),
            len(batch_sources),
            queued,
            skipped,
        )

    return DatosGobMxImportResponse(
        message=f"Queued {queued} CKAN datasets for metadata indexing ({skipped} skipped)",
        totalQueued=queued,
        skipped=skipped,
    )


async def _run_datos_gob_mx_dataset_index(
    source_id: int,
    pkg: dict,
    *,
    category: str,
    language: str,
    ckan_group: str,
):
    from app.rag.datos_gob_mx import build_index_text, portal_dataset_url

    org_name = (pkg.get("organization") or {}).get("title")
    taxonomy: dict = {
        "portal": ["datos.gob.mx"],
        "grupo_ckan": [ckan_group],
        "tipo_documento": ["dataset_abierto_gobmx"],
    }
    if org_name:
        taxonomy["institucion"] = [str(org_name)[:200]]
    tag_names = [str(t.get("name") or "").strip() for t in (pkg.get("tags") or []) if t.get("name")]
    if tag_names:
        taxonomy["etiquetas"] = tag_names[:40]

    await _run_indexing_in_background(
        source_id,
        "text",
        content=build_index_text(pkg),
        title=_safe_title(pkg.get("title") or pkg.get("name") or "Dataset"),
        url=portal_dataset_url(pkg),
        category=category,
        language=language,
        taxonomy=taxonomy,
        rag_source_type="datos_gob_mx",
    )


async def _run_tainacan_item_index(source_id: int, item: dict):
    """Background task: download + index a single Tainacan item."""
    from app.database import async_session
    from app.rag.tainacan_importer import index_single_item

    try:
        sem = asyncio.Semaphore(3)
        chunks = await index_single_item(item, source_id, concurrency_semaphore=sem)

        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if source:
                source.status = SourceStatus.active
                source.chunks_count = chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Tainacan source {source_id} indexed: {chunks} chunks")

    except Exception as e:
        logger.error(f"Tainacan indexing failed for source {source_id}: {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    source.status = SourceStatus.error
                    source.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update Tainacan source status: {db_err}")


# ==================== URL Scraping (Bulk PDF Discovery) ====================


@router.post("/api/rag-sources/scrape-preview", response_model=ScrapePreviewResponse)
async def scrape_preview(
    body: ScrapeUrlRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """
    Preview: Scrape a URL for PDF, CSV, XLS, XLSX links (without downloading/indexing).
    Returns unified 'files' with format per item; 'pdfs' kept for backward compatibility.
    """
    from app.rag.scraper import scrape_file_links

    try:
        file_links = await scrape_file_links(body.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scrape URL: {e}")

    pdfs = [f for f in file_links if f.get("format", "").lower() == "pdf"]
    return ScrapePreviewResponse(
        url=body.url,
        totalPdfs=len(pdfs),
        pdfs=[
            ScrapedPdfItem(
                title=p["title"],
                pdfUrl=p["file_url"],
                sourcePage=p["source_page"],
            )
            for p in pdfs
        ],
        totalFiles=len(file_links),
        files=[
            ScrapedFileItem(
                title=f["title"],
                fileUrl=f["file_url"],
                sourcePage=f["source_page"],
                format=f.get("format", "pdf"),
            )
            for f in file_links
        ],
    )


@router.post("/api/rag-sources/scrape-index", response_model=ScrapeIndexResponse)
async def scrape_and_index(
    body: ScrapeIndexRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Scrape a URL for PDF/CSV/XLS/XLSX links (or use provided list), create RAG sources,
    and trigger background indexing. Each file becomes its own RAG source with correct type.
    """
    from app.rag.scraper import scrape_file_links

    try:
        if body.files:
            file_list = [
                {"title": f.title, "file_url": f.fileUrl, "source_page": f.sourcePage, "format": (f.format or "pdf").lower()}
                for f in body.files
            ]
        elif body.pdfs:
            file_list = [
                {"title": p.title, "file_url": p.pdfUrl, "source_page": p.sourcePage, "format": "pdf"}
                for p in body.pdfs
            ]
        else:
            try:
                file_list = await scrape_file_links(body.url)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to scrape URL: {e}")

        if not file_list:
            raise HTTPException(status_code=404, detail="No PDF/CSV/XLS links found on the page")

        created_sources = []
        ts = int(time.time())
        category = body.category or "scraped"
        language = body.language

        for idx, file_info in enumerate(file_list):
            title = _safe_title(file_info["title"])
            file_url = file_info["file_url"]
            file_format = (file_info.get("format") or "pdf").lower()
            source_type = file_format if file_format in ("pdf", "csv", "xls", "xlsx") else "dataset"

            base = _slugify(title) or source_type
            base = base[:230]
            slug = f"{base}-{ts}-{idx}"

            existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
            if existing.scalar_one_or_none():
                slug = f"{base}-{ts}-{idx}-{uuid.uuid4().hex[:8]}"

            source = RAGSource(
                title=title,
                slug=slug,
                source_type=source_type,
                source_url=file_url,
                status=SourceStatus.indexing,
                category=category,
                language=language,
            )
            db.add(source)
            await db.flush()

            created_sources.append({
                "sourceId": source.id,
                "title": title,
                "pdfUrl": file_url,
                "fileUrl": file_url,
                "format": file_format,
                "status": "indexing",
            })

        await db.commit()

        for info in created_sources:
            asyncio.create_task(_run_file_download_and_index(
                source_id=info["sourceId"],
                file_url=info["fileUrl"],
                title=info["title"],
                category=category,
                language=language,
                file_format=info["format"],
            ))

        return ScrapeIndexResponse(
            message=f"Queued {len(created_sources)} files for indexing from {body.url}",
            totalQueued=len(created_sources),
            sources=created_sources,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("scrape-index failed: %s", e)
        msg = str(e)[:200]
        if "UniqueViolation" in type(e).__name__ or "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail="Algunos PDFs generan el mismo identificador. Intenta de nuevo o indexa en lotes más pequeños.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error al indexar PDFs: {msg}. Revisa los logs del servidor.",
        )


async def _run_pdf_download_and_index(
    source_id: int,
    pdf_url: str,
    title: str,
    category: str,
    language: str,
    taxonomy: dict | None = None,
):
    """Download a PDF from URL and index it, updating the RAG source record."""
    from app.database import async_session
    from app.rag.scraper import download_pdf

    tmp_path = None
    try:
        # Download PDF
        tmp_path, file_size = await download_pdf(pdf_url)
        logger.info(f"Downloaded PDF '{title}' ({file_size} bytes) for source {source_id}")

        # Index it
        from app.rag.indexing import index_file_with_meta
        meta = {
            "title": title,
            "url": pdf_url,
            "source_type": "rag",
            "category": category,
            "language": language,
        }
        if taxonomy:
            meta["taxonomy"] = taxonomy
        chunks = await asyncio.to_thread(
            index_file_with_meta,
            file_path=str(tmp_path),
            source_id=source_id,
            meta=meta,
        )

        # Update source record
        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if source:
                source.status = SourceStatus.active
                source.chunks_count = chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Source {source_id} ('{title}'): indexed {chunks} chunks from PDF")

        # Extract metadata using LLM
        await _extract_and_save_metadata(source_id, {"url": pdf_url, "file_path": str(tmp_path) if tmp_path else ""})

    except Exception as e:
        logger.error(f"Failed to index PDF '{title}' (source {source_id}): {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    source.status = SourceStatus.error
                    source.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update source status: {db_err}")
    finally:
        if tmp_path:
            Path(str(tmp_path)).unlink(missing_ok=True)


async def _run_file_download_and_index(
    source_id: int,
    file_url: str,
    title: str,
    category: str,
    language: str,
    file_format: str,
):
    """Download a file (PDF, CSV, XLS, XLSX) from URL and index it."""
    from app.database import async_session
    from app.rag.scraper import download_pdf, download_file

    tmp_path = None
    try:
        if file_format == "pdf":
            tmp_path, file_size = await download_pdf(file_url)
        else:
            tmp_path, file_size, ext = await download_file(file_url)
            file_format = ext or file_format

        logger.info(f"Downloaded '{title}' ({file_size} bytes, .{file_format}) for source {source_id}")

        from app.rag.indexing import index_file_with_meta
        meta = {
            "title": title,
            "url": file_url,
            "source_type": "rag",
            "category": category,
            "language": language,
        }
        chunks = await asyncio.to_thread(
            index_file_with_meta,
            file_path=str(tmp_path),
            source_id=source_id,
            meta=meta,
        )

        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if source:
                source.status = SourceStatus.active
                source.chunks_count = chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Source {source_id} ('{title}'): indexed {chunks} chunks")

        if file_format == "pdf":
            await _extract_and_save_metadata(source_id, {"url": file_url, "file_path": str(tmp_path) if tmp_path else ""})

    except Exception as e:
        logger.error(f"Failed to index file '{title}' (source {source_id}): {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    source.status = SourceStatus.error
                    source.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update source status: {db_err}")
    finally:
        if tmp_path:
            Path(str(tmp_path)).unlink(missing_ok=True)


# ==================== Dataset Page Scraping (CSV/XLS/PDF from data portals) ====================


@router.post("/api/rag-sources/dataset-preview", response_model=DatasetPreviewResponse)
async def dataset_preview(
    body: DatasetPreviewRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """
    Preview: Scrape a dataset page (datos.gob.mx, CKAN, etc.) and return all
    downloadable resources with metadata, without indexing.
    """
    from app.rag.scraper import scrape_dataset_resources

    try:
        result = await scrape_dataset_resources(body.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scrape dataset page: {e}")

    return DatasetPreviewResponse(
        pageTitle=result["page_title"],
        pageMetadata=result["page_metadata"],
        totalResources=len(result["resources"]),
        resources=[
            DatasetResourceItem(
                title=r["title"],
                description=r.get("description", ""),
                url=r["url"],
                format=r.get("format", ""),
                resourceId=r.get("resource_id", ""),
                sourcePage=r.get("source_page", body.url),
            )
            for r in result["resources"]
        ],
    )


@router.post("/api/rag-sources/dataset-index", response_model=DatasetIndexResponse)
async def dataset_index(
    body: DatasetIndexRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Scrape a dataset page and index all (or selected) resources.
    Each resource becomes its own RAG source with page-level metadata attached.
    """
    from app.rag.scraper import scrape_dataset_resources

    # Get the resource list
    if body.resources:
        resource_list = [
            {
                "title": r.title,
                "description": r.description,
                "url": r.url,
                "format": r.format,
                "resource_id": r.resourceId,
                "source_page": r.sourcePage or body.url,
            }
            for r in body.resources
        ]
        page_title = body.pageTitle
        page_metadata = body.pageMetadata
    else:
        try:
            result = await scrape_dataset_resources(body.url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to scrape page: {e}")
        resource_list = result["resources"]
        page_title = result["page_title"]
        page_metadata = result["page_metadata"]

    if not resource_list:
        raise HTTPException(status_code=404, detail="No downloadable resources found")

    created_sources = []

    for res in resource_list:
        title = _safe_title(res["title"] or _title_from_filename_generic(res["url"]))
        slug = _slugify(title)

        existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{int(time.time())}"

        file_format = res.get("format", "").lower() or ""
        source_type = file_format if file_format in ("csv", "xlsx", "xls", "pdf", "json") else "dataset"

        source = RAGSource(
            title=title,
            slug=slug,
            source_type=source_type,
            source_url=res["url"],
            content=res.get("description", ""),
            status=SourceStatus.indexing,
            category=body.category or page_metadata.get("Tema", "dataset"),
            language=body.language,
        )
        db.add(source)
        await db.flush()

        created_sources.append({
            "sourceId": source.id,
            "title": title,
            "url": res["url"],
            "format": file_format,
            "status": "indexing",
        })

    await db.commit()

    # Build enriched metadata string from page-level metadata
    meta_text = ""
    if page_title:
        meta_text += f"Dataset: {page_title}\n"
    for k, v in page_metadata.items():
        meta_text += f"{k}: {v}\n"

    # Trigger background indexing for each resource
    for info in created_sources:
        asyncio.create_task(_run_dataset_resource_index(
            source_id=info["sourceId"],
            resource_url=info["url"],
            title=info["title"],
            category=body.category or page_metadata.get("Tema", "dataset"),
            language=body.language,
            page_metadata_text=meta_text,
        ))

    return DatasetIndexResponse(
        message=f"Queued {len(created_sources)} resources for indexing from {page_title or body.url}",
        totalQueued=len(created_sources),
        sources=created_sources,
    )


def _title_from_filename_generic(url: str) -> str:
    """Generate a readable title from a URL filename."""
    path = urlparse(url).path if "://" in url else url
    from pathlib import PurePosixPath
    filename = PurePosixPath(path).stem
    title = filename.replace("-", " ").replace("_", " ")
    return title.strip().title() if title.strip() else "Resource"


async def _run_dataset_resource_index(
    source_id: int,
    resource_url: str,
    title: str,
    category: str,
    language: str,
    page_metadata_text: str,
):
    """Download a dataset resource file and index it with metadata."""
    from app.database import async_session
    from app.rag.scraper import download_file as scraper_download_file

    tmp_path = None
    try:
        tmp_path, file_size, ext = await scraper_download_file(resource_url)
        logger.info(f"Downloaded resource '{title}' ({file_size} bytes, .{ext}) for source {source_id}")

        from app.rag.indexing import index_file_with_meta, index_raw_text

        meta = {
            "title": title,
            "url": resource_url,
            "source_type": "dataset",
            "category": category,
            "language": language,
        }

        indexable = {"csv", "xlsx", "xls", "pdf", "html", "htm", "txt", "docx"}
        total_chunks = 0
        if ext in indexable:
            total_chunks += await asyncio.to_thread(
                index_file_with_meta,
                file_path=str(tmp_path),
                source_id=source_id,
                meta=meta,
            )
        else:
            # For non-indexable formats (JSON, XML, ZIP), index metadata only
            content = f"Título: {title}\n{page_metadata_text}\nURL del recurso: {resource_url}\nFormato: {ext}"
            total_chunks += await asyncio.to_thread(
                index_raw_text,
                content=content,
                source_id=source_id,
                title=title,
                url=resource_url,
                source_type="dataset",
                category=category,
                language=language,
            )

        # Also index page metadata as an extra chunk if available
        if page_metadata_text.strip():
            total_chunks += await asyncio.to_thread(
                index_raw_text,
                content=f"Metadatos del dataset para: {title}\n{page_metadata_text}",
                source_id=source_id,
                title=f"Metadata: {title}",
                url=resource_url,
                source_type="dataset",
                category=category,
                language=language,
            )

        async with async_session() as db:
            result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
            source = result.scalar_one_or_none()
            if source:
                source.status = SourceStatus.active
                source.chunks_count = total_chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Dataset source {source_id} ('{title}'): indexed {total_chunks} chunks")

    except Exception as e:
        logger.error(f"Failed to index dataset resource '{title}' (source {source_id}): {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                source = result.scalar_one_or_none()
                if source:
                    source.status = SourceStatus.error
                    source.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update source status: {db_err}")
    finally:
        if tmp_path:
            Path(str(tmp_path)).unlink(missing_ok=True)


@router.get("/api/rag-sources/{source_id}")
async def get_rag_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single RAG source (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"data": _source_to_out(source)}


@router.get("/api/rag-sources/{source_id}/chunks", response_model=ChunkListResponse)
async def get_source_chunks_endpoint(
    source_id: int,
    page: int = Query(1),
    page_size: int = Query(20),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """List chunks belonging to a specific source (Admin+)."""
    # Verify source exists
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from app.rag.indexing import get_source_chunks

    offset = (page - 1) * page_size
    docs = await asyncio.to_thread(get_source_chunks, source_id, limit=page_size, offset=offset)

    chunks = [
        ChunkOut(
            id=doc.id or "",
            contentPreview=(doc.content or "")[:200],
            title=doc.meta.get("title", ""),
            url=doc.meta.get("url", ""),
            sourceType=doc.meta.get("source_type", "rag"),
            sourceId=doc.meta.get("source_id"),
        )
        for doc in docs
    ]

    return ChunkListResponse(
        data=chunks,
        meta={"pagination": {"total": source.chunks_count, "page": page, "pageSize": page_size}},
    )


@router.post("/api/rag-sources")
async def create_rag_source(
    body: dict,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new RAG source (Admin+). Triggers indexing if content or URL is provided."""
    data = body.get("data", body)
    create_data = RAGSourceCreate(**data)

    safe_t = _safe_title(create_data.title)
    slug = create_data.slug or _slugify(safe_t)

    # Check slug uniqueness
    existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A source with this slug already exists")

    taxonomy = None
    if create_data.taxonomy:
        from app.rag.taxonomy import sanitize_taxonomy
        taxonomy = sanitize_taxonomy(create_data.taxonomy)

    source = RAGSource(
        title=safe_t,
        slug=slug,
        source_type=create_data.sourceType,
        source_url=create_data.sourceUrl,
        content=create_data.content,
        category=create_data.category,
        language=create_data.language,
        taxonomy=taxonomy,
    )

    # Determine if we should auto-index
    should_index = bool(create_data.content) or bool(create_data.sourceUrl)
    if should_index:
        source.status = SourceStatus.indexing

    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Trigger background indexing if content or URL provided
    if should_index:
        if create_data.content:
            asyncio.create_task(_run_indexing_in_background(
                source_id=source.id,
                method="text",
                content=create_data.content,
                title=create_data.title,
                url=create_data.sourceUrl or "",
                category=create_data.category or "",
                language=create_data.language,
                taxonomy=taxonomy,
            ))
        elif create_data.sourceUrl:
            asyncio.create_task(_run_indexing_in_background(
                source_id=source.id,
                method="url",
                url=create_data.sourceUrl,
                title=create_data.title,
                category=create_data.category or "",
                language=create_data.language,
                taxonomy=taxonomy,
            ))

    return {"data": _source_to_out(source)}


@router.post("/api/rag-sources/urls-batch", response_model=UrlsBatchResponse)
async def create_rag_sources_urls_batch(
    body: UrlsBatchRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple RAG sources from URLs. If crawl=True, follow same-domain links up to MAX_CRAWL_PAGES."""
    urls = [u.strip() for u in (body.urls or []) if (u or "").strip().startswith(("http://", "https://"))]
    if not urls:
        raise HTTPException(status_code=400, detail="Provide at least one valid URL")
    category = (body.category or "").strip()
    if body.crawl:
        pages = await asyncio.to_thread(_crawl_urls_sync, urls, MAX_CRAWL_PAGES)
        for i, item in enumerate(pages):
            title = _safe_title(item["title"])
            slug = _slugify(title)
            existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
            if existing.scalar_one_or_none():
                slug = f"{slug}-{int(time.time())}-{i}"
            source = RAGSource(
                title=title,
                slug=slug,
                source_type="webpage",
                source_url=item["url"],
                content=item["text"],
                category=category,
                language="es",
                status=SourceStatus.indexing,
            )
            db.add(source)
            await db.flush()
            asyncio.create_task(_run_indexing_in_background(
                source_id=source.id,
                method="text",
                content=item["text"],
                title=title,
                url=item["url"],
                category=category,
                language="es",
            ))
        await db.commit()
        return UrlsBatchResponse(queued=len(pages), message=f"{len(pages)} páginas en cola (crawl mismo dominio)")
    for i, url in enumerate(urls):
        title = _safe_title(urlparse(url).path.rstrip("/").split("/")[-1] or url[:80])
        slug = _slugify(title)
        existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{int(time.time())}-{i}"
        source = RAGSource(
            title=title,
            slug=slug,
            source_type="webpage",
            source_url=url,
            category=category,
            language="es",
            status=SourceStatus.indexing,
        )
        db.add(source)
        await db.flush()
        asyncio.create_task(_run_indexing_in_background(
            source_id=source.id,
            method="url",
            url=url,
            title=title,
            category=category,
            language="es",
        ))
    await db.commit()
    return UrlsBatchResponse(queued=len(urls), message=f"{len(urls)} URL(s) en cola para indexación")


@router.post("/api/rag-sources/upload", response_model=FileUploadResponse)
async def upload_rag_source(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(""),
    language: str = Form("es"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file (PDF, DOCX, TXT, HTML, CSV, XLS, XLSX, SAV) and index it as a RAG source.
    SAV (SPSS): only variable dictionary and methodology are indexed (no raw microdata).
    Other types: processed through Haystack converters, split, embedded, and stored.
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    if ext == ".zip":
        import io
        created = 0
        first_id = None
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/") or not name.lower().endswith(".txt"):
                        continue
                    try:
                        raw = zf.read(name)
                        text = raw.decode("utf-8", errors="replace").strip()
                    except Exception as e:
                        logger.warning("Zip read %s: %s", name, e)
                        continue
                    if len(text) < 50:
                        continue
                    file_title = _safe_title(Path(name).stem or name[:80])
                    slug = _slugify(file_title)
                    existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
                    if existing.scalar_one_or_none():
                        slug = f"{slug}-{int(time.time())}-{created}"
                    source = RAGSource(
                        title=file_title,
                        slug=slug,
                        source_type="txt",
                        content=text[:500_000],
                        category=category,
                        language=language,
                        status=SourceStatus.indexing,
                    )
                    db.add(source)
                    await db.flush()
                    if first_id is None:
                        first_id = source.id
                    asyncio.create_task(_run_indexing_in_background(
                        source_id=source.id,
                        method="text",
                        content=text[:500_000],
                        title=file_title,
                        url="",
                        category=category,
                        language=language,
                    ))
                    created += 1
            await db.commit()
        except zipfile.BadZipFile as e:
            raise HTTPException(status_code=400, detail=f"ZIP inválido: {e}")
        if created == 0:
            raise HTTPException(status_code=400, detail="El ZIP no contiene archivos .txt válidos")
        return FileUploadResponse(
            message=f"ZIP: {created} archivo(s) .txt en cola para indexación.",
            sourceId=first_id or 0,
            chunksCount=0,
            status="indexing",
        )

    # Create RAG source record
    title = _safe_title(title)
    slug = _slugify(title)
    existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
    if existing.scalar_one_or_none():
        slug = f"{slug}-{int(time.time())}"

    source = RAGSource(
        title=title,
        slug=slug,
        source_type=ext.lstrip("."),
        status=SourceStatus.indexing,
        category=category,
        language=language,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    # Save to temp file
    tmp_path = Path(tempfile.mkdtemp()) / f"upload_{source.id}{ext}"
    tmp_path.write_bytes(content)

    # Trigger background indexing
    meta = {
        "title": title,
        "source_type": "rag",
        "category": category,
        "language": language,
    }
    asyncio.create_task(_run_indexing_in_background(
        source_id=source.id,
        method="file",
        file_path=str(tmp_path),
        meta=meta,
    ))

    return FileUploadResponse(
        message=f"File '{file.filename}' uploaded. Indexing started.",
        sourceId=source.id,
        chunksCount=0,  # Will be updated after indexing completes
        status="indexing",
    )


@router.post("/api/rag-sources/{source_id}/analytical-query")
async def analytical_query(
    source_id: int,
    body: AnalyticalQueryRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """
    Run an analytical query on a SAV-derived Parquet (e.g. weighted mean, group by).
    Only available when the source was uploaded as .sav and analytical_data_dir is set.
    """
    from app.rag.analytical import run_analytical_query

    result = run_analytical_query(
        source_id=source_id,
        variable=body.variable,
        statistic=body.statistic,
        group_by=body.group_by,
        weight_var=body.weight_var,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Analytical query failed"))
    return result


@router.put("/api/rag-sources/{source_id}")
async def update_rag_source(
    source_id: int,
    body: dict,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
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
        db_field = {
            "sourceType": "source_type",
            "sourceUrl": "source_url",
        }.get(field, field)
        if value is not None and hasattr(source, db_field):
            if field == "taxonomy" and isinstance(value, dict):
                from app.rag.taxonomy import sanitize_taxonomy
                value = sanitize_taxonomy(value)
            setattr(source, db_field, value)

    await db.commit()
    await db.refresh(source)

    return {"data": _source_to_out(source)}


@router.delete("/api/rag-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a RAG source and all its chunks from pgvector (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Delete chunks from pgvector document store
    try:
        from app.rag.indexing import delete_source_chunks
        deleted = await asyncio.to_thread(delete_source_chunks, source_id)
        logger.info(f"Deleted {deleted} chunks for source {source_id}")
    except Exception as e:
        logger.error(f"Failed to delete chunks for source {source_id}: {e}")

    # Delete the source record
    await db.delete(source)
    await db.commit()


@router.post("/api/rag-sources/{source_id}/classify")
async def classify_source_taxonomy(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Run LLM taxonomy classification for a single source and save to DB.
    Does not reindex; use reindex to propagate taxonomy to chunks.
    """
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Get content snippet
    content_snippet = ""
    if source.content:
        content_snippet = source.content[:2500]
    else:
        from app.rag.indexing import get_source_chunks
        chunks = await asyncio.to_thread(get_source_chunks, source_id, limit=5, offset=0)
        if chunks:
            content_snippet = "\n\n".join((c.content or "")[:500] for c in chunks)

    if not content_snippet.strip():
        raise HTTPException(status_code=400, detail="No content to classify")

    from app.rag.metadata_extractor import extract_taxonomy
    from app.rag.pipeline import get_pipeline_manager

    manager = get_pipeline_manager()
    generator = manager.get_generator()

    taxonomy = await extract_taxonomy(
        content_snippet=content_snippet,
        url=source.source_url or "",
        title=source.title,
        generator=generator,
    )

    if taxonomy:
        source.taxonomy = taxonomy
        await db.commit()
        await db.refresh(source)
        return {"data": _source_to_out(source), "message": "Taxonomy classified"}
    return {"data": _source_to_out(source), "message": "No taxonomy extracted"}


@router.post("/api/rag-sources/mark-stuck-indexing")
async def mark_stuck_indexing(
    older_than_minutes: int = Query(30, ge=1, le=10080),  # default 30 min, max 1 week
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve sources stuck in 'indexing' (no update for longer than older_than_minutes).
    If vectors exist in the store, promote to active; otherwise mark as error for reindex.
    """
    from app.database import async_session
    from app.rag.indexing import count_source_chunks

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    result = await db.execute(
        select(RAGSource.id).where(
            RAGSource.status == SourceStatus.indexing,
            RAGSource.updated_at < cutoff,
        )
    )
    stuck_ids = [row[0] for row in result.fetchall()]

    promoted = 0
    marked_error = 0
    for sid in stuck_ids:
        n = await asyncio.to_thread(count_source_chunks, sid)
        async with async_session() as db2:
            r = await db2.execute(select(RAGSource).where(RAGSource.id == sid))
            src = r.scalar_one_or_none()
            if not src or src.status != SourceStatus.indexing:
                continue
            if n > 0:
                src.status = SourceStatus.active
                src.chunks_count = n
                src.indexing_error = None
                await db2.commit()
                promoted += 1
            else:
                src.status = SourceStatus.error
                src.indexing_error = (
                    f"Indexing timed out (marked as stuck after {older_than_minutes} min)"
                )
                await db2.commit()
                marked_error += 1

    if promoted or marked_error:
        logger.info(
            "mark-stuck-indexing: promoted %s to active, marked %s error (older than %s min)",
            promoted,
            marked_error,
            older_than_minutes,
        )
    return {
        "promoted": promoted,
        "markedError": marked_error,
        "olderThanMinutes": older_than_minutes,
        "checked": len(stuck_ids),
    }


@router.post("/api/rag-sources/reconcile-status")
async def reconcile_rag_status(
    include_indexing: bool = Query(
        False,
        description="If true, also check sources stuck in 'indexing' (default: only 'error')",
    ),
    include_active: bool = Query(
        True,
        description="If true, also sync chunks_count for active sources against pgvector",
    ),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Reconcile RAG source status/counts with pgvector reality.

    - For error/indexing sources with vectors: set status=active, clear indexing_error.
    - For active sources: sync chunks_count to actual vectors to avoid stale 'active but no chunks'.
    """
    from app.database import async_session
    from app.rag.indexing import count_source_chunks

    statuses = [SourceStatus.error]
    if include_indexing:
        statuses.append(SourceStatus.indexing)
    if include_active:
        statuses.append(SourceStatus.active)

    q = select(RAGSource.id).where(RAGSource.status.in_(statuses))
    result = await db.execute(q)
    ids = [row[0] for row in result.fetchall()]

    fixed_status = 0
    synced_counts = 0
    for sid in ids:
        n = int(await asyncio.to_thread(count_source_chunks, sid) or 0)
        async with async_session() as db2:
            r = await db2.execute(select(RAGSource).where(RAGSource.id == sid))
            src = r.scalar_one_or_none()
            if not src:
                continue

            changed = False
            if int(src.chunks_count or 0) != n:
                src.chunks_count = n
                synced_counts += 1
                changed = True

            if n > 0 and src.status in {SourceStatus.error, SourceStatus.indexing}:
                src.status = SourceStatus.active
                src.indexing_error = None
                fixed_status += 1
                changed = True

            if changed:
                await db2.commit()

    if fixed_status or synced_counts:
        logger.info(
            "reconcile-status: fixed_status=%s synced_counts=%s checked=%s",
            fixed_status,
            synced_counts,
            len(ids),
        )

    return {
        "fixed": fixed_status,
        "syncedCounts": synced_counts,
        "checked": len(ids),
    }


@router.post("/api/rag-sources/{source_id}/reindex")
async def reindex_source(
    source_id: int,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-indexing of a RAG source (Admin+)."""
    result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source.status = SourceStatus.indexing
    source.indexing_error = None
    await db.commit()

    asyncio.create_task(_run_single_reindex(source))

    return {
        "message": f"Re-indexing started for source '{source.title}'",
        "sourceId": source.id,
        "status": "indexing",
    }


@router.post("/api/rag-sources/batch-reindex", response_model=BatchReindexResponse)
async def batch_reindex(
    body: BatchReindexRequest | None = None,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """
    Reindex multiple sources in background to propagate taxonomy to chunks.
    By default only reindexes sources that have taxonomy.
    Uses limited concurrency to avoid overload.
    """
    opts = body or BatchReindexRequest()
    query = select(RAGSource).where(RAGSource.status == SourceStatus.active)
    if opts.onlyWithTaxonomy:
        query = query.where(RAGSource.taxonomy.isnot(None))
    # Only sources with content or URL to reindex
    query = query.where(
        or_(
            RAGSource.content.isnot(None),
            RAGSource.source_url.isnot(None),
        )
    )
    result = await db.execute(query)
    sources = list(result.scalars().all())

    if not sources:
        return BatchReindexResponse(
            message="No sources to reindex",
            queued=0,
            skipped=0,
        )

    sem = asyncio.Semaphore(opts.maxConcurrent)

    async def _reindex_with_semaphore(src: RAGSource):
        async with sem:
            await _run_single_reindex(src)

    for src in sources:
        src.status = SourceStatus.indexing
        src.indexing_error = None
    await db.commit()

    for src in sources:
        asyncio.create_task(_reindex_with_semaphore(src))

    logger.info(f"Batch reindex: queued {len(sources)} sources (maxConcurrent={opts.maxConcurrent})")
    return BatchReindexResponse(
        message=f"Re-indexing queued for {len(sources)} sources",
        queued=len(sources),
        skipped=0,
    )


async def _run_single_reindex(source: RAGSource):
    """Run full reindex for one source (delete chunks + re-index with taxonomy)."""
    from app.database import async_session
    from app.rag.indexing import delete_source_chunks

    source_id = source.id
    taxonomy = source.taxonomy if source.taxonomy else None

    try:
        await asyncio.to_thread(delete_source_chunks, source_id)
    except Exception as e:
        logger.error(f"Failed to delete chunks for source {source_id}: {e}")

    try:
        # Non-stripped content is truthy in Python but index_raw_text returns 0 chunks → user sees
        # "reindexed" with 0 vectors. Prefer real text; if that yields 0 chunks, fall back to URL.
        text_body = (source.content or "").strip()
        chunks_after = 0

        if text_body:
            await _run_indexing_in_background(
                source_id=source_id,
                method="text",
                content=text_body,
                title=source.title,
                url=source.source_url or "",
                category=source.category or "",
                language=source.language or "es",
                taxonomy=taxonomy,
            )
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                src = result.scalar_one_or_none()
                chunks_after = int(src.chunks_count or 0) if src else 0

        if chunks_after == 0 and source.source_url:
            try:
                await asyncio.to_thread(delete_source_chunks, source_id)
            except Exception as e:
                logger.warning("delete before URL reindex (source %s): %s", source_id, e)
            if text_body:
                logger.info(
                    "Reindex: text path produced 0 chunks for source %s; falling back to URL fetch",
                    source_id,
                )
            if source.source_type == "pdf" or (source.source_url or "").lower().endswith(".pdf"):
                await _run_pdf_download_and_index(
                    source_id=source_id,
                    pdf_url=source.source_url,
                    title=source.title,
                    category=source.category or "",
                    language=source.language or "es",
                    taxonomy=taxonomy,
                )
            else:
                await _run_indexing_in_background(
                    source_id=source_id,
                    method="url",
                    url=source.source_url,
                    title=source.title,
                    category=source.category or "",
                    language=source.language or "es",
                    taxonomy=taxonomy,
                )
        elif not text_body and not source.source_url:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                src = result.scalar_one_or_none()
                if src:
                    src.status = SourceStatus.error
                    src.chunks_count = 0
                    src.indexing_error = "No content or URL to index"
                    await db.commit()
    except Exception as e:
        logger.error(f"Reindex failed for source {source_id}: {e}", exc_info=True)
        try:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                src = result.scalar_one_or_none()
                if src:
                    src.status = SourceStatus.error
                    src.indexing_error = str(e)[:500]
                    await db.commit()
        except Exception as db_err:
            logger.error(f"Failed to update source status: {db_err}")


# ==================== System Stats ====================


@router.get("/api/system-stats")
async def get_system_stats(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Get system statistics (Admin+)."""
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

    queries_1h = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= now - timedelta(hours=1))
        )
    ).scalar() or 0
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

    # Document store count from pgvector
    try:
        doc_store = get_document_store()
        store_count = doc_store.count_documents()
    except Exception:
        store_count = 0

    stats = SystemStatsOut(
        totalSources=total_sources,
        indexedSources=indexed_sources,
        totalChunks=total_chunks or store_count,
        modelVersion="ominis-2.0",
        modelStatus="active",
        cpuServerStatus="online",
        gpuServerStatus="online",
        totalQueries1h=queries_1h,
        totalQueries24h=queries_24h,
        totalQueriesWeek=queries_week,
        totalQueriesMonth=queries_month,
        lastHealthCheck=now.isoformat(),
    )

    return {"data": stats.model_dump()}


@router.get("/api/system-stats/dashboard-overview")
async def get_dashboard_overview(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Single payload for admin overview cards: health checks, servers, queries, sources, users."""
    now = datetime.now(timezone.utc)
    health = await compute_health_snapshot(db)

    queries_1h = (
        await db.execute(
            select(func.count())
            .select_from(QueryLog)
            .where(QueryLog.created_at >= now - timedelta(hours=1))
        )
    ).scalar() or 0
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

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    users_admins = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role.in_([RoleEnum.admin, RoleEnum.superadmin]))
        )
    ).scalar() or 0
    users_researchers = (
        await db.execute(select(func.count()).select_from(User).where(User.role == RoleEnum.researcher))
    ).scalar() or 0
    users_developers = (
        await db.execute(select(func.count()).select_from(User).where(User.role == RoleEnum.developer))
    ).scalar() or 0

    cd_row = (await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))).scalar_one_or_none()
    default_model_id = normalize_public_model_id(getattr(cd_row, "default_model", None) or "ominis-2.0") if cd_row else "ominis-2.0"
    llm_cfg = (await db.execute(select(LLMModelConfig).where(LLMModelConfig.model_id == default_model_id))).scalar_one_or_none()

    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    sum_ = health.get("inference_summary") or {}
    ollama_def = (sum_.get("ollama_default") or "").lower()
    # Solo Ollama/Vast “base”; las APIs de terceros van en el check del modelo mapeado.
    route_ok = ollama_def in ("online", "serverless")
    mapped_ok, mapped_detail = _mapped_default_model_availability(health, default_model_id, llm_cfg)

    indexed_sources = (
        await db.execute(
            select(func.count()).select_from(RAGSource).where(RAGSource.status == SourceStatus.active)
        )
    ).scalar() or 0
    try:
        doc_store = get_document_store()
        store_count = doc_store.count_documents()
    except Exception:
        store_count = 0

    directory_profiles = (
        await db.execute(select(func.count()).select_from(DoctorDirectoryProfile))
    ).scalar() or 0

    allcan_total: int | None = None
    try:
        base = (getattr(settings, "allcan_strapi_url", None) or "").strip()
        tok = (getattr(settings, "allcan_strapi_api_token", None) or "").strip()
        if base and tok:
            allcan_total = await fetch_organization_total_count(base, tok)
    except Exception as e:
        logger.debug("dashboard allcan count: %s", e)

    ri = get_research_instance_status()
    vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    openscholar_any = bool(
        (getattr(settings, "openscholar_api_url", "") or "").strip()
        or ((getattr(settings, "vast_serverless_openscholar_endpoint", "") or "").strip() and vk)
        or (ri.get("openscholar") or "").lower() == "running"
    )
    openscholar_128k_any = bool(
        (getattr(settings, "openscholar_128k_api_url", "") or "").strip()
        or ((getattr(settings, "vast_serverless_openscholar_128k_endpoint", "") or "").strip() and vk)
        or (ri.get("openscholar_128k") or "").lower() == "running"
    )

    pubmed_corpus_count, clinical_trials_corpus_count = await asyncio.gather(
        fetch_pubmed_record_count(),
        fetch_clinicaltrials_study_count(),
    )

    strapi_base = (getattr(settings, "allcan_strapi_url", None) or "").strip()
    strapi_tok = (getattr(settings, "allcan_strapi_api_token", None) or "").strip()
    allcan_level: str
    if strapi_base and strapi_tok:
        if allcan_total is None:
            allcan_level = "warning"
        elif allcan_total > 0:
            allcan_level = "ok"
        else:
            allcan_level = "warning"
    else:
        allcan_level = "warning"

    source_checklist: list[dict[str, Any]] = [
        {
            "key": "pgvector",
            "label": "Docs vectorizados (pgvector)",
            "level": source_level_ok_count(int(store_count)),
            "count": int(store_count),
            "detail": None,
        },
        {
            "key": "directory_mx",
            "label": "Especialistas (directorio MX)",
            "level": source_level_ok_count(int(directory_profiles or 0)),
            "count": int(directory_profiles or 0),
            "detail": None,
        },
        {
            "key": "allcan",
            "label": "Recursos All.Can (Strapi)",
            "level": allcan_level,
            "count": allcan_total,
            "detail": None if (strapi_base and strapi_tok) else "Strapi URL o token no configurados",
        },
        {
            "key": "clinical_trials",
            "label": "Estudios clínicos (ClinicalTrials.gov)",
            "level": "ok" if clinical_trials_corpus_count else "warning",
            "count": clinical_trials_corpus_count,
            "detail": "API v2 clinicaltrials.gov",
        },
        {
            "key": "pubmed",
            "label": "PubMed (NCBI)",
            "level": "ok" if pubmed_corpus_count else "warning",
            "count": pubmed_corpus_count,
            "detail": "Corpus vía einfo",
        },
        {
            "key": "openscholar",
            "label": "OpenScholar (investigación)",
            "level": "ok" if (openscholar_any or openscholar_128k_any) else "error",
            "count": None,
            "detail": "Modelo vLLM / Vast (sin corpus fijo indexado)",
        },
    ]

    health_checks = [
        {"key": "api", "label": "API Haystack", "level": "ok", "detail": None},
        {"key": "database", "label": "PostgreSQL", "level": "ok" if db_ok else "error", "detail": None},
        {
            "key": "inference_route",
            "label": "Inferencia base (Ollama / Vast)",
            "level": "ok" if route_ok else "error",
            "detail": health.get("model", {}).get("status"),
        },
        {
            "key": "mapped_default_llm",
            "label": f"Modelo por defecto en chat ({default_model_id})",
            "level": "ok" if mapped_ok else "error",
            "detail": mapped_detail,
        },
    ]

    servers_raw = get_ecosystem_servers_checklist()
    servers_out: list[dict[str, Any]] = []
    for s in servers_raw:
        lvl = server_row_level(bool(s.get("up")), str(s.get("state") or ""), s.get("detail"))
        servers_out.append({**s, "level": lvl})

    rag_indexing = (
        await db.execute(
            select(
                RAGSource.id,
                RAGSource.title,
                RAGSource.source_type,
                RAGSource.slug,
                RAGSource.updated_at,
                RAGSource.last_indexed_at,
                RAGSource.chunks_count,
            )
            .where(RAGSource.status == SourceStatus.indexing)
            .order_by(RAGSource.updated_at.desc())
            .limit(25)
        )
    ).all()
    doctor_runs = (
        await db.execute(
            select(DoctorDirectoryScrapeRun)
            .where(DoctorDirectoryScrapeRun.status == DoctorScrapeStatus.running)
            .order_by(DoctorDirectoryScrapeRun.id.desc())
            .limit(15)
        )
    ).scalars().all()

    last_scraped_by_run: dict[int, datetime] = {}
    if doctor_runs:
        run_ids = [r.id for r in doctor_runs]
        mx_rows = (
            await db.execute(
                select(
                    DoctorDirectoryProfile.scrape_run_id,
                    func.max(DoctorDirectoryProfile.last_scraped_at),
                )
                .where(DoctorDirectoryProfile.scrape_run_id.in_(run_ids))
                .group_by(DoctorDirectoryProfile.scrape_run_id)
            )
        ).all()
        for rid, mx in mx_rows:
            if rid is not None and mx is not None:
                last_scraped_by_run[int(rid)] = mx

    ingestion_jobs: list[dict[str, Any]] = []
    for row in rag_indexing:
        rid, title, stype, slug, updated_at, last_indexed_at, chunks = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
        )
        label = (title or slug or f"fuente #{rid}")[:140]
        last_at = last_indexed_at or updated_at
        ingestion_jobs.append(
            {
                "id": f"rag-{rid}",
                "kind": "embedder",
                "label": "Vectorización / indexación RAG",
                "detail": label,
                "source_type": stype,
                "last_ingestion_at": last_at.isoformat() if last_at else None,
                "results_count": int(chunks or 0),
            }
        )
    for run in doctor_runs:
        last_at = last_scraped_by_run.get(run.id) or run.started_at or run.created_at
        ingestion_jobs.append(
            {
                "id": f"doctor-scrape-{run.id}",
                "kind": "scraper",
                "label": "Scrape directorio médicos",
                "detail": f"{run.source_site} · run #{run.id}",
                "source_site": run.source_site,
                "last_ingestion_at": last_at.isoformat() if last_at else None,
                "results_count": int(run.profiles_upserted or 0),
            }
        )

    return {
        "data": {
            "overall": {"status": health.get("status"), "timestamp": health.get("timestamp")},
            "health_checks": health_checks,
            "servers": servers_out,
            "queries": {
                "last1h": int(queries_1h),
                "last24h": int(queries_24h),
                "last7d": int(queries_week),
                "last30d": int(queries_month),
            },
            "sources": source_checklist,
            "sources_legacy": {
                "vector_documents": int(store_count),
                "indexed_sources": int(indexed_sources or 0),
                "directory_specialists": int(directory_profiles or 0),
                "allcan_organizations": allcan_total,
            },
            "users": {
                "total": int(total_users),
                "admins": int(users_admins),
                "researchers": int(users_researchers),
                "developers": int(users_developers),
            },
            "ingestion": {"jobs": ingestion_jobs},
            "health": health,
        }
    }


@router.get("/api/system-stats/query-series")
async def get_query_series(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Time-bucketed query counts for dashboard charts (Admin+)."""
    try:
        raw = await build_query_series(db)
        data = QuerySeriesOut.model_validate(raw)
        return {"data": data.model_dump()}
    except Exception as e:
        logger.exception("get_query_series failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/system-stats/refresh")
async def refresh_system_stats(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db: AsyncSession = Depends(get_db),
):
    """Refresh system statistics (Admin+)."""
    response = await get_system_stats(_, db)
    return {"message": "Statistics refreshed", "stats": response["data"]}


@router.get("/api/system-stats/server-performance")
async def get_server_performance(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """Get real-time server performance metrics for the application server (Admin+)."""
    import os
    import shutil
    import socket

    perf: dict = {}

    # Server identity
    try:
        perf["hostname"] = socket.gethostname()
        perf["ip"] = socket.gethostbyname(socket.gethostname())
        # Try to get AWS instance ID
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://169.254.169.254/latest/api/token",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                method="PUT",
            )
            token = urllib.request.urlopen(req, timeout=2).read().decode()
            req2 = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/instance-id",
                headers={"X-aws-ec2-metadata-token": token},
            )
            perf["awsInstanceId"] = urllib.request.urlopen(req2, timeout=2).read().decode()
            req3 = urllib.request.Request(
                "http://169.254.169.254/latest/meta-data/instance-type",
                headers={"X-aws-ec2-metadata-token": token},
            )
            perf["awsInstanceType"] = urllib.request.urlopen(req3, timeout=2).read().decode()
        except Exception:
            perf["awsInstanceId"] = None
            perf["awsInstanceType"] = None
    except Exception:
        pass

    try:
        # CPU
        load1, load5, load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        perf["cpu"] = {
            "cores": cpu_count,
            "loadAvg1m": round(load1, 2),
            "loadAvg5m": round(load5, 2),
            "loadAvg15m": round(load15, 2),
            "usagePercent": round(min(load1 / cpu_count * 100, 100), 1),
        }

        # Memory
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = int(parts[1].strip().split()[0])  # kB
                        meminfo[key] = val
            total = meminfo.get("MemTotal", 0) / 1024  # MB
            available = meminfo.get("MemAvailable", 0) / 1024
            used = total - available
            perf["memory"] = {
                "totalMB": round(total),
                "usedMB": round(used),
                "availableMB": round(available),
                "usagePercent": round(used / total * 100, 1) if total else 0,
            }
        except Exception:
            perf["memory"] = None

        # Disk
        try:
            disk = shutil.disk_usage("/")
            perf["disk"] = {
                "totalGB": round(disk.total / (1024**3), 1),
                "usedGB": round(disk.used / (1024**3), 1),
                "freeGB": round(disk.free / (1024**3), 1),
                "usagePercent": round(disk.used / disk.total * 100, 1),
            }
        except Exception:
            perf["disk"] = None

        # GPU (nvidia-smi)
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                perf["gpu"] = {
                    "name": parts[0] if len(parts) > 0 else "unknown",
                    "memoryTotalMB": int(parts[1]) if len(parts) > 1 else 0,
                    "memoryUsedMB": int(parts[2]) if len(parts) > 2 else 0,
                    "memoryFreeMB": int(parts[3]) if len(parts) > 3 else 0,
                    "utilizationPercent": int(parts[4]) if len(parts) > 4 else 0,
                    "temperatureC": int(parts[5]) if len(parts) > 5 else 0,
                }
            else:
                perf["gpu"] = None
        except Exception:
            perf["gpu"] = None

        # Backend workers
        try:
            import subprocess
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5,
            )
            workers = []
            for line in result.stdout.splitlines():
                if "uvicorn" in line or "ominis-backend" in line:
                    parts = line.split()
                    if len(parts) >= 11:
                        workers.append({
                            "pid": int(parts[1]),
                            "cpuPercent": float(parts[2]),
                            "memPercent": float(parts[3]),
                            "memMB": round(int(parts[5]) / 1024),  # RSS in KB → MB
                        })
            perf["workers"] = workers
        except Exception:
            perf["workers"] = []

        # Database connections
        try:
            from app.database import async_session
            async with async_session() as db:
                result = await db.execute(
                    text("SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'ominis_haystack' GROUP BY state")
                )
                conns = {row[0] or "other": row[1] for row in result.fetchall()}
                perf["database"] = {
                    "activeConnections": conns.get("active", 0),
                    "idleConnections": conns.get("idle", 0),
                    "totalConnections": sum(conns.values()),
                }
        except Exception:
            perf["database"] = None

        # Uptime
        try:
            with open("/proc/uptime") as f:
                uptime_seconds = float(f.read().split()[0])
                perf["uptimeHours"] = round(uptime_seconds / 3600, 1)
        except Exception:
            perf["uptimeHours"] = None

    except Exception as e:
        logger.error(f"Failed to collect performance metrics: {e}")

    return perf


@router.get("/api/system-stats/gpu-server")
async def get_gpu_server_performance(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
):
    """Get real-time GPU/LLM server performance metrics (Admin+)."""
    perf: dict = {"status": "unknown"}

    ollama_url = settings.ollama_url.rstrip("/")
    perf["ollamaUrl"] = ollama_url

    # 1. Ollama API: models loaded
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            tags_resp = await client.get(f"{ollama_url}/api/tags")
            if tags_resp.status_code == 200:
                perf["status"] = "online"
                models_data = tags_resp.json().get("models", [])
                perf["models"] = [
                    {
                        "name": m.get("name", ""),
                        "sizeGB": round(m.get("size", 0) / 1e9, 1),
                        "modifiedAt": (m.get("modified_at") or "")[:19],
                        "family": m.get("details", {}).get("family", ""),
                        "parameterSize": m.get("details", {}).get("parameter_size", ""),
                        "quantization": m.get("details", {}).get("quantization_level", ""),
                    }
                    for m in models_data
                ]
            else:
                perf["status"] = "error"
                perf["models"] = []
    except Exception as e:
        perf["status"] = "offline"
        perf["models"] = []
        perf["error"] = str(e)[:200]

    # 2. Ollama API: running models (VRAM usage)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            ps_resp = await client.get(f"{ollama_url}/api/ps")
            if ps_resp.status_code == 200:
                running = ps_resp.json().get("models", [])
                perf["runningModels"] = [
                    {
                        "name": m.get("name", ""),
                        "sizeVramGB": round(m.get("size_vram", 0) / 1e9, 1),
                        "expiresAt": (m.get("expires_at") or "")[:19],
                    }
                    for m in running
                ]
            else:
                perf["runningModels"] = []
    except Exception:
        perf["runningModels"] = []

    # 3. Ollama API: test generation speed (quick ping)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            import time as _time
            t0 = _time.time()
            gen_resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": settings.ollama_model, "prompt": "Hola", "stream": False,
                      "options": {"num_predict": 5}},
            )
            latency_ms = int((_time.time() - t0) * 1000)
            if gen_resp.status_code == 200:
                gen_data = gen_resp.json()
                perf["inference"] = {
                    "latencyMs": latency_ms,
                    "evalCount": gen_data.get("eval_count", 0),
                    "evalDurationMs": round(gen_data.get("eval_duration", 0) / 1e6),
                    "loadDurationMs": round(gen_data.get("load_duration", 0) / 1e6),
                    "tokensPerSecond": round(
                        gen_data.get("eval_count", 0) / max(gen_data.get("eval_duration", 1) / 1e9, 0.001), 1
                    ),
                }
            else:
                perf["inference"] = {"error": f"HTTP {gen_resp.status_code}"}
    except Exception as e:
        perf["inference"] = {"error": str(e)[:100]}

    # 4. Try to get GPU hardware info via Ollama's system info or direct nvidia-smi
    # (Ollama doesn't expose GPU stats directly, but we can infer from VRAM)
    try:
        # Parse the Ollama server IP to get remote host info
        from urllib.parse import urlparse as _urlparse
        parsed = _urlparse(ollama_url)
        gpu_host = parsed.hostname
        perf["gpuServerIp"] = gpu_host

        # Try AWS metadata from the GPU server (if same VPC)
        # We can't SSH from the backend, but we can try the Ollama version endpoint
        async with httpx.AsyncClient(timeout=3.0) as client:
            ver_resp = await client.get(f"{ollama_url}/api/version")
            if ver_resp.status_code == 200:
                perf["ollamaVersion"] = ver_resp.json().get("version", "unknown")
    except Exception:
        pass

    return perf


async def compute_health_snapshot(db: AsyncSession) -> dict:
    """Shared health payload for /system-stats/health and dashboard-overview."""
    now = datetime.now(timezone.utc)

    inference_status = "offline"
    try:
        import urllib.request

        req = urllib.request.Request(f"{settings.ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                inference_status = "online"
    except Exception:
        pass

    vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    vsep = (getattr(settings, "vast_serverless_ollama_endpoint", "") or "").strip()
    # Main chat (ominis-2.0) can use Vast Serverless instead of a reachable Ollama URL
    if inference_status == "offline" and vsep and vk:
        inference_status = "serverless"

    secondary_status = "offline"
    clinic_url = (getattr(settings, "ollama_clinic_url", None) or "").strip()
    clinic_is_distinct = bool(clinic_url and clinic_url.rstrip("/") != settings.ollama_url.rstrip("/"))
    if clinic_is_distinct:
        try:
            import urllib.request

            req = urllib.request.Request(f"{clinic_url.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    secondary_status = "online"
        except Exception:
            pass
    else:
        secondary_status = inference_status  # same server as primary

    third_party_models = 0
    try:
        third_party_models = (
            await db.execute(
                select(func.count())
                .select_from(LLMModelConfig)
                .where(
                    LLMModelConfig.llm_provider.isnot(None),
                    LLMModelConfig.llm_provider != "",
                    LLMModelConfig.llm_provider != "ominis",
                )
            )
        ).scalar() or 0
    except Exception:
        pass

    has_inference_path = (
        inference_status in ("online", "serverless")
        or secondary_status == "online"
        or third_party_models > 0
    )
    overall = "healthy" if has_inference_path else "degraded"

    return {
        "status": overall,
        "timestamp": now.isoformat(),
        "backend": {"status": "ok"},
        "model": {"version": "ominis-2.0", "status": inference_status},
        "servers": {"primary": inference_status, "secondary": secondary_status},
        "inference_summary": {
            "ollama_default": inference_status,
            "ollama_clinic": secondary_status if clinic_is_distinct else None,
            "clinic_configured": clinic_is_distinct,
            "serverless_configured": bool(vsep and vk),
            "third_party_models": int(third_party_models),
        },
        "lastCheck": now.isoformat(),
        "serverless": {
            "ollama_endpoint": vsep or None,
            "api_key_configured": bool(vk),
        },
    }


@router.get("/system-stats/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Public health check endpoint (no auth required).

    Overall status stays "healthy" if any inference path works: Ollama, Vast Serverless,
    separate clinic Ollama, or at least one chat model routed to a third-party API (DB config).
    """
    return await compute_health_snapshot(db)


@router.get("/system-stats/health/vast-serverless")
async def vast_serverless_health_detail():
    """List Vast Serverless endpoints and worker counts (requires VAST_API_KEY). Public; no secrets returned."""
    vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    if not vk:
        return {"ok": False, "error": "VAST_API_KEY not configured on backend"}
    from app.vast_serverless.status import list_vast_serverless_endpoints_sync

    return {"ok": True, **list_vast_serverless_endpoints_sync()}


# ==================== Research GPU Instances (Admin) ====================


@router.get("/api/research-instances/status")
async def research_instances_status(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
):
    """Get EC2 status for Ominis 2.0 Research (8K and 128K). Any authenticated user can see which research models are available."""
    return get_research_instance_status()


@router.post("/api/research-instances/start")
async def research_instances_start(
    key: str = Query(..., description="openscholar or openscholar_128k"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    """Start the given research GPU instance. 128K auto-stops after configured minutes."""
    if key not in ("openscholar", "openscholar_128k"):
        raise HTTPException(status_code=400, detail="key must be openscholar or openscholar_128k")
    result = start_research_instance(key)
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result["message"])
    return result


@router.post("/api/research-instances/stop")
async def research_instances_stop(
    key: str = Query(..., description="openscholar or openscholar_128k"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    """Stop the given research GPU instance."""
    if key not in ("openscholar", "openscholar_128k"):
        raise HTTPException(status_code=400, detail="key must be openscholar or openscholar_128k")
    result = stop_research_instance(key)
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result["message"])
    return result


# ==================== LLM GPU Instances (ominis-2.0, ominis-2.0-clinic) ====================


@router.get("/api/llm-instances/status")
async def llm_instances_status(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
):
    """Get EC2 status for ominis-2.0 and ominis-2.0-med servers (often same g4dn)."""
    return get_llm_instance_status()


@router.post("/api/llm-instances/start")
async def llm_instances_start(
    key: str = Query(..., description="ominis-2.0 or ominis-2.0-med"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    """Start the given LLM GPU instance."""
    if key not in ("ominis-2.0", "ominis-2.0-med"):
        raise HTTPException(status_code=400, detail="key must be ominis-2.0 or ominis-2.0-med")
    result = start_llm_instance(cast(LlmInstanceKey, key))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result["message"])
    return result


@router.post("/api/llm-instances/stop")
async def llm_instances_stop(
    key: str = Query(..., description="ominis-2.0 or ominis-2.0-med"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    """Stop the given LLM GPU instance."""
    if key not in ("ominis-2.0", "ominis-2.0-med"):
        raise HTTPException(status_code=400, detail="key must be ominis-2.0 or ominis-2.0-med")
    result = stop_llm_instance(cast(LlmInstanceKey, key))
    if result["status"] == "error":
        raise HTTPException(status_code=502, detail=result["message"])
    return result


# ==================== Servers (grouped by EC2 instance; one on/off per server) ====================


@router.get("/api/servers/status")
async def servers_status(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
):
    """Get all LLM/research EC2 servers with instance details and models on each. For dashboard grouped view."""
    return get_servers_status()


# ==================== LLM servers status (which Ollama URLs are up and which models they have) ====================


@router.get("/api/llm-servers/status")
async def llm_servers_status(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
):
    """
    Check each configured Ollama server (OLLAMA_URL, OLLAMA_CLINIC_URL).
    Returns reachable status and list of model names (Qwen, BioMistral, etc.).
    """
    servers = []
    main_url = (settings.ollama_url or "").strip() or None
    clinic_url = (getattr(settings, "ollama_clinic_url", None) or "").strip() or None
    # When clinic URL is empty, clinic uses main URL (same g4dn); we show both rows with same server info
    urls_to_check = [
        ("OLLAMA_URL (ominis-2.0 / vision)", main_url),
        ("OLLAMA_CLINIC_URL (ominis-2.0-clinic)", clinic_url if clinic_url else main_url),
    ]
    # Probe each unique URL once; cache result by normalized url
    url_cache: dict[str, dict] = {}
    for _label, url in urls_to_check:
        if not url:
            note = "not set (ominis-2.0-clinic usa OLLAMA_URL)" if "CLINIC" in _label else "not set"
            servers.append({"label": _label, "url": None, "reachable": False, "models": [], "note": note})
            continue
        base = url.rstrip("/")
        if base not in url_cache:
            entry = {"reachable": False, "models": []}
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(f"{base}/api/tags")
                    if r.status_code == 200:
                        entry["reachable"] = True
                        entry["models"] = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
            except Exception as e:
                entry["error"] = str(e)[:120]
            url_cache[base] = entry
        cached = url_cache[base]
        note = "Mismo servidor que Ominis 2.0 (OLLAMA_URL)" if ("CLINIC" in _label and not clinic_url and main_url) else None
        servers.append({
            "label": _label,
            "url": base,
            "reachable": cached.get("reachable", False),
            "models": cached.get("models", [])[:],
            **({"note": note} if note else {}),
            **({"error": cached["error"]} if cached.get("error") else {}),
        })
    return {"servers": servers}


# ==================== LLM model config (dashboard: assignments, prompts, version, params) ====================


@router.get("/api/llm-models/providers")
async def get_llm_model_providers(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
):
    """Server-side provider registry (labels + credential key names)."""
    return {"providers": list_provider_ids()}


@router.post("/api/llm-models/list-models")
async def post_llm_list_models(
    body: LLMListModelsRequest,
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """List remote model IDs for a provider (uses stored API token when token not sent)."""
    from app.admin.llm_credentials_read import credential_key_for_provider, get_stored_provider_token
    from app.admin.vision_runtime import get_vision_provider_token

    if body.model_id == "__vision__":
        result_sc = await db.execute(select(SiteConfig).where(SiteConfig.id == 1))
        srow = result_sc.scalar_one_or_none()
        ck = credential_key_for_provider(body.provider_id)
        token = (body.api_token or "").strip()
        if not token and ck:
            token = get_vision_provider_token(ck or "")
        ollama_base = None
        if (body.provider_id or "").strip().lower() == "ominis":
            ollama_base = (
                (srow.vision_ollama_url if srow and getattr(srow, "vision_ollama_url", None) else None)
                or settings.ollama_url
            )
        models = list_models_for_provider(
            body.provider_id,
            api_token=token or None,
            ollama_base_url=ollama_base,
        )
        return {"models": models}

    registry = get_model_registry()
    if body.model_id not in registry:
        raise HTTPException(status_code=404, detail="Model not found")
    cfg = registry[body.model_id]

    ck = credential_key_for_provider(body.provider_id)
    token = (body.api_token or "").strip()
    if not token and ck:
        token = get_stored_provider_token(body.model_id, ck)
    result_db = await db.execute(select(LLMModelConfig).where(LLMModelConfig.model_id == body.model_id))
    row = result_db.scalar_one_or_none()
    ollama_base = None
    if (body.provider_id or "").strip().lower() == "ominis":
        ollama_base = (row.backend_url_override if row and row.backend_url_override else None) or cfg.ollama_url or settings.ollama_url
    models = list_models_for_provider(
        body.provider_id,
        api_token=token or None,
        ollama_base_url=ollama_base,
    )
    return {"models": models}


@router.get("/api/vision-llm-config", response_model=VisionLlmConfigOut)
async def get_vision_llm_config(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard: Vision model (images) — provider, URL, model id, stored key flags."""
    result = await db.execute(select(SiteConfig).where(SiteConfig.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SiteConfig(id=1, banner_message=None)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return VisionLlmConfigOut(
        llm_provider=(getattr(row, "vision_llm_provider", None) or "ominis") or "ominis",
        backend_model=(getattr(row, "vision_backend_model", None) or "") or "",
        ollama_url=(getattr(row, "vision_ollama_url", None) or "") or "",
        openai_base_url=(getattr(row, "vision_openai_base_url", None) or "") or "",
        provider_keys_present=_vision_provider_keys_present(row),
    )


@router.put("/api/vision-llm-config", response_model=VisionLlmConfigOut)
async def put_vision_llm_config(
    body: VisionLlmConfigUpdate,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """Update Vision LLM settings (encrypted API keys per provider)."""
    result = await db.execute(select(SiteConfig).where(SiteConfig.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SiteConfig(id=1, banner_message=None)
        db.add(row)
        await db.flush()
    if body.llm_provider is not None:
        row.vision_llm_provider = body.llm_provider.strip().lower() or None
    if body.backend_model is not None:
        row.vision_backend_model = body.backend_model.strip() or None
    if body.ollama_url is not None:
        v = body.ollama_url.strip()
        row.vision_ollama_url = v or None
    if body.openai_base_url is not None:
        v = body.openai_base_url.strip()
        row.vision_openai_base_url = v or None
    if body.provider_credentials_patch:
        row.vision_credentials_enc = merge_credential_patch(
            getattr(row, "vision_credentials_enc", None),
            body.provider_credentials_patch,
        )
    await db.commit()
    await db.refresh(row)
    try:
        from app.rag.pipeline import get_pipeline_manager

        get_pipeline_manager().rebuild_vision_generator()
    except Exception:
        pass
    return VisionLlmConfigOut(
        llm_provider=(getattr(row, "vision_llm_provider", None) or "ominis") or "ominis",
        backend_model=(getattr(row, "vision_backend_model", None) or "") or "",
        ollama_url=(getattr(row, "vision_ollama_url", None) or "") or "",
        openai_base_url=(getattr(row, "vision_openai_base_url", None) or "") or "",
        provider_keys_present=_vision_provider_keys_present(row),
    )


@router.get("/api/llm-models/config", response_model=list[LLMModelConfigOut])
async def get_llm_models_config(
    _: User = Depends(require_role(RoleEnum.researcher, RoleEnum.developer, RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """
    List all chat LLM models with current config (env + DB overrides).
    overridden lists which keys are saved in DB.
    """
    registry = get_model_registry()
    result_db = await db.execute(select(LLMModelConfig))
    rows = {r.model_id: r for r in result_db.scalars().all()}
    result = []
    for model_id, cfg in registry.items():
        row = rows.get(model_id)
        overridden = []
        if row:
            if row.display_name is not None: overridden.append("display_name")
            if row.version_label is not None: overridden.append("version_label")
            if row.description is not None: overridden.append("description")
            if row.backend_model is not None: overridden.append("backend_model")
            if row.backend_url_override is not None: overridden.append("backend_url_override")
            if row.system_prompt is not None: overridden.append("system_prompt")
            if row.temperature is not None: overridden.append("temperature")
            if row.num_predict is not None: overridden.append("num_predict")
            if row.extra_params is not None: overridden.append("extra_params")
            if row.is_default is not None: overridden.append("is_default")
            if getattr(row, "available_for_researcher", None) is not None: overridden.append("available_for_researcher")
            if getattr(row, "llm_provider", None) is not None:
                overridden.append("llm_provider")
            if getattr(row, "provider_credentials_enc", None):
                overridden.append("provider_credentials")
        backend_type = _backend_type_for_cfg(cfg)
        backend_model = (
            cfg.openai_model
            if (getattr(cfg, "use_openai", False) or getattr(cfg, "use_anthropic", False))
            else cfg.ollama_model
        )
        result.append(LLMModelConfigOut(
            model_id=model_id,
            display_name=cfg.display_name,
            version_label=getattr(cfg, "version_label", "") or "",
            description=cfg.description or "",
            backend_type=backend_type,
            llm_provider=_effective_llm_provider(row, cfg),
            provider_keys_present=_provider_keys_present(row),
            backend_model=backend_model or "",
            backend_url_override=row.backend_url_override if row else None,
            system_prompt=(cfg.system_prompt or None) if getattr(cfg, "system_prompt", "") else None,
            temperature=cfg.temperature,
            num_predict=cfg.num_predict,
            extra_params=dict(row.extra_params) if row and row.extra_params else None,
            is_default=cfg.is_default,
            overridden=overridden,
            available_for_researcher=row.available_for_researcher if row and getattr(row, "available_for_researcher", None) is not None else True,
        ))
    # Synthetic entries only when research slots are not in the main registry (avoids duplicates:
    # research-8k / research-128k are registered in config when env or dashboard enables them).
    for rid, disp, def_url, def_model in (
        ("research-8k", "Ominis Investigación (8K)", settings.openscholar_api_url, settings.openscholar_model),
        (
            "research-128k",
            "Ominis Investigación (128K)",
            (getattr(settings, "openscholar_128k_api_url", None) or "") or "",
            getattr(settings, "openscholar_model", "openscholar") or "openscholar",
        ),
    ):
        if rid in registry:
            continue
        row = rows.get(rid)
        overridden = []
        if row:
            if row.display_name is not None:
                overridden.append("display_name")
            if row.backend_model is not None:
                overridden.append("backend_model")
            if row.backend_url_override is not None:
                overridden.append("backend_url_override")
            if row.extra_params is not None:
                overridden.append("extra_params")
        result.append(
            LLMModelConfigOut(
                model_id=rid,
                display_name=(row.display_name if row and row.display_name else disp),
                version_label="",
                description="Motor del modo Investigación (OpenAI-compatible). La UI sigue mostrando Ominis.",
                backend_type="openai",
                llm_provider="openai",
                provider_keys_present=_provider_keys_present(row),
                backend_model=(row.backend_model if row and row.backend_model else def_model) or "",
                backend_url_override=row.backend_url_override if row else None,
                system_prompt=None,
                temperature=None,
                num_predict=None,
                extra_params=dict(row.extra_params) if row and row.extra_params else None,
                is_default=False,
                overridden=overridden,
                available_for_researcher=True,
            )
        )
    return result


@router.put("/api/llm-models/config/{model_id}")
async def put_llm_model_config(
    model_id: str,
    body: LLMModelConfigUpdate,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update dashboard overrides for one LLM model.
    Only provided fields are updated. Invalidates registry and pipeline so changes apply immediately.
    """
    registry = get_model_registry()
    if model_id not in registry and model_id not in RESEARCH_ROUTING_MODEL_IDS:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    result = await db.execute(select(LLMModelConfig).where(LLMModelConfig.model_id == model_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = LLMModelConfig(model_id=model_id)
        db.add(row)
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.version_label is not None:
        row.version_label = body.version_label
    if body.description is not None:
        row.description = body.description
    if body.backend_model is not None:
        row.backend_model = body.backend_model
    if body.backend_url_override is not None:
        row.backend_url_override = body.backend_url_override.strip() or None
    if body.system_prompt is not None:
        row.system_prompt = body.system_prompt.strip() or None
    if body.temperature is not None:
        row.temperature = body.temperature
    if body.num_predict is not None:
        row.num_predict = body.num_predict
    if body.extra_params is not None:
        row.extra_params = body.extra_params
    if body.is_default is not None:
        row.is_default = body.is_default
    if body.available_for_researcher is not None:
        row.available_for_researcher = body.available_for_researcher
    if body.llm_provider is not None:
        row.llm_provider = body.llm_provider.strip().lower() or None
    if body.provider_credentials_patch:
        row.provider_credentials_enc = merge_credential_patch(
            getattr(row, "provider_credentials_enc", None),
            body.provider_credentials_patch,
        )
    await db.commit()
    invalidate_model_registry()
    try:
        from app.rag.pipeline import get_pipeline_manager

        get_pipeline_manager().invalidate_generators()
    except RuntimeError:
        pass
    return {"status": "ok", "model_id": model_id}


# ==================== Site config (banner message) ====================


@router.get("/api/site-config")
async def get_site_config(db: AsyncSession = Depends(get_db)):
    """Return site-wide config (e.g. banner_message). Public — used to show notification at top of app."""
    result = await db.execute(select(SiteConfig).where(SiteConfig.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SiteConfig(id=1, banner_message=None)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return {"banner_message": getattr(row, "banner_message", None) or None}


@router.patch("/api/site-config")
async def update_site_config(
    body: dict,
    _: User = Depends(require_role(RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """Update site config (e.g. global banner). Superadmin only."""
    result = await db.execute(select(SiteConfig).where(SiteConfig.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = SiteConfig(id=1, banner_message=None)
        db.add(row)
        await db.flush()
    if "banner_message" in body:
        val = body["banner_message"]
        row.banner_message = str(val).strip() or None if val is not None else None
    await db.commit()
    await db.refresh(row)
    return {"banner_message": getattr(row, "banner_message", None) or None}


# ==================== Chat defaults (for all users) ====================


@router.get("/api/chat-defaults")
async def get_chat_defaults(db: AsyncSession = Depends(get_db)):
    """Return default toggles for the chat (Investigación, Ominis, PubMed, Web). Public — used when the chat loads."""
    result = await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        # First run: create default row
        row = ChatDefaults(
            id=1,
            research_mode=False,
            rag_search=True,
            web_search=True,
            pubmed_search=True,
            openscholar_search=False,
            research_2_1=False,
            public_access_enabled=False,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return {
        "research_mode": row.research_mode,
        "rag_search": row.rag_search,
        "web_search": row.web_search,
        "pubmed_search": row.pubmed_search,
        "openscholar_search": getattr(row, "openscholar_search", False),
        "research_2_1": getattr(row, "research_2_1", False),
        "public_access_enabled": getattr(row, "public_access_enabled", False),
        "default_model": normalize_public_model_id(getattr(row, "default_model", None) or "ominis-2.0"),
    }


@router.patch("/api/chat-defaults")
async def update_chat_defaults(
    body: dict,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
    db: AsyncSession = Depends(get_db),
):
    """Update default toggles for the chat. Admin only."""
    result = await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = ChatDefaults(
            id=1,
            research_mode=False,
            rag_search=True,
            web_search=True,
            pubmed_search=True,
            openscholar_search=False,
            research_2_1=False,
            public_access_enabled=False,
        )
        db.add(row)
        await db.flush()
    if "research_mode" in body:
        row.research_mode = bool(body["research_mode"])
    if "rag_search" in body:
        row.rag_search = bool(body["rag_search"])
    if "web_search" in body:
        row.web_search = bool(body["web_search"])
    if "pubmed_search" in body:
        row.pubmed_search = bool(body["pubmed_search"])
    if "openscholar_search" in body:
        row.openscholar_search = bool(body["openscholar_search"])
    if "research_2_1" in body:
        row.research_2_1 = bool(body["research_2_1"])
    if "default_model" in body:
        row.default_model = (body["default_model"] or "").strip() or None
    if "public_access_enabled" in body:
        row.public_access_enabled = bool(body["public_access_enabled"])
    await db.commit()
    await db.refresh(row)
    return {
        "research_mode": row.research_mode,
        "rag_search": row.rag_search,
        "web_search": row.web_search,
        "pubmed_search": row.pubmed_search,
        "openscholar_search": getattr(row, "openscholar_search", False),
        "research_2_1": getattr(row, "research_2_1", False),
        "public_access_enabled": getattr(row, "public_access_enabled", False),
        "default_model": normalize_public_model_id(getattr(row, "default_model", None) or "ominis-2.0"),
    }


# ==================== Query Logs ====================


@router.get("/api/query-logs/aggregated", response_model=QueryStatsOut)
async def get_aggregated_query_stats(
    period: str = Query("day"),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
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

    total_result = await db.execute(
        select(func.count())
        .select_from(QueryLog)
        .where(QueryLog.created_at >= start_date)
    )
    total = total_result.scalar() or 0

    avg_time_result = await db.execute(
        select(func.avg(QueryLog.response_time_ms))
        .where(QueryLog.created_at >= start_date)
        .where(QueryLog.response_time_ms.isnot(None))
    )
    avg_time = avg_time_result.scalar() or 0.0

    tokens_result = await db.execute(
        select(func.sum(QueryLog.tokens_used))
        .where(QueryLog.created_at >= start_date)
    )
    total_tokens = tokens_result.scalar() or 0

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
