"""
Admin routes: RAG sources, file upload, indexing, system stats, query logs.
Paths match the Strapi-compatible format the frontend expects.
"""

import asyncio
import json
import logging
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import QueryLog, RAGSource, SourceStatus, SystemStat
from app.admin.schemas import (
    BatchReindexRequest,
    BatchReindexResponse,
    ChunkListResponse,
    ChunkOut,
    DatasetIndexRequest,
    DatasetIndexResponse,
    DatasetPreviewRequest,
    DatasetPreviewResponse,
    DatasetResourceItem,
    FileUploadResponse,
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
    SourceStatsOut,
    StoreStatsOut,
    SystemStatsOut,
    TainacanImportRequest,
    TainacanImportResponse,
    TainacanPreviewResponse,
)
from app.auth.dependencies import require_role
from app.auth.models import RoleEnum, User
from app.config import get_settings
from app.database import get_db
from app.rag.document_store import get_document_store

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["admin"])

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm", ".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


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
                source_type="rag",
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

        # Extract metadata using LLM (non-blocking, best-effort)
        await _extract_and_save_metadata(source_id, kwargs)

        # Clean up temp file if applicable
        if method == "file" and "file_path" in kwargs:
            Path(kwargs["file_path"]).unlink(missing_ok=True)

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


@router.get("/api/rag-sources/taxonomy-schema")
async def get_taxonomy_schema(
    _: User = Depends(require_role(RoleEnum.admin)),
):
    """Return the taxonomy dimensions and valid values for researcher classification."""
    from app.rag.taxonomy import RAG_TAXONOMY
    return {"taxonomy": RAG_TAXONOMY}


@router.get("/api/rag-sources/stats", response_model=SourceStatsOut)
async def get_source_stats(
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
):
    """Get document store statistics (Admin+)."""
    from app.rag.indexing import get_store_stats
    stats = get_store_stats()
    return StoreStatsOut(**stats)


# ==================== Tainacan Import ====================


@router.get("/api/rag-sources/tainacan-preview", response_model=TainacanPreviewResponse)
async def tainacan_preview(
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
):
    """
    Preview: Scrape a URL and return all PDF links found, without downloading/indexing.
    Use this to show the user what will be indexed before committing.
    """
    from app.rag.scraper import scrape_pdf_links

    try:
        pdf_links = await scrape_pdf_links(body.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to scrape URL: {e}")

    return ScrapePreviewResponse(
        url=body.url,
        totalPdfs=len(pdf_links),
        pdfs=[
            ScrapedPdfItem(
                title=p["title"],
                pdfUrl=p["pdf_url"],
                sourcePage=p["source_page"],
            )
            for p in pdf_links
        ],
    )


@router.post("/api/rag-sources/scrape-index", response_model=ScrapeIndexResponse)
async def scrape_and_index(
    body: ScrapeIndexRequest,
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Scrape a URL for PDF links (or use a provided list), create RAG sources for each,
    and trigger background indexing. Each PDF becomes its own RAG source.
    """
    from app.rag.scraper import scrape_pdf_links

    # Get the list of PDFs to index
    if body.pdfs:
        # Use the provided list (user may have filtered the preview)
        pdf_list = [{"title": p.title, "pdf_url": p.pdfUrl, "source_page": p.sourcePage} for p in body.pdfs]
    else:
        # Scrape the page fresh
        try:
            pdf_list = await scrape_pdf_links(body.url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to scrape URL: {e}")

    if not pdf_list:
        raise HTTPException(status_code=404, detail="No PDF links found on the page")

    created_sources = []

    for pdf_info in pdf_list:
        title = _safe_title(pdf_info["title"])
        pdf_url = pdf_info["pdf_url"]
        source_page = pdf_info["source_page"]

        slug = _slugify(title)

        # Ensure unique slug
        existing = await db.execute(select(RAGSource).where(RAGSource.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{int(time.time())}"

        source = RAGSource(
            title=title,
            slug=slug,
            source_type="pdf",
            source_url=pdf_url,
            status=SourceStatus.indexing,
            category=body.category or "scraped",
            language=body.language,
        )
        db.add(source)
        await db.flush()  # Get the ID without committing yet

        created_sources.append({
            "sourceId": source.id,
            "title": title,
            "pdfUrl": pdf_url,
            "status": "indexing",
        })

    await db.commit()

    # Trigger background indexing for each PDF
    for info in created_sources:
        asyncio.create_task(_run_pdf_download_and_index(
            source_id=info["sourceId"],
            pdf_url=info["pdfUrl"],
            title=info["title"],
            category=body.category or "scraped",
            language=body.language,
        ))

    return ScrapeIndexResponse(
        message=f"Queued {len(created_sources)} PDFs for indexing from {body.url}",
        totalQueued=len(created_sources),
        sources=created_sources,
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


# ==================== Dataset Page Scraping (CSV/XLS/PDF from data portals) ====================


@router.post("/api/rag-sources/dataset-preview", response_model=DatasetPreviewResponse)
async def dataset_preview(
    body: DatasetPreviewRequest,
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
        if ext in indexable:
            chunks = await asyncio.to_thread(
                index_file_with_meta,
                file_path=str(tmp_path),
                source_id=source_id,
                meta=meta,
            )
        else:
            # For non-indexable formats (JSON, XML, ZIP), index metadata only
            content = f"Título: {title}\n{page_metadata_text}\nURL del recurso: {resource_url}\nFormato: {ext}"
            chunks = await asyncio.to_thread(
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
            await asyncio.to_thread(
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
                source.chunks_count = chunks
                source.last_indexed_at = datetime.now(timezone.utc)
                source.indexing_error = None
                await db.commit()
                logger.info(f"Dataset source {source_id} ('{title}'): indexed {chunks} chunks")

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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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


@router.post("/api/rag-sources/upload", response_model=FileUploadResponse)
async def upload_rag_source(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(""),
    language: str = Form("es"),
    _: User = Depends(require_role(RoleEnum.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file (PDF, DOCX, TXT, HTML) and index it as a RAG source.
    The file is processed through Haystack's native converters, split, embedded,
    and stored in the PgvectorDocumentStore.
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


@router.put("/api/rag-sources/{source_id}")
async def update_rag_source(
    source_id: int,
    body: dict,
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
        if source.content:
            await _run_indexing_in_background(
                source_id=source_id,
                method="text",
                content=source.content,
                title=source.title,
                url=source.source_url or "",
                category=source.category or "",
                language=source.language or "es",
                taxonomy=taxonomy,
            )
        elif source.source_url:
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
        else:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source_id))
                src = result.scalar_one_or_none()
                if src:
                    src.status = SourceStatus.active
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
    _: User = Depends(require_role(RoleEnum.admin)),
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
    response = await get_system_stats(_, db)
    return {"message": "Statistics refreshed", "stats": response["data"]}


@router.get("/api/system-stats/server-performance")
async def get_server_performance(
    _: User = Depends(require_role(RoleEnum.admin)),
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
    _: User = Depends(require_role(RoleEnum.admin)),
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


@router.get("/system-stats/health")
async def health_check():
    """Public health check endpoint (no auth required)."""
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

    secondary_status = "offline"
    try:
        import urllib.request
        req = urllib.request.Request(f"{settings.falcon_ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                secondary_status = "online"
    except Exception:
        pass

    if inference_status == "online" or secondary_status == "online":
        overall = "healthy"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "timestamp": now.isoformat(),
        "model": {"version": "ominis-2.0", "status": inference_status},
        "servers": {"primary": inference_status, "secondary": secondary_status},
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
