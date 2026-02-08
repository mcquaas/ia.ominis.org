"""
Tainacan Collection Importer — fetches items from Tainacan (WordPress),
downloads the linked files, and indexes them into pgvector with full metadata.

Supports: CSV, XLSX, XLS, PDF, HTML, TXT and other text-based files.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

TAINACAN_BASE = "https://ominis.org"
COLLECTION_ID = 97
USER_AGENT = "OminisBot/1.0 (+https://ominis.org)"

# Extensions we can index
INDEXABLE_EXTS = {".csv", ".xlsx", ".xls", ".pdf", ".html", ".htm", ".txt", ".doc", ".docx", ".ods"}

# Map Tainacan metadata field names → our internal keys
META_FIELD_MAP = {
    "Nombre de la fuente": "source_name",
    "Descripción": "description",
    "Taxonomía": "taxonomy",
    "Tipo de fuente": "source_type_id",
    "Ámbito geográfico": "geographic_scope",
    "Idioma": "language_id",
    "Periodo cubierto por los datos": "coverage_period",
    "Área de servicio": "service_area",
    "Liga directa al archivo": "direct_url",
    "Tipo de archivo": "file_type",
    "Organismo que publica la fuente": "publisher_id",
    "País de publicación": "country_id",
    "URL original de la fuente": "original_url",
    "Fecha de publicación": "publication_date",
    "Periodo de actualización ISO-8601": "update_period",
    "Licencia": "license",
    "Derechos, términos y condiciones de uso": "rights",
    "Fecha copyright": "copyright_date",
    "Fecha de verificación": "verification_date",
    "Mostrar Fuente": "display_source",
    "IA No. de registros": "record_count",
    "IA No. Columnas": "column_count",
}


# ---------------------------------------------------------------------------
# Tainacan API fetching
# ---------------------------------------------------------------------------

async def fetch_all_items(
    base_url: str = TAINACAN_BASE,
    collection_id: int = COLLECTION_ID,
    max_items: Optional[int] = None,
) -> list[dict]:
    """Fetch all published items from a Tainacan collection."""
    api_url = f"{base_url}/wp-json/tainacan/v2/collection/{collection_id}/items"
    all_items = []
    page = 1

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            try:
                resp = await client.get(
                    api_url,
                    params={"perpage": 20, "paged": page, "status": "publish"},
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Tainacan sometimes returns 500 on certain pages; retry once
                logger.warning(f"Page {page} returned {e.response.status_code}, retrying...")
                await asyncio.sleep(2)
                try:
                    resp = await client.get(
                        api_url,
                        params={"perpage": 10, "paged": page, "status": "publish"},
                        headers={"User-Agent": USER_AGENT},
                    )
                    resp.raise_for_status()
                except Exception:
                    logger.error(f"Page {page} failed permanently, skipping")
                    page += 1
                    continue

            total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])

            if not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                parsed = _parse_item(item)
                if parsed:
                    all_items.append(parsed)

            logger.info(f"Tainacan page {page}/{total_pages}: {len(all_items)} items")

            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break
            if page >= total_pages:
                break
            page += 1

    return all_items


def _parse_item(item: dict) -> Optional[dict]:
    """Extract structured data from a Tainacan item."""
    item_id = item.get("id")
    title = item.get("title", "")
    if isinstance(title, dict):
        title = title.get("rendered", str(title))
    # Clean HTML from title
    title = title.strip()

    meta = item.get("metadata", {})
    parsed_meta = {}

    for key, value in meta.items():
        if not isinstance(value, dict):
            continue
        field_name = value.get("name", "")
        field_value = value.get("value", "")

        internal_key = META_FIELD_MAP.get(field_name)
        if not internal_key:
            continue

        # Handle taxonomy (list of dicts with 'name')
        if isinstance(field_value, list):
            if field_value and isinstance(field_value[0], dict):
                field_value = ", ".join(v.get("name", "") for v in field_value if v.get("name"))
            else:
                field_value = ", ".join(str(v) for v in field_value)

        parsed_meta[internal_key] = str(field_value).strip() if field_value else ""

    direct_url = parsed_meta.get("direct_url", "")
    original_url = parsed_meta.get("original_url", "")

    # Pick the best URL to download
    download_url = direct_url or original_url

    # Detect file extension from URL
    file_ext = _detect_ext(download_url)

    return {
        "tainacan_id": item_id,
        "title": title,
        "url": item.get("url", ""),
        "download_url": download_url,
        "original_url": original_url,
        "file_ext": file_ext,
        "meta": parsed_meta,
    }


def _detect_ext(url: str) -> str:
    """Detect file extension from URL path."""
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path.lower()
    last_part = path.split("/")[-1]
    if "." in last_part:
        ext = "." + last_part.rsplit(".", 1)[-1]
        if len(ext) <= 6:
            return ext
    return ""


# ---------------------------------------------------------------------------
# Download + index a single Tainacan item
# ---------------------------------------------------------------------------

async def download_file(url: str, timeout: float = 120.0) -> tuple[Path, str]:
    """Download a file from URL. Returns (temp_path, detected_extension)."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=15),
        follow_redirects=True,
    ) as client:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        url_ext = _detect_ext(url)

        # Determine extension from content-type if URL doesn't have one
        if not url_ext:
            if "pdf" in content_type:
                url_ext = ".pdf"
            elif "csv" in content_type:
                url_ext = ".csv"
            elif "spreadsheet" in content_type or "xlsx" in content_type:
                url_ext = ".xlsx"
            elif "ms-excel" in content_type:
                url_ext = ".xls"
            elif "html" in content_type:
                url_ext = ".html"
            else:
                url_ext = ".txt"

        tmp = tempfile.NamedTemporaryFile(suffix=url_ext, delete=False)
        tmp.write(resp.content)
        tmp.close()

        return Path(tmp.name), url_ext


async def index_single_item(
    item: dict,
    source_id: int,
    concurrency_semaphore: Optional[asyncio.Semaphore] = None,
) -> int:
    """Download and index a single Tainacan item. Returns chunks written."""
    from app.rag.indexing import index_file_with_meta, index_raw_text

    sem = concurrency_semaphore or asyncio.Semaphore(1)
    download_url = item.get("download_url", "")
    file_ext = item.get("file_ext", "")
    title = item.get("title", "")
    meta_info = item.get("meta", {})

    # Build rich metadata for embeddings
    meta = {
        "title": title,
        "url": download_url,
        "original_url": meta_info.get("original_url", ""),
        "source_type": "tainacan",
        "category": meta_info.get("taxonomy", ""),
        "language": "es",
        "tainacan_id": item.get("tainacan_id"),
        "geographic_scope": meta_info.get("geographic_scope", ""),
        "coverage_period": meta_info.get("coverage_period", ""),
        "publication_date": meta_info.get("publication_date", ""),
        "publisher": meta_info.get("publisher_id", ""),
    }

    tmp_path = None
    try:
        # Can we download the file?
        if download_url and download_url.startswith("http") and file_ext in INDEXABLE_EXTS:
            async with sem:
                tmp_path, actual_ext = await download_file(download_url)

            # Use actual_ext if more specific
            if actual_ext and actual_ext in INDEXABLE_EXTS:
                file_ext = actual_ext

            # ODS → convert to text via description only (not directly supported)
            if file_ext == ".ods":
                logger.info(f"ODS file '{title}': indexing metadata+description only")
                return _index_metadata_only(item, source_id, meta)

            # ZIP / RAR → skip file content, index metadata only
            if file_ext in (".zip", ".rar", ".exe"):
                logger.info(f"Archive '{title}': indexing metadata+description only")
                return _index_metadata_only(item, source_id, meta)

            chunks = await asyncio.to_thread(
                index_file_with_meta,
                file_path=str(tmp_path),
                source_id=source_id,
                meta=meta,
            )
            return chunks

        else:
            # No downloadable file — index the rich metadata + description as text
            return _index_metadata_only(item, source_id, meta)

    except Exception as e:
        logger.error(f"Failed to index Tainacan item '{title}': {e}")
        # Fallback: index metadata only
        try:
            return _index_metadata_only(item, source_id, meta)
        except Exception:
            return 0
    finally:
        if tmp_path:
            Path(str(tmp_path)).unlink(missing_ok=True)


def _index_metadata_only(item: dict, source_id: int, meta: dict) -> int:
    """Index just the Tainacan metadata + description as text."""
    from app.rag.indexing import index_raw_text

    meta_info = item.get("meta", {})
    parts = []

    title = item.get("title", "")
    if title:
        parts.append(f"Título: {title}")

    desc = meta_info.get("description", "")
    if desc:
        # Strip HTML tags from description
        import re
        clean_desc = re.sub(r"<[^>]+>", " ", desc)
        clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
        if clean_desc:
            parts.append(f"Descripción: {clean_desc}")

    taxonomy = meta_info.get("taxonomy", "")
    if taxonomy:
        parts.append(f"Taxonomía: {taxonomy}")

    geo = meta_info.get("geographic_scope", "")
    if geo:
        parts.append(f"Ámbito geográfico: {geo}")

    period = meta_info.get("coverage_period", "")
    if period:
        parts.append(f"Periodo: {period}")

    pub_date = meta_info.get("publication_date", "")
    if pub_date:
        parts.append(f"Fecha de publicación: {pub_date}")

    license_info = meta_info.get("license", "")
    if license_info:
        parts.append(f"Licencia: {license_info}")

    url = item.get("download_url", "") or meta_info.get("original_url", "")
    if url:
        parts.append(f"URL: {url}")

    content = "\n".join(parts)
    if not content.strip():
        return 0

    return index_raw_text(
        content=content,
        source_id=source_id,
        title=title,
        url=url,
        source_type="tainacan",
        category=taxonomy,
        language="es",
    )


# ---------------------------------------------------------------------------
# Preview (summary of what will be imported)
# ---------------------------------------------------------------------------

async def preview_collection(
    base_url: str = TAINACAN_BASE,
    collection_id: int = COLLECTION_ID,
) -> dict:
    """Fetch all items and return a summary without indexing."""
    items = await fetch_all_items(base_url, collection_id)

    by_ext = {}
    indexable = 0
    metadata_only = 0

    for item in items:
        ext = item.get("file_ext", "") or "(no file)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        if ext in INDEXABLE_EXTS:
            indexable += 1
        else:
            metadata_only += 1

    return {
        "totalItems": len(items),
        "indexableFiles": indexable,
        "metadataOnly": metadata_only,
        "byExtension": dict(sorted(by_ext.items(), key=lambda x: -x[1])),
        "items": items,  # full list for the import step
    }
