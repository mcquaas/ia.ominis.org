"""
Haystack Indexing Pipeline — native file conversion + embedding + pgvector storage.

Supports PDF, DOCX, TXT, HTML, CSV, XLSX, XLS, and SAV (SPSS) files.
SAV: variable dictionary + methodology only (no raw microdata); RAG = knowledge layer.
Other tabular/standard formats use Haystack converters or custom CSV/Excel/SAV converters.
Embeds with SentenceTransformers or ExternalDocumentEmbedder (when configured) and writes to PgvectorDocumentStore.
"""

import csv
import io
import logging
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

import httpx
from haystack import Document, Pipeline
from haystack.components.converters import HTMLToDocument, TextFileToDocument
from haystack.components.embedders import SentenceTransformersDocumentEmbedder
from haystack.components.joiners import DocumentJoiner
from haystack.components.preprocessors import DocumentCleaner, DocumentSplitter
from haystack.components.routers import FileTypeRouter
from haystack.components.writers import DocumentWriter

from app.config import get_settings
from app.rag.document_store import get_document_store
from app.rag.embedder import ExternalDocumentEmbedder

logger = logging.getLogger(__name__)
settings = get_settings()

# Serialize writes to pgvector to avoid "no result available" when many PDFs index concurrently
_index_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# PDF converter (custom: adds page numbers)
# ---------------------------------------------------------------------------

def _pdf_to_documents_with_page_numbers(file_path: Path) -> list[Document]:
    """
    Convert a PDF file to Haystack Documents, adding 'page_number' to metadata.
    Uses pypdf to extract text page by page.
    """
    docs: list[Document] = []
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("pypdf not installed. pip install pypdf for PDF support.")
        return docs

    try:
        reader = PdfReader(str(file_path))
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                docs.append(
                    Document(
                        content=text.strip(),
                        meta={
                            "page_number": i + 1,
                            "file_path": str(file_path),
                            "file_name": file_path.name,
                        },
                    )
                )
    except Exception as e:
        logger.error(f"Failed to convert PDF {file_path.name}: {e}", exc_info=True)
    return docs


# ---------------------------------------------------------------------------
# Tabular data converters (CSV / Excel / SAV → Document)
# ---------------------------------------------------------------------------

def _csv_to_documents(file_path: Path) -> list[Document]:
    """Convert a CSV file to Haystack Documents.
    Each chunk is a group of rows rendered as natural-language text.
    """
    docs: list[Document] = []
    try:
        raw = file_path.read_bytes()
        # Try UTF-8 first, fallback to latin-1
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return docs

        headers = rows[0]
        data_rows = rows[1:]

        # Build a summary header
        summary = f"Dataset with {len(data_rows)} rows and {len(headers)} columns.\n"
        summary += f"Columns: {', '.join(headers)}\n"

        # Sample first few rows for the summary doc
        sample_lines = []
        for row in data_rows[:5]:
            pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
            sample_lines.append("; ".join(pairs))
        summary += "Sample data:\n" + "\n".join(sample_lines)

        docs.append(Document(content=summary, meta={"chunk_type": "csv_summary"}))

        # Chunk remaining rows in groups of 20
        CHUNK_SIZE = 20
        for i in range(0, len(data_rows), CHUNK_SIZE):
            chunk_rows = data_rows[i : i + CHUNK_SIZE]
            lines = []
            for row in chunk_rows:
                pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
                if pairs:
                    lines.append("; ".join(pairs))
            if lines:
                content = "\n".join(lines)
                docs.append(Document(content=content, meta={"chunk_type": "csv_rows", "row_range": f"{i+1}-{i+len(chunk_rows)}"}))

    except Exception as e:
        logger.error(f"Failed to convert CSV {file_path.name}: {e}")
    return docs


def _excel_to_documents(file_path: Path) -> list[Document]:
    """Convert an Excel file (XLSX or XLS) to Haystack Documents."""
    docs: list[Document] = []
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    rows.append([str(c) if c is not None else "" for c in row])
                if rows:
                    docs.extend(_rows_to_documents(rows, sheet_name=sheet_name))
            wb.close()

        elif suffix == ".xls":
            import xlrd
            wb = xlrd.open_workbook(str(file_path))
            for sheet_idx in range(wb.nsheets):
                ws = wb.sheet_by_index(sheet_idx)
                rows = []
                for row_idx in range(ws.nrows):
                    rows.append([str(ws.cell_value(row_idx, c)) for c in range(ws.ncols)])
                if rows:
                    docs.extend(_rows_to_documents(rows, sheet_name=ws.name))

    except Exception as e:
        logger.error(f"Failed to convert Excel {file_path.name}: {e}")
    return docs


def _rows_to_documents(rows: list[list[str]], sheet_name: str = "") -> list[Document]:
    """Convert table rows (with header) into Document chunks."""
    docs: list[Document] = []
    if not rows:
        return docs

    headers = rows[0]
    data_rows = rows[1:]

    prefix = f"Sheet: {sheet_name}\n" if sheet_name else ""
    summary = f"{prefix}Dataset with {len(data_rows)} rows and {len(headers)} columns.\n"
    summary += f"Columns: {', '.join(h for h in headers if h.strip())}\n"

    sample_lines = []
    for row in data_rows[:5]:
        pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
        sample_lines.append("; ".join(pairs))
    if sample_lines:
        summary += "Sample data:\n" + "\n".join(sample_lines)

    docs.append(Document(content=summary, meta={"chunk_type": "table_summary", "sheet": sheet_name}))

    CHUNK_SIZE = 20
    for i in range(0, len(data_rows), CHUNK_SIZE):
        chunk_rows = data_rows[i : i + CHUNK_SIZE]
        lines = []
        for row in chunk_rows:
            pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
            if pairs:
                lines.append("; ".join(pairs))
        if lines:
            content = f"{prefix}" + "\n".join(lines)
            docs.append(Document(content=content, meta={"chunk_type": "table_rows", "sheet": sheet_name, "row_range": f"{i+1}-{i+len(chunk_rows)}"}))

    return docs


# ---------------------------------------------------------------------------
# SPSS/SAV (SASS) — variable dictionary only (no raw microdata in RAG)
# ---------------------------------------------------------------------------

def _sav_to_documents(file_path: Path) -> list[Document]:
    """
    Convert an SPSS .sav file into RAG-ready documents: variable dictionary + methodology.
    Does NOT index raw microdata (recommended: keep microdata in an analytical engine).
    Uses metadata only (pyreadstat metadataonly=True) so large files stay fast.
    """
    docs: list[Document] = []
    try:
        import pyreadstat
    except ImportError:
        logger.error("pyreadstat not installed. pip install pyreadstat for .sav support.")
        return docs

    try:
        _, meta = pyreadstat.read_sav(str(file_path), metadataonly=True)
    except Exception as e:
        logger.error(f"Failed to read SAV metadata from {file_path.name}: {e}")
        return docs

    column_names = getattr(meta, "column_names", []) or []
    column_labels = getattr(meta, "column_labels", []) or []
    # column_labels can be a list (same order as column_names) or missing for some vars
    if len(column_labels) != len(column_names):
        column_labels = [None] * len(column_names)
    var_to_label = dict(zip(column_names, column_labels))
    variable_value_labels = getattr(meta, "variable_value_labels", None) or {}
    file_label = getattr(meta, "file_label", None) or ""
    notes = getattr(meta, "notes", None)
    if notes is None:
        notes = []
    if isinstance(notes, str):
        notes = [notes] if notes.strip() else []
    number_rows = getattr(meta, "number_rows", None)
    number_columns = len(column_names)

    # Methodology chunk (design, weights, analytical notes)
    methodology_parts = []
    if file_label:
        methodology_parts.append(f"Dataset: {file_label}")
    methodology_parts.append(f"Variables: {number_columns}. Observations: {number_rows or 'N/A'}.")
    if notes:
        methodology_parts.append("Notas metodológicas:")
        methodology_parts.extend(f"- {n}" for n in notes[:20])  # cap for size
    if methodology_parts:
        docs.append(
            Document(
                content="\n".join(methodology_parts),
                meta={"chunk_type": "sav_methodology"},
            )
        )

    # One chunk per variable (variable dictionary)
    for var_name in column_names:
        label = var_to_label.get(var_name)
        values_map = variable_value_labels.get(var_name)
        lines = [
            f"Variable: {var_name}",
            f"Pregunta/Etiqueta: {label or '(sin etiqueta)'}",
        ]
        if values_map:
            values_txt = ", ".join(f"{k} = {v}" for k, v in sorted(values_map.items(), key=lambda x: (str(x[0]), str(x[1]))))
            lines.append(f"Valores: {values_txt}")
        lines.append("Universo: (consultar documentación del estudio si aplica).")
        content = "\n".join(lines)
        docs.append(
            Document(
                content=content,
                meta={"chunk_type": "sav_variable", "variable_name": var_name},
            )
        )

    return docs

_indexing_pipeline: Optional[Pipeline] = None


# ---------------------------------------------------------------------------
# Full file-based indexing pipeline (PDF / DOCX / TXT / HTML)
# ---------------------------------------------------------------------------

def build_file_indexing_pipeline() -> Pipeline:
    """
    Build the Haystack indexing pipeline for file uploads.
    Flow: FileTypeRouter → Converters → Joiner → Cleaner → Splitter → Embedder → Writer
    """
    document_store = get_document_store()
    pipeline = Pipeline()

    # File type router (dispatches by MIME type)
    file_type_router = FileTypeRouter(
        mime_types=[
            "application/pdf",
            "text/plain",
            "text/html",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    )

    # Converters for each file type
    pdf_converter = PyPDFToDocument()
    text_converter = TextFileToDocument()
    html_converter = HTMLToDocument()

    # DOCX converter (conditionally import)
    try:
        from haystack.components.converters import DOCXToDocument
        docx_converter = DOCXToDocument()
        has_docx = True
    except ImportError:
        logger.warning("DOCXToDocument not available. DOCX files will not be supported.")
        has_docx = False

    # Joiner merges outputs from all converters
    document_joiner = DocumentJoiner()

    # Preprocessors
    cleaner = DocumentCleaner(
        remove_empty_lines=True,
        remove_extra_whitespaces=True,
    )
    splitter = DocumentSplitter(
        split_by="sentence",
        split_length=3,
        split_overlap=1,
    )

    # Embedder
    embedder = SentenceTransformersDocumentEmbedder(
        model=settings.embedding_model,
    )

    # Writer to PgvectorDocumentStore
    writer = DocumentWriter(
        document_store=document_store,
        policy="overwrite",
    )

    # Add components
    pipeline.add_component("file_type_router", file_type_router)
    pipeline.add_component("pdf_converter", pdf_converter)
    pipeline.add_component("text_converter", text_converter)
    pipeline.add_component("html_converter", html_converter)
    if has_docx:
        pipeline.add_component("docx_converter", docx_converter)
    pipeline.add_component("document_joiner", document_joiner)
    pipeline.add_component("cleaner", cleaner)
    pipeline.add_component("splitter", splitter)
    pipeline.add_component("embedder", embedder)
    pipeline.add_component("writer", writer)

    # Connect router to converters
    pipeline.connect("file_type_router.application/pdf", "pdf_converter.sources")
    pipeline.connect("file_type_router.text/plain", "text_converter.sources")
    pipeline.connect("file_type_router.text/html", "html_converter.sources")
    if has_docx:
        pipeline.connect(
            "file_type_router.application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx_converter.sources",
        )

    # Connect converters to joiner
    pipeline.connect("pdf_converter", "document_joiner")
    pipeline.connect("text_converter", "document_joiner")
    pipeline.connect("html_converter", "document_joiner")
    if has_docx:
        pipeline.connect("docx_converter", "document_joiner")

    # Connect processing chain
    pipeline.connect("document_joiner", "cleaner")
    pipeline.connect("cleaner", "splitter")
    pipeline.connect("splitter", "embedder")
    pipeline.connect("embedder", "writer")

    return pipeline


# ---------------------------------------------------------------------------
# Raw text: clean / split / embed (same logic as former simple pipeline, no DocumentWriter)
# ---------------------------------------------------------------------------


def _clean_split_embed_documents(documents: list[Document]) -> list[Document]:
    """
    Clean → split → embed using the same settings as index_file_with_meta.
    Does not write to pgvector; callers must use _index_write_lock around write_documents.
    """
    cleaner = DocumentCleaner(
        remove_empty_lines=True,
        remove_extra_whitespaces=True,
    )
    splitter = DocumentSplitter(
        split_by="sentence",
        split_length=3,
        split_overlap=1,
    )
    cleaned = cleaner.run(documents=documents)["documents"]
    chunks = splitter.run(documents=cleaned)["documents"]
    if (getattr(settings, "embedding_service_url", None) or "").strip():
        embedder = ExternalDocumentEmbedder()
    else:
        embedder = SentenceTransformersDocumentEmbedder(model=settings.embedding_model)
    embedder.warm_up()
    return embedder.run(documents=chunks)["documents"]


# ---------------------------------------------------------------------------
# Pipeline singletons
# ---------------------------------------------------------------------------

def get_file_indexing_pipeline() -> Pipeline:
    """Get or create the file indexing pipeline."""
    global _indexing_pipeline
    if _indexing_pipeline is None:
        _indexing_pipeline = build_file_indexing_pipeline()
        _indexing_pipeline.warm_up()
    return _indexing_pipeline


# ---------------------------------------------------------------------------
# High-level indexing functions
# ---------------------------------------------------------------------------

def index_file(file_path: str | Path, meta: dict | None = None) -> int:
    """
    Index a file (PDF, DOCX, TXT, HTML) through the Haystack file pipeline.
    Returns the number of document chunks written.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    pipeline = get_file_indexing_pipeline()

    # Inject metadata into the pipeline converters if provided
    result = pipeline.run({"file_type_router": {"sources": [path]}})
    written = result.get("writer", {}).get("documents_written", 0)
    logger.info(f"Indexed file '{path.name}': {written} chunks written")
    return written


def index_file_with_meta(file_path: str | Path, source_id: int, meta: dict | None = None) -> int:
    """
    Index a file and tag all resulting chunks with source metadata.
    This is the primary method used by the admin API.
    Supports: PDF, DOCX, TXT, HTML, CSV, XLSX, XLS.

    Optional paper metadata (for Qdrant/vision collections): pass in meta:
    year, journal, design, population, country, doi. These are stored in chunk.meta.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    document_store = get_document_store()

    suffix = path.suffix.lower()

    # --- Tabular data: use custom converters ---
    if suffix == ".csv":
        raw_docs = _csv_to_documents(path)
    elif suffix in (".xlsx", ".xls"):
        raw_docs = _excel_to_documents(path)
    elif suffix == ".sav":
        raw_docs = _sav_to_documents(path)
    elif suffix == ".pdf":
        raw_docs = _pdf_to_documents_with_page_numbers(path)
    else:
        # --- Standard converters ---
        from haystack.components.converters import TextFileToDocument, HTMLToDocument

        converter_map = {
            ".txt": TextFileToDocument,
            ".html": HTMLToDocument,
            ".htm": HTMLToDocument,
        }

        try:
            from haystack.components.converters import DOCXToDocument
            converter_map[".docx"] = DOCXToDocument
        except ImportError:
            pass

        converter_cls = converter_map.get(suffix)
        if converter_cls is None:
            raise ValueError(f"Unsupported file type: {suffix}")

        converter = converter_cls()
        conv_result = converter.run(sources=[path])
        raw_docs = conv_result.get("documents", [])

    if not raw_docs:
        logger.warning(f"No content extracted from {path.name}")
        return 0

    # Step 2: Clean + split (skip split for .sav — variable dictionary is already one chunk per variable)
    cleaner = DocumentCleaner(remove_empty_lines=True, remove_extra_whitespaces=True)
    cleaned = cleaner.run(documents=raw_docs)["documents"]
    if suffix == ".sav":
        chunks = cleaned
    else:
        splitter = DocumentSplitter(split_by="sentence", split_length=3, split_overlap=1)
        chunks = splitter.run(documents=cleaned)["documents"]

    # Step 3: Tag all chunks with source metadata (including taxonomy)
    # Store source_id as string so pgvector filters (meta.source_id == "123") match retrieval/delete.
    default_meta = {
        "source_id": str(source_id),
        "source_type": "rag",
    }
    if meta:
        default_meta.update(meta)
        # Taxonomy is stored as JSON; pass through for chunk metadata
        if "taxonomy" in meta and meta["taxonomy"]:
            default_meta["taxonomy"] = meta["taxonomy"]
    # Prefer file type (e.g. "pdf") so the API can send sourceType and page_number for PDF links
    if suffix:
        default_meta["source_type"] = suffix.lstrip(".")

    for chunk in chunks:
        chunk.meta.update(default_meta)

    # Step 4: Embed (external bge service or SentenceTransformers)
    if (getattr(settings, "embedding_service_url", None) or "").strip():
        embedder = ExternalDocumentEmbedder()
        embedder.warm_up()
    else:
        embedder = SentenceTransformersDocumentEmbedder(model=settings.embedding_model)
        embedder.warm_up()
    embedded = embedder.run(documents=chunks)["documents"]

    # Step 5: Write to pgvector (serialized to avoid psycopg "no result available" under concurrency)
    with _index_write_lock:
        document_store.write_documents(embedded, policy="overwrite")
    logger.info(f"Indexed file '{path.name}' for source_id={source_id}: {len(embedded)} chunks")
    return len(embedded)


def index_raw_text(
    content: str,
    source_id: int = 0,
    title: str = "",
    url: str = "",
    source_type: str = "rag",
    category: str = "",
    language: str = "es",
    taxonomy: dict | None = None,
) -> int:
    """
    Index raw text content through the simple pipeline.
    Tags all chunks with the given source metadata.
    """
    if not content or not content.strip():
        return 0

    meta: dict = {
        "source_id": str(source_id),
        "title": title,
        "url": url,
        "source_type": source_type,
        "category": category,
        "language": language,
    }
    if taxonomy:
        meta["taxonomy"] = taxonomy
    doc = Document(content=content, meta=meta)

    embedded = _clean_split_embed_documents([doc])
    dim = settings.embedding_dimension
    for d in embedded:
        ev = getattr(d, "embedding", None) or []
        if ev and len(ev) != dim:
            raise ValueError(
                f"Embedding length {len(ev)} != EMBEDDING_DIMENSION={dim}; "
                "align the external embedding service with backend config."
            )

    document_store = get_document_store()
    with _index_write_lock:
        document_store.write_documents(embedded, policy="overwrite")
    n = len(embedded)
    logger.info(f"Indexed raw text (source_id={source_id}): {n} chunks")
    return n


async def index_from_url(
    url: str,
    source_id: int = 0,
    title: str = "",
    category: str = "",
    language: str = "es",
    taxonomy: dict | None = None,
) -> int:
    """
    Fetch content from a URL and index it.
    Downloads the page, saves as temp HTML, runs through the file pipeline.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

        # Determine suffix from content-type or URL
        url_path = url.lower().split("?")[0]
        if "pdf" in content_type or url_path.endswith(".pdf"):
            suffix = ".pdf"
        elif "csv" in content_type or url_path.endswith(".csv"):
            suffix = ".csv"
        elif "spreadsheet" in content_type or "excel" in content_type or url_path.endswith(".xlsx"):
            suffix = ".xlsx"
        elif "ms-excel" in content_type or url_path.endswith(".xls"):
            suffix = ".xls"
        elif "html" in content_type or "text/html" in content_type:
            suffix = ".html"
        else:
            suffix = ".txt"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        meta = {
            "title": title or url,
            "url": url,
            "source_type": "rag",
            "category": category,
            "language": language,
        }
        if taxonomy:
            meta["taxonomy"] = taxonomy

        chunks_written = index_file_with_meta(tmp_path, source_id=source_id, meta=meta)

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        return chunks_written

    except Exception as e:
        logger.error(f"Failed to index URL '{url}': {e}", exc_info=True)
        raise


def _documents_for_source_id(store, source_id: int) -> list[Document]:
    """Match chunks where meta.source_id is stored as string OR int (legacy)."""
    seen: set[str] = set()
    out = []
    for val in (str(source_id), source_id):
        filters = {
            "operator": "AND",
            "conditions": [
                {"field": "meta.source_id", "operator": "==", "value": val},
            ],
        }
        try:
            batch = store.filter_documents(filters=filters) or []
        except Exception as e:
            logger.error(f"Failed to filter chunks for source_id={source_id} val={val!r}: {e}")
            batch = []
        for d in batch:
            did = getattr(d, "id", None) or ""
            key = str(did)
            if key and key not in seen:
                seen.add(key)
                out.append(d)
            elif not key:
                out.append(d)
    return out


def count_source_chunks(source_id: int) -> int:
    """Return how many vector documents exist for this source (string or int meta.source_id)."""
    store = get_document_store()
    try:
        return len(_documents_for_source_id(store, source_id))
    except Exception as e:
        logger.error(f"count_source_chunks failed for source_id={source_id}: {e}")
        return 0


def delete_source_chunks(source_id: int) -> int:
    """
    Delete all document chunks belonging to a specific source.
    Uses pgvector's filter_documents + delete_documents.
    Returns the number of documents deleted.
    """
    store = get_document_store()

    try:
        docs = _documents_for_source_id(store, source_id)
    except Exception as e:
        logger.error(f"Failed to filter chunks for source_id={source_id}: {e}")
        return 0

    if not docs:
        logger.info(f"No chunks found for source_id={source_id}")
        return 0

    doc_ids = list(dict.fromkeys([d.id for d in docs if d.id]))
    store.delete_documents(document_ids=doc_ids)
    logger.info(f"Deleted {len(doc_ids)} chunks for source_id={source_id}")
    return len(doc_ids)


def get_source_chunks(source_id: int, limit: int = 50, offset: int = 0) -> list[Document]:
    """
    Get all document chunks belonging to a specific source.
    """
    store = get_document_store()

    try:
        docs = _documents_for_source_id(store, source_id)
    except Exception as e:
        logger.error(f"Failed to filter chunks for source_id={source_id}: {e}")
        return []
    # Manual pagination since pgvector filter_documents doesn't support limit/offset
    return docs[offset : offset + limit]


def get_store_stats() -> dict:
    """Get document store statistics."""
    store = get_document_store()
    total = store.count_documents()
    return {
        "totalDocuments": total,
        "embeddingModel": settings.embedding_model,
        "embeddingDimension": settings.embedding_dimension,
        "storageType": "pgvector (PostgreSQL)",
    }
