"""
RAG query routes — Haystack 2.23 native architecture.

Uses OllamaChatGenerator with ChatMessage objects for proper chat/multimodal support.
Integrates web search (DuckDuckGo) and PubMed search as Haystack components.
Vision analysis uses OllamaChatGenerator + ImageContent natively.

SSE event format:
  data: {"type": "status", "message": "..."}\n\n
  data: {"type": "chunk", "text": "..."}\n\n
  data: {"type": "sources", "sources": [...]}\n\n
  data: {"type": "done", "answer": "...", "sources": [...]}\n\n
"""

import asyncio
import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from haystack import Document
from haystack.dataclasses import ChatMessage, StreamingChunk

import httpx
import html2text

from app.config import DEFAULT_MODEL_ID, get_model_config, get_settings
from app.rag.pipeline import (
    SYSTEM_PROMPT,
    build_chat_messages,
    get_pipeline_manager,
)
from app.rag.document_store import get_document_store
from app.rag.charting import generate_chart_specs, parse_chart_specs_from_text, render_chart_images, strip_chart_block_from_text
from app.rag.pdf_generator import generate_pdf
from app.rag.web_search import search_web
from app.rag.pubmed_search import search_pubmed
from app.rag.vision import analyze_image
from app.rag.scraper import BROWSER_HEADERS
from app.admin.research_instances import get_active_research_key
from app.rag.openscholar import (
    MODEL_CTX_LIMIT,
    MODEL_CTX_LIMIT_128K,
    build_academic_messages,
    get_openscholar_128k_generator,
    get_openscholar_generator,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["query"])

# Approximate chars per token for input estimation (Spanish/English)
CHARS_PER_TOKEN = 4
# Reserve tokens so completion never exceeds model context
OUTPUT_TOKEN_BUFFER = 128
MIN_OUTPUT_TOKENS = 1024
MAX_OUTPUT_TOKENS_CAP = 4096


def _estimate_input_tokens_from_messages(messages) -> int:
    """Estimate total input tokens from ChatMessage list (for context limit check)."""
    total_chars = 0
    for m in messages:
        content = getattr(m, "content", None)
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if hasattr(block, "text"):
                    total_chars += len(block.text or "")
                else:
                    total_chars += len(str(block))
        else:
            total_chars += len(str(content or ""))
    return max(0, total_chars // CHARS_PER_TOKEN)


# --- Request/Response schemas ---

class HistoryMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    history: list[HistoryMessage] = []
    image: Optional[str] = None  # Base64 encoded image for vision analysis
    model: Optional[str] = None  # Model variant (e.g. "ominis-2.0")
    rag_search: bool = True
    web_search: bool = True
    pubmed_search: bool = True
    num_sources: int = 3
    file_context: Optional[str] = None  # Extracted text from attached files


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    query: str
    model: str
    charts: Optional[list[dict]] = None


class ResearchRequest(BaseModel):
    question: str
    history: list[HistoryMessage] = []
    image: Optional[str] = None
    model: Optional[str] = None
    rag_search: bool = True
    web_search: bool = True
    pubmed_search: bool = True
    num_sources: int = 10
    file_context: Optional[str] = None
    iterations: int = 5
    max_total_sources: int = 20
    max_follow_links: int = 20
    max_trusted_sources: int = 10
    time_budget_seconds: int = 300
    excluded_sources: list[str] = []  # URLs the user deselected from the plan
    excluded_topics: list[str] = []  # Topics or study types the user asked NOT to include


# --- Text sanitization ---

_CJK_RANGES = re.compile(
    r'[\u2E80-\u2FFF\u3000-\u303F\u3040-\u309F\u30A0-\u30FF'
    r'\u3100-\u312F\u3130-\u318F\u31A0-\u31EF\u31F0-\u31FF'
    r'\u3200-\u32FF\u3300-\u33FF\u3400-\u4DBF\u4E00-\u9FFF'
    r'\uA000-\uA48F\uA490-\uA4CF\uAC00-\uD7AF\uF900-\uFAFF'
    r'\uFE30-\uFE4F\U00020000-\U0002A6DF\U0002A700-\U0002B73F'
    r'\U0002B740-\U0002B81F\U0002B820-\U0002CEAF\U0002CEB0-\U0002EBEF'
    r'\U00030000-\U0003134F\u0600-\u06FF\u0750-\u077F\u0E00-\u0E7F]+'
)

def _sanitize_text(text: str) -> str:
    """Remove CJK, Arabic, Thai and other non-Latin characters from LLM output."""
    return _CJK_RANGES.sub('', text)


# --- SSE Helpers ---

def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _source_display_title(meta: dict) -> str:
    """Get a display title for a source; fallback to URL hostname when title is generic/empty."""
    title = (meta.get("title") or "").strip()
    url = meta.get("url", "")
    if not title or title.lower() in ("url", "sin título", "sin titulo"):
        if url:
            try:
                return urlparse(url).netloc or url[:60]
            except Exception:
                return url[:60] if len(url) > 60 else url
        return "Sin título"
    return title


def _doc_to_source(doc: Document) -> dict:
    """Convert a Haystack Document to a source dict for the API response."""
    return {
        "title": _source_display_title(doc.meta),
        "url": doc.meta.get("url", ""),
        "score": round(doc.score or 0.0, 4) if doc.score else None,
        "type": doc.meta.get("source_type", "rag"),
        "citation": doc.meta.get("citation", ""),
        "authors": doc.meta.get("authors", ""),
        "year": doc.meta.get("year", ""),
        "journal": doc.meta.get("journal", ""),
    }


def _deduplicate_and_rank(documents: list[Document], max_total: int = 10) -> list[Document]:
    """
    Deduplicate documents by URL, keeping the version with the MOST content.
    Then rank by relevance with a balanced mix of source types.
    """
    url_best: dict[str, Document] = {}

    for doc in documents:
        url = doc.meta.get("url", "")
        if not url or not doc.content:
            continue

        normalized = urlparse(url)._replace(fragment="").geturl().rstrip("/")
        existing = url_best.get(normalized)
        if existing is None:
            url_best[normalized] = doc
        else:
            # Keep the version with more content (full page > snippet)
            if len(doc.content or "") > len(existing.content or ""):
                url_best[normalized] = doc

    unique = list(url_best.values())

    def sort_key(d: Document) -> tuple:
        source_type = d.meta.get("source_type", "rag")
        score = d.score or 0
        type_priority = {"rag": 0, "pubmed": 1, "web": 2}.get(source_type, 3)
        return (type_priority, -score)

    unique.sort(key=sort_key)
    return unique[:max_total]


def _filter_cited_sources(
    answer: str,
    all_sources: list[dict],
) -> list[dict]:
    """
    Filter sources to only include those actually cited in the answer.
    Looks for [N] patterns in the text and returns only matching sources.
    If no citations found at all, returns empty list.
    """
    cited_nums = set()
    for match in re.finditer(r"\[(\d+)\]", answer):
        cited_nums.add(int(match.group(1)))

    if not cited_nums:
        return []

    cited_sources = []
    for i, source in enumerate(all_sources):
        ref_num = i + 1
        if ref_num in cited_nums:
            source["ref_num"] = ref_num
            cited_sources.append(source)

    return cited_sources


def _is_trustworthy_domain(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    trusted = (
        ".gob.mx",
        ".gov",
        ".edu",
        "who.int",
        "paho.org",
        "ops.org",
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "sciencedirect.com",
        "nature.com",
        "thelancet.com",
        "bmj.com",
    )
    return any(d in domain for d in trusted)


def _source_priority(doc: Document) -> tuple:
    source_type = doc.meta.get("source_type", "rag")
    url = doc.meta.get("url", "")
    score = doc.score or 0
    trusted = 0 if _is_trustworthy_domain(url) else 1
    type_priority = {"rag": 0, "pubmed": 0, "web": 1, "webpage": 1}.get(source_type, 2)
    return (trusted, type_priority, -score)


def _extract_links(html: str, base_url: str) -> list[str]:
    links = []
    for match in re.finditer(r'href=["\\\']([^"\\\']+)["\\\']', html, re.IGNORECASE):
        href = match.group(1).strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        if href.startswith("/"):
            href = urljoin(base_url, href)
        elif not href.startswith("http"):
            href = urljoin(base_url, href)
        links.append(href)
    return links


async def _fetch_url_content(url: str, timeout: float = 20.0) -> tuple[str, str, list[str]]:
    """
    Fetch a URL and return (title, text_content, links). Returns ("", "", []) on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=BROWSER_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                return "", "", []
            html = resp.text
    except Exception as e:
        logger.warning(f"Research fetch failed for {url}: {e}")
        return "", "", []

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = ""
    if title_match:
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

    # Extract links
    links = _extract_links(html, url) if html else []

    h2t = html2text.HTML2Text()
    h2t.ignore_links = True
    h2t.ignore_images = True
    h2t.body_width = 0
    text = h2t.handle(html)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text[:10000], links


def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from a text blob."""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return json.loads(text[start : end + 1])
    except Exception:
        return None


async def _build_research_plan(question: str, generator) -> dict:
    """
    Build a simple research plan using the LLM.
    Returns a dict with keys: focus, queries, sections.
    In Phase 2, question may include user specifications/clarifications — those OVERRIDE the original topic.
    """
    system = (
        "Eres un planificador de investigación en salud para México. "
        "Evalúa si la pregunta es viable para investigar. "
        "Devuelve SOLO JSON válido sin texto extra."
    )
    user = (
        "Evalúa la siguiente pregunta y genera un plan de investigación. "
        "Si la pregunta no tiene sentido, es gibberish, o no es investigable, "
        "pon viable=false.\n"
        "REGLA CRÍTICA: Si el usuario proporcionó ESPECIFICACIONES Y ACLARACIONES, "
        "estas OBLIGATORIAMENTE reemplazan o aclaran el tema original. "
        "Ejemplo: si el usuario escribió 'IC' y luego aclaró 'me refería a Insuficiencia Cardiaca', "
        "las queries DEBEN ser sobre Insuficiencia Cardiaca, NO sobre infección crónica (u otro IC)."
        "\n"
        "Formato JSON:\n"
        "{"
        "\"viable\": true/false, "
        "\"reason\": \"razón si no es viable\", "
        "\"focus\": \"enfoque específico de la investigación\", "
        "\"queries\": [\"consulta1\", \"query2\", \"consulta3\", \"query4\", \"consulta5\", \"query6\"], "
        "\"sections\": [\"Resumen ejecutivo\", \"Contexto\", \"Hallazgos principales\", \"Análisis detallado\", \"Discusión\", \"Limitaciones\", \"Conclusiones\"]"
        "}\n"
        "REGLAS PARA QUERIES:\n"
        "- Genera 5-7 consultas MUY ESPECÍFICAS al tema exacto que pide el usuario.\n"
        "- Si hay aclaraciones del usuario, las queries DEBEN reflejar EXACTAMENTE esas aclaraciones.\n"
        "- Al menos 3 consultas en INGLÉS con términos técnicos/MeSH para PubMed.\n"
        "- Al menos 2 consultas en ESPAÑOL para búsqueda web.\n"
        "- Las consultas deben usar los términos EXACTOS del tema (no generalices).\n"
        "- Incluye variaciones: sinónimos, términos técnicos, combinaciones.\n"
        f"Pregunta y contexto:\n{question}"
    )
    messages = [
        ChatMessage.from_system(system),
        ChatMessage.from_user(user),
    ]
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: generator.run(messages=messages),
            ),
            timeout=90.0,  # ominis-2.0 plan call timeout
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        plan = _extract_json_object(text) or {}
    except asyncio.TimeoutError:
        logger.error("Research plan timeout: ominis-2.0 did not respond in 90s")
        plan = {"viable": False, "reason": "ominis-2.0 no respondió a tiempo. Verifica que el servicio esté disponible."}
    except Exception as e:
        logger.error(f"Research plan error: {e}", exc_info=True)
        plan = {}

    viable = plan.get("viable", True)
    if isinstance(viable, str):
        viable = viable.lower() not in ("false", "no", "0")

    queries = plan.get("queries") if isinstance(plan.get("queries"), list) else []
    sections = plan.get("sections") if isinstance(plan.get("sections"), list) else []
    focus = plan.get("focus", "") if isinstance(plan.get("focus"), str) else ""
    reason = plan.get("reason", "") if isinstance(plan.get("reason"), str) else ""

    if not queries:
        queries = [question]
    if not sections:
        sections = ["Resumen", "Hallazgos", "Evidencia", "Limitaciones", "Conclusiones"]

    return {
        "viable": viable,
        "reason": reason,
        "focus": focus,
        "queries": queries[:6],
        "sections": sections[:8],
    }


async def _refine_search_query(
    question: str,
    history: list[dict] | None,
    generator,
) -> list[str]:
    """
    Use the LLM to generate optimal search queries based on the user's
    question and conversation history. Returns a list of refined queries.
    """
    system = (
        "Eres un experto en búsquedas académicas y de salud para México. "
        "Tu tarea es analizar la pregunta del usuario Y el historial de conversación completo "
        "para generar las mejores consultas de búsqueda posibles. "
        "Devuelve SOLO un JSON válido sin texto extra.\n\n"
        "REGLAS:\n"
        "- Genera 2-4 consultas optimizadas para buscar en PubMed, web y bases de datos.\n"
        "- Analiza TODO el historial para entender el contexto completo, no solo el último mensaje.\n"
        "- Si el usuario dice algo breve como 'dame más detalles' o 'los más recientes', "
        "infiere QUÉ quiere basándote en el historial previo.\n"
        "- Para PubMed, genera consultas en INGLÉS con términos MeSH cuando sea posible.\n"
        "- Para web, genera consultas en ESPAÑOL enfocadas en México.\n"
        "- SIEMPRE incluye 'Mexico' o 'Mexican' en al menos una consulta, a menos que el usuario "
        "especifique otro país.\n"
        "- Si el usuario menciona un nombre propio, incluye variaciones del nombre.\n"
        "- Responde SOLO JSON."
    )
    user_parts = []
    if history:
        recent = history[-6:]
        hist = "\n".join([f"{m.get('role')}: {m.get('content','')[:300]}" for m in recent])
        user_parts.append(f"HISTORIAL DE CONVERSACIÓN:\n{hist}")
    user_parts.append(f"ÚLTIMO MENSAJE DEL USUARIO: {question}")
    user_parts.append(
        'Genera consultas que capturen la INTENCIÓN REAL del usuario basándote en todo el contexto.\n'
        'Formato: {"queries": ["consulta para web en español", "query for PubMed in English", "otra consulta"]}'
    )

    messages = [
        ChatMessage.from_system(system),
        ChatMessage.from_user("\n\n".join(user_parts)),
    ]
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: generator.run(messages=messages)
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        obj = _extract_json_object(text) or {}
        queries = obj.get("queries", [])
        if isinstance(queries, list) and queries:
            return [str(q) for q in queries[:3]]
    except Exception as e:
        logger.warning(f"Query refinement failed: {e}")
    return []


async def _score_source_relevance(
    topic: str,
    user_spec: str,
    documents: list[Document],
    generator,
) -> list[Document]:
    """
    Use LLM to score and filter documents for relevance to the research topic.
    Returns only the documents deemed relevant, sorted by relevance.
    """
    if not documents or len(documents) <= 5:
        return documents

    # Build a compact list of sources for the LLM to evaluate
    source_list = ""
    for i, doc in enumerate(documents):
        title = doc.meta.get("title", "Sin título")[:60]
        content_preview = (doc.content or "")[:150].replace("\n", " ")
        source_list += f"[{i}] {title} — {content_preview}\n"

    system = (
        "Eres un evaluador de relevancia de fuentes para investigación. "
        "Devuelve SOLO JSON con los índices de las fuentes relevantes."
    )
    user = (
        f"TEMA DE INVESTIGACIÓN: {topic}\n"
        f"ESPECIFICACIONES DEL USUARIO: {user_spec}\n\n"
        f"FUENTES ENCONTRADAS:\n{source_list}\n"
        "Evalúa cada fuente y devuelve los ÍNDICES de las que son relevantes para esta investigación específica. "
        "Descarta fuentes que no tienen relación directa con el tema.\n"
        'Formato: {"relevant": [0, 2, 5, 8], "reason": "breve explicación"}'
    )

    try:
        import asyncio as _aio
        loop = _aio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: generator.run(messages=[
                ChatMessage.from_system(system),
                ChatMessage.from_user(user),
            ])
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        obj = _extract_json_object(text) or {}
        relevant_indices = obj.get("relevant", [])
        if isinstance(relevant_indices, list):
            filtered = [documents[i] for i in relevant_indices if isinstance(i, int) and 0 <= i < len(documents)]
            if filtered:
                logger.info(f"Relevance filter: {len(documents)} → {len(filtered)} sources")
                return filtered
    except Exception as e:
        logger.warning(f"Relevance scoring failed: {e}")

    return documents  # Fallback: return all


async def _gather_sources(
    question: str,
    rag_search: bool,
    web_search: bool,
    pubmed_search: bool,
    num_sources: int,
    manager,
    refined_queries: list[str] | None = None,
) -> list[Document]:
    """
    Gather documents from all enabled search sources in parallel.
    Uses Haystack components for each search type.
    If refined_queries are provided, also searches with those.
    """
    tasks = []

    # RAG retrieval (using Haystack embedder + retriever components)
    if rag_search:
        async def do_rag():
            try:
                text_embedder = manager.get_text_embedder()
                retriever = manager.get_retriever()
                embed_result = text_embedder.run(text=question)
                query_embedding = embed_result["embedding"]
                result = retriever.run(
                    query_embedding=query_embedding,
                    top_k=num_sources * 2,
                )
                docs = result.get("documents", [])
                valid = []
                for d in docs:
                    score = d.score or 0
                    if d.content and d.meta.get("url") and score >= 0.5:
                        d.meta["source_type"] = d.meta.get("source_type", "rag")
                        valid.append(d)
                valid.sort(key=lambda d: d.score or 0, reverse=True)
                return valid[:num_sources]
            except Exception as e:
                logger.error(f"RAG retrieval error: {e}", exc_info=True)
                return []
        tasks.append(do_rag())

    # Web search (Haystack WebSearchComponent)
    if web_search:
        async def do_web():
            try:
                return await search_web(question, max_results=num_sources)
            except Exception as e:
                logger.error(f"Web search error: {e}", exc_info=True)
                return []
        tasks.append(do_web())

    # PubMed search (Haystack PubMedSearchComponent)
    if pubmed_search:
        async def do_pubmed():
            try:
                return await search_pubmed(question, max_results=num_sources)
            except Exception as e:
                logger.error(f"PubMed search error: {e}", exc_info=True)
                return []
        tasks.append(do_pubmed())

    # Also search with refined queries if provided
    if refined_queries:
        for rq in refined_queries:
            if web_search:
                async def do_web_refined(q=rq):
                    try:
                        return await search_web(q, max_results=num_sources)
                    except Exception:
                        return []
                tasks.append(do_web_refined())
            if pubmed_search:
                async def do_pubmed_refined(q=rq):
                    try:
                        return await search_pubmed(q, max_results=num_sources)
                    except Exception:
                        return []
                tasks.append(do_pubmed_refined())

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[Document] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Search task failed: {result}")
            continue
        if isinstance(result, list):
            combined.extend(result)

    return combined


# --- File extraction endpoint ---

ALLOWED_FILE_EXTENSIONS = {".pdf", ".csv", ".xls", ".xlsx", ".doc", ".docx"}
MAX_EXTRACT_SIZE = 30 * 1024 * 1024  # 30 MB


@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    """
    Extract text content from an uploaded file (PDF, CSV, XLS, XLSX, DOC, DOCX).
    Returns the extracted text for use as context in a query.
    """
    import csv
    import io
    import tempfile
    from pathlib import Path

    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_FILE_EXTENSIONS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no soportado: {ext}. Formatos válidos: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_EXTRACT_SIZE:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 30 MB")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(content)
    tmp.close()
    tmp_path = Path(tmp.name)

    try:
        extracted = ""

        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(tmp_path))
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"[Página {i+1}]\n{text.strip()}")
            extracted = "\n\n".join(pages)

        elif ext == ".csv":
            raw = content.decode("utf-8", errors="replace")
            reader_csv = csv.reader(io.StringIO(raw))
            rows = list(reader_csv)
            if rows:
                headers = rows[0]
                extracted = f"Columnas: {', '.join(headers)}\n"
                extracted += f"Total de filas: {len(rows) - 1}\n\n"
                for row in rows[1:201]:  # first 200 data rows
                    extracted += " | ".join(row) + "\n"
                if len(rows) > 201:
                    extracted += f"\n... ({len(rows) - 201} filas más)"

        elif ext in (".xls", ".xlsx"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(str(tmp_path), read_only=True, data_only=True)
                parts = []
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    rows = list(ws.iter_rows(values_only=True))
                    if not rows:
                        continue
                    headers = [str(c) if c is not None else "" for c in rows[0]]
                    part = f"## Hoja: {sheet_name}\nColumnas: {', '.join(headers)}\nFilas: {len(rows) - 1}\n\n"
                    for row in rows[1:201]:
                        part += " | ".join(str(c) if c is not None else "" for c in row) + "\n"
                    if len(rows) > 201:
                        part += f"\n... ({len(rows) - 201} filas más)"
                    parts.append(part)
                extracted = "\n\n".join(parts)
            except Exception:
                # Fallback for .xls
                import xlrd
                wb = xlrd.open_workbook(str(tmp_path))
                parts = []
                for sheet in wb.sheets():
                    if sheet.nrows == 0:
                        continue
                    headers = [str(sheet.cell_value(0, c)) for c in range(sheet.ncols)]
                    part = f"## Hoja: {sheet.name}\nColumnas: {', '.join(headers)}\nFilas: {sheet.nrows - 1}\n\n"
                    for r in range(1, min(sheet.nrows, 201)):
                        vals = [str(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
                        part += " | ".join(vals) + "\n"
                    if sheet.nrows > 201:
                        part += f"\n... ({sheet.nrows - 201} filas más)"
                    parts.append(part)
                extracted = "\n\n".join(parts)

        elif ext in (".doc", ".docx"):
            from docx import Document as DocxDocument
            doc = DocxDocument(str(tmp_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            extracted = "\n\n".join(paragraphs)

        # Truncate to avoid overwhelming the LLM context
        if len(extracted) > 15000:
            extracted = extracted[:15000] + "\n\n... [contenido truncado por longitud]"

        return {
            "filename": filename,
            "extension": ext,
            "text": extracted,
            "chars": len(extracted),
        }

    finally:
        tmp_path.unlink(missing_ok=True)


# --- PDF generation endpoint ---

class GeneratePdfRequest(BaseModel):
    content: str
    title: Optional[str] = "OMINIS Report"


@router.post("/generate-pdf")
async def generate_pdf_endpoint(body: GeneratePdfRequest):
    """
    Generate a PDF from markdown content.
    Returns PDF file for download.
    """
    import asyncio
    from fastapi.responses import Response

    title = (body.title or "OMINIS Report").strip() or "OMINIS Report"
    # Limit content size to avoid DoS
    content = (body.content or "")[:500000]

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        lambda: generate_pdf(content, title=title),
    )

    if pdf_bytes is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="PDF generation is not available. Install weasyprint and markdown.",
        )

    # Safe filename from title
    import re
    safe_title = re.sub(r'[^\w\s\-]', '', title)[:60].strip() or "ominis-report"
    safe_title = re.sub(r'\s+', '-', safe_title)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"',
        },
    )


# --- Model listing endpoint ---

@router.get("/models")
async def list_models():
    """List available Ominis models (public metadata only)."""
    manager = get_pipeline_manager()
    return {"models": manager.available_models, "default": "ominis-2.0"}


# --- Streaming endpoint ---

@router.post("/query-stream")
async def query_stream(body: QueryRequest, request: Request):
    """
    Streaming query endpoint using Haystack OllamaChatGenerator.
    Supports RAG, web search, PubMed, and vision (multimodal).
    """
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    public_model_id = manager.get_public_model_id(model_id)

    async def event_generator():
        start_time = time.time()
        full_answer = ""
        sources_list = []

        try:
            has_image = body.image and len(body.image) > 50
            image_description = ""

            # Step 0: Vision analysis using OllamaChatGenerator + ImageContent
            if has_image:
                yield sse_event({
                    "type": "status",
                    "message": "Analizando imagen...",
                    "model": public_model_id,
                })
                vision_gen = manager.get_vision_generator()
                image_description = await analyze_image(
                    image_b64=body.image,
                    question=body.question,
                    vision_generator=vision_gen,
                )

            # Status: searching
            search_parts = []
            if body.rag_search:
                search_parts.append("base de datos")
            if body.web_search:
                search_parts.append("web")
            if body.pubmed_search:
                search_parts.append("PubMed")

            if search_parts:
                status_msg = f"Buscando en {', '.join(search_parts)}..."
            else:
                status_msg = "Generando respuesta..."

            yield sse_event({
                "type": "status",
                "message": status_msg,
                "model": public_model_id,
            })

            # Step 1: Use LLM to generate optimal search queries from context
            generator = manager.get_generator(model_id)
            history_dicts = [msg.model_dump() for msg in body.history] if body.history else None
            refined_queries: list[str] = []

            # Always refine when there's history (context matters)
            # or when web/pubmed search is enabled (to get Mexico-focused results)
            if (history_dicts and len(history_dicts) > 0) or body.web_search or body.pubmed_search:
                yield sse_event({
                    "type": "status",
                    "message": "Analizando consulta...",
                })
                refined_queries = await _refine_search_query(
                    question=body.question,
                    history=history_dicts,
                    generator=generator,
                )
                if refined_queries:
                    logger.info(f"LLM-refined queries: {refined_queries}")

            # Gather sources using both the original question AND refined queries
            raw_documents = await _gather_sources(
                question=body.question,
                rag_search=body.rag_search,
                web_search=body.web_search,
                pubmed_search=body.pubmed_search,
                num_sources=body.num_sources,
                manager=manager,
                refined_queries=refined_queries if refined_queries else None,
            )

            documents = _deduplicate_and_rank(raw_documents, max_total=8)

            all_sources_list = [
                _doc_to_source(doc) for doc in documents
                if doc.content and doc.meta.get("url")
            ]

            if all_sources_list:
                yield sse_event({"type": "sources", "sources": all_sources_list})

            yield sse_event({
                "type": "status",
                "message": "Generando respuesta...",
            })

            # Step 2: Build ChatMessage objects (Haystack native)
            messages = build_chat_messages(
                question=body.question,
                documents=documents,
                history=[msg.model_dump() for msg in body.history] if body.history else [],
                image_description=image_description,
                file_context=body.file_context or "",
            )

            # Step 3: Stream generation via OllamaChatGenerator
            chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

            def streaming_callback(chunk: StreamingChunk):
                text = chunk.content
                if text:
                    chunk_queue.put_nowait(text)

            generator = manager.get_generator(model_id)

            async def run_generator():
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: generator.run(
                        messages=messages,
                        streaming_callback=streaming_callback,
                    ),
                )
                await chunk_queue.put(None)
                return result

            gen_task = asyncio.create_task(run_generator())

            while True:
                try:
                    token = await asyncio.wait_for(chunk_queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    yield sse_event({"type": "error", "message": "Generation timed out"})
                    break

                if token is None:
                    break

                token = _sanitize_text(token)
                full_answer += token
                yield sse_event({"type": "chunk", "text": token})

            await gen_task

            sources_list = _filter_cited_sources(full_answer, all_sources_list)
            charts: list[dict] = []
            try:
                chart_specs = await generate_chart_specs(
                    question=body.question,
                    answer=full_answer,
                    documents=documents,
                    history=[msg.model_dump() for msg in body.history] if body.history else [],
                    generator=generator,
                )
                charts = render_chart_images(chart_specs)
                if charts:
                    yield sse_event({"type": "charts", "charts": charts})
            except Exception as e:
                logger.error(f"Chart generation error: {e}", exc_info=True)

            elapsed_ms = int((time.time() - start_time) * 1000)
            yield sse_event({
                "type": "done",
                "answer": full_answer,
                "sources": sources_list,
                "charts": charts if charts else None,
                "model": public_model_id,
                "elapsed_ms": elapsed_ms,
            })

            asyncio.create_task(
                _log_query(
                    question=body.question,
                    answer=full_answer,
                    sources=sources_list,
                    elapsed_ms=elapsed_ms,
                    model_used=model_id,
                    rag_search=body.rag_search,
                    web_search=body.web_search,
                    pubmed_search=body.pubmed_search,
                )
            )

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield sse_event({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Public model IDs
ACADEMIC_MODEL_ID = "ominis-2.0-research"
ACADEMIC_MODEL_ID_128K = "ominis-2.0-research-128k"


def _get_research_generator_and_model_id():
    """
    Choose research generator and model id: 128K if running, else 8K if running, else Ollama (ominis-2.0).
    Returns (generator, public_model_id).
    """
    manager = get_pipeline_manager()
    active = get_active_research_key()
    if active == "openscholar_128k":
        try:
            return get_openscholar_128k_generator(), ACADEMIC_MODEL_ID_128K
        except ValueError:
            pass
    if active == "openscholar":
        return get_openscholar_generator(), ACADEMIC_MODEL_ID
    # Both research instances off: use normal Ollama (ominis-2.0)
    return manager.get_generator(), "ominis-2.0"


async def _research_stream_events(body: ResearchRequest):
    """
    Shared event generator for research/academic mode.
    Routes to 128K if that instance is running, else OpenScholar 8K if running, else Ollama (ominis-2.0).
    """
    manager = get_pipeline_manager()
    generator, public_model_id = _get_research_generator_and_model_id()
    logger.info("Research mode: using %s", public_model_id)

    start_time = time.time()
    full_answer = ""
    sources_list = []

    try:
        has_image = body.image and len(body.image) > 50
        image_description = ""

        if has_image:
            yield sse_event({
                "type": "status",
                "message": "Analizando imagen...",
                "model": public_model_id,
            })
            vision_gen = manager.get_vision_generator()
            image_description = await analyze_image(
                image_b64=body.image,
                question=body.question,
                vision_generator=vision_gen,
            )

        # Detect phase: is user replying to a previous plan?
        history_dicts = [msg.model_dump() for msg in body.history] if body.history else []
        is_phase2 = False
        if history_dicts and len(history_dicts) >= 2:
            for msg in history_dicts:
                if msg.get("role") == "assistant" and "?" in (msg.get("content") or "") and len(msg.get("content", "")) > 50:
                    is_phase2 = True
                    break

        # Phase 1 only: validate viability (always runs, regardless of history length)
        if not is_phase2:
            yield sse_event({
                "type": "status",
                "message": "Evaluando consulta...",
                "model": public_model_id,
            })
            plan = await _build_research_plan(body.question, generator)
            if not plan.get("viable", True):
                reason = plan.get("reason", "La pregunta no es clara o no es viable para investigar.")
                yield sse_event({"type": "chunk", "text": f"No es posible investigar esta consulta.\n\n**Razón:** {reason}\n\nReformula tu pregunta con un tema específico."})
                yield sse_event({"type": "done", "answer": f"No viable: {reason}", "sources": [], "model": public_model_id, "elapsed_ms": int((time.time() - start_time) * 1000)})
                return
        else:
            # Phase 2: build plan from the FULL conversation context
            # CRITICAL: user clarifications OVERRIDE ambiguous original topic (e.g. "IC" → "Insuficiencia Cardiaca")
            original_topic = ""
            user_answers = ""
            for msg in history_dicts:
                if msg.get("role") == "user":
                    if not original_topic:
                        original_topic = msg.get("content", "")
                    else:
                        user_answers += msg.get("content", "") + "\n"
            user_answers += body.question  # Current message is also an answer
            # Pass full context so plan reflects user's clarifications (e.g. IC = Insuficiencia Cardiaca, not infección crónica)
            plan_input = f"{original_topic}\n\nESPECIFICACIONES Y ACLARACIONES DEL USUARIO (OBLIGATORIAS — las queries DEBEN reflejar esto):\n{user_answers}"
            plan = await _build_research_plan(plan_input, generator)

        # Search for sources
        queries = plan.get("queries", [])
        research_notes: list[str] = []

        if not is_phase2:
            # Phase 1: quick search for planning
            collected: list[Document] = []
            yield sse_event({"type": "status", "message": "Buscando fuentes iniciales..."})
            docs = await _gather_sources(
                question=queries[0] if queries else body.question,
                rag_search=body.rag_search, web_search=body.web_search,
                pubmed_search=body.pubmed_search, num_sources=5, manager=manager,
            )
            collected.extend(docs)
        else:
            # Phase 2: DEEP research — 3 independent phases, each with its own budget
            collected = []
            seen_urls: set[str] = set()
            research_steps: list[dict] = []
            total_found = 0
            total_read = 0

            def emit_step(action: str, detail: str, url: str = "", result: str = "", reasoning: str = ""):
                step = {"action": action, "detail": detail, "url": url, "result": result, "reasoning": reasoning, "elapsed": int(time.time() - start_time)}
                research_steps.append(step)
                return sse_event({"type": "research_step", "step": step, "progress": {
                    "found": total_found, "read": total_read,
                    "totalSteps": len(research_steps),
                    "elapsedSeconds": step["elapsed"],
                }})

            # ── PHASE A: SEARCH (no time limit — always completes all queries) ──
            focus = plan.get("focus", "")
            yield emit_step("plan", f"Plan: {focus}", result=f"{len(queries)} consultas",
                reasoning=f"Definiendo el plan de investigación para abordar: {focus[:80]}{'...' if len(focus) > 80 else ''}. Consultas iniciales: {len(queries)}.")

            for i, q in enumerate(queries):
                yield sse_event({"type": "status", "message": f"Buscando ({i+1}/{len(queries)}): {q[:50]}..."})
                yield emit_step("search", f"Buscando: {q}",
                    reasoning=f"Buscaré en PubMed, web y bases locales información sobre: {q[:60]}{'...' if len(q) > 60 else ''}. Es relevante para el tema de {focus[:40]}{'...' if len(focus) > 40 else ''}.")
                docs = await _gather_sources(
                    question=q, rag_search=body.rag_search,
                    web_search=body.web_search, pubmed_search=body.pubmed_search,
                    num_sources=body.num_sources, manager=manager,
                )
                collected.extend(docs)
                total_found += len(docs)
                yield emit_step("search_result", f"Resultados: {q[:40]}", result=f"{len(docs)} fuentes",
                    reasoning=f"Encontré {len(docs)} fuentes. Evaluando cuáles profundizar para el reporte.")

            # Refine with user's answers (always runs if answers exist)
            if user_answers.strip():
                yield emit_step("refine", "Refinando con respuestas del usuario",
                    reasoning=f"Refinando con las especificaciones del usuario: {user_answers[:100].replace(chr(10), ' ')}{'...' if len(user_answers) > 100 else ''}")
                yield sse_event({"type": "status", "message": "Refinando búsqueda..."})
                extra_queries = await _refine_search_query(
                    question=f"{original_topic}\nEl usuario especificó: {user_answers}",
                    history=history_dicts, generator=generator,
                )
                for q in extra_queries:
                    yield sse_event({"type": "status", "message": f"Buscando: {q[:50]}..."})
                    yield emit_step("search", f"Refinada: {q}",
                        reasoning=f"Buscando fuentes refinadas según lo que el usuario indicó: {q[:60]}{'...' if len(q) > 60 else ''}")
                    docs = await _gather_sources(
                        question=q, rag_search=False,
                        web_search=body.web_search, pubmed_search=body.pubmed_search,
                        num_sources=body.num_sources, manager=manager,
                    )
                    collected.extend(docs)
                    total_found += len(docs)
                    yield emit_step("search_result", f"Resultados: {q[:40]}", result=f"{len(docs)} fuentes",
                        reasoning=f"Me interesaron {len(docs)} fuentes adicionales. Las incorporaré al análisis.")

            # Deduplicate
            candidates = _deduplicate_and_rank(collected, max_total=40)
            candidates.sort(key=_source_priority)
            yield emit_step("filter", f"{len(collected)} → {len(candidates)} únicas",
                reasoning=f"Filtrando duplicados: de {len(collected)} resultados a {len(candidates)} fuentes únicas para leer.")

            # ── PHASE B: READ ALL SOURCES (web + PubMed full text) ──
            read_deadline = time.time() + 150  # 2.5 min for reading
            fetched_count = 0
            follow_urls: list[str] = []

            # Read ALL sources — web snippets need full pages, PubMed abstracts
            readable = []
            for d in candidates:
                url = d.meta.get("url", "")
                if url and url not in seen_urls:
                    readable.append(d)

            yield emit_step("read_start", f"Leyendo {len(readable)} fuentes de {len(candidates)} candidatas",
                reasoning=f"Identificando fuentes para leer en detalle. Tomaré notas de cada una para el reporte final.")

            for doc in readable:
                if time.time() > read_deadline or fetched_count >= body.max_follow_links:
                    yield emit_step("read_skip", f"Límite alcanzado: {fetched_count}/{body.max_follow_links} leídas",
                        reasoning="Respetando el límite de fuentes para garantizar un reporte enfocado y completo.")
                    break
                url = doc.meta.get("url", "")
                seen_urls.add(url)
                title_hint = doc.meta.get("title", "")[:50]

                yield sse_event({"type": "status", "message": f"Leyendo ({fetched_count+1}/{len(readable)}): {title_hint or url[:40]}..."})
                yield emit_step("read", f"Leyendo: {title_hint}", url=url,
                    reasoning=f"Leyendo esta fuente para extraer datos relevantes sobre {focus[:50]}{'...' if len(focus) > 50 else ''}.")
                try:
                    title, text, links = await _fetch_url_content(url)
                except Exception as e:
                    yield emit_step("read_fail", f"Error: {title_hint}", url=url, result=str(e)[:80],
                        reasoning="No pude extraer contenido de esta fuente. Continuando con otras.")
                    continue
                if text and len(text) > 50:
                    collected.append(Document(
                        content=text,
                        meta={"title": title or title_hint, "url": url, "source_type": "webpage"},
                    ))
                    fetched_count += 1
                    total_read += 1
                    preview = text[:200].replace("\n", " ")
                    note = f"{title or title_hint}: {preview}"
                    research_notes.append(note)
                    yield emit_step("read_done", f"{title or title_hint}", url=url, result=f"{len(text)} chars — {preview[:80]}",
                        reasoning=f"Hallazgo: {preview[:120]}... Tomando nota para citar en el reporte.")
                    for link in links:
                        if _is_trustworthy_domain(link) and link not in seen_urls:
                            follow_urls.append(link)
                else:
                    yield emit_step("read_fail", f"Sin contenido útil", url=url, result=f"{len(text or '')} chars",
                        reasoning="Contenido no útil. Marcando para no incluir en el reporte.")

            # ── PHASE C: FOLLOW TRUSTED LINKS (separate budget) ──
            if follow_urls and time.time() < read_deadline:
                unique_follows = []
                for link in follow_urls:
                    if link not in seen_urls and len(unique_follows) < body.max_follow_links:
                        unique_follows.append(link)
                if unique_follows:
                    yield emit_step("follow", f"Siguiendo {len(unique_follows)} enlaces confiables",
                        reasoning=f"Explorando enlaces adicionales de fuentes confiables para ampliar la investigación.")
                    for link in unique_follows:
                        if time.time() > read_deadline or fetched_count >= body.max_follow_links * 2:
                            break
                        seen_urls.add(link)
                        yield sse_event({"type": "status", "message": f"Siguiendo: {link[:50]}..."})
                        yield emit_step("read", "Enlace", url=link,
                            reasoning="Leyendo enlace secundario para completar el contexto.")
                        title, text, _ = await _fetch_url_content(link)
                        if text:
                            collected.append(Document(
                                content=text,
                                meta={"title": title or "", "url": link, "source_type": "webpage"},
                            ))
                            fetched_count += 1
                            total_read += 1
                            follow_preview = (text or "")[:200].replace("\n", " ")
                            research_notes.append(f"{title or link[:40]}: {follow_preview}")
                            yield emit_step("read_done", f"{title or link[:40]}", url=link, result=f"{len(text)} chars",
                                reasoning="Contenido adicional útil. Incorporando al análisis.")

            elapsed_search = int(time.time() - start_time)
            yield emit_step("complete", "Investigación completa", result=f"{total_found} encontradas, {total_read} leídas, {elapsed_search}s",
                reasoning=f"Consolidando lo que he encontrado: {total_found} fuentes encontradas, {total_read} leídas. Preparando el reporte con citas específicas.")
            logger.info(f"Deep research: {total_found} found, {total_read} read, {fetched_count} fetched, {elapsed_search}s")

        # Final source selection (runs for both Phase 1 and Phase 2)
        documents = _deduplicate_and_rank(collected, max_total=body.max_total_sources)

        # Remove user-excluded sources
        if body.excluded_sources:
            excluded_set = set(body.excluded_sources)
            before = len(documents)
            documents = [d for d in documents if d.meta.get("url", "") not in excluded_set]
            if is_phase2 and before != len(documents):
                yield emit_step("filter", f"Excluidas {before - len(documents)} fuentes por el usuario",
                    reasoning="Respetando las fuentes que el usuario decidió excluir del plan.")

        # Phase 2: filter for relevance using LLM before generating report
        if is_phase2 and len(documents) > 5:
            yield sse_event({"type": "status", "message": "Evaluando relevancia de fuentes..."})
            yield emit_step("relevance", f"Evaluando {len(documents)} fuentes para relevancia",
                reasoning=f"Identificando cuáles de {len(documents)} fuentes son más relevantes para el tema del usuario.")
            documents = await _score_source_relevance(
                topic=original_topic,
                user_spec=user_answers,
                documents=documents,
                generator=generator,
            )
            yield emit_step("relevance_done", f"{len(documents)} fuentes relevantes seleccionadas",
                reasoning=f"Seleccionadas las {len(documents)} fuentes más pertinentes para elaborar el reporte detallado.")

        all_sources_list = [
            _doc_to_source(doc) for doc in documents
            if doc.content and doc.meta.get("url")
        ]

        if all_sources_list:
            yield sse_event({"type": "sources", "sources": all_sources_list})
            if is_phase2:
                yield emit_step("sources", f"{len(all_sources_list)} fuentes para el reporte",
                    reasoning=f"Generando reporte con {len(all_sources_list)} fuentes, citando científicamente cada origen.")

        yield sse_event({
            "type": "status",
            "message": "Generando reporte..." if is_phase2 else "Preparando plan...",
        })

        # Build messages — ominis-2.0-research academic prompt
        messages = build_academic_messages(
            question=body.question,
            documents=documents,
            plan=plan,
            history=history_dicts,
            image_description=image_description,
            file_context=body.file_context or "",
            is_phase2=is_phase2,
            research_notes=research_notes if is_phase2 else None,
            excluded_topics=body.excluded_topics or None,
        )

        # Phase 2: set max_tokens so input + output never exceed model context
        if is_phase2:
            ctx_limit = MODEL_CTX_LIMIT_128K if public_model_id == ACADEMIC_MODEL_ID_128K else MODEL_CTX_LIMIT
            input_tokens = _estimate_input_tokens_from_messages(messages)
            space_for_output = ctx_limit - input_tokens - OUTPUT_TOKEN_BUFFER
            max_tokens_cap = 8192 if public_model_id == ACADEMIC_MODEL_ID_128K else MAX_OUTPUT_TOKENS_CAP
            max_tokens = max(MIN_OUTPUT_TOKENS, min(max_tokens_cap, space_for_output))
            research_gen_kwargs = {"max_tokens": max_tokens, "temperature": 0.3}
            logger.info("Research report: input_tokens≈%s, max_tokens=%s", input_tokens, max_tokens)
        else:
            research_gen_kwargs = {}

        chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def streaming_callback(chunk: StreamingChunk):
            text = chunk.content
            if text:
                chunk_queue.put_nowait(text)

        async def run_generator():
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: generator.run(
                        messages=messages,
                        streaming_callback=streaming_callback,
                        generation_kwargs=research_gen_kwargs,
                    ),
                )
            except Exception as e:
                logger.error(f"ominis-2.0 generation failed: {e}", exc_info=True)
                raise
            finally:
                chunk_queue.put_nowait(None)  # unblock consumer loop
            return result

        # Timeout: 150s (ominis-2.0 HTTP timeout is 120s; extra buffer for slow responses)
        gen_task = asyncio.create_task(
            asyncio.wait_for(run_generator(), timeout=150.0)
        )

        while True:
            try:
                token = await asyncio.wait_for(chunk_queue.get(), timeout=160.0)
            except asyncio.TimeoutError:
                gen_task.cancel()
                try:
                    await gen_task
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass
                yield sse_event({
                    "type": "error",
                    "message": "ominis-2.0 no respondió a tiempo. Verifica que el servicio esté disponible o intenta de nuevo.",
                })
                return

            if token is None:
                break

            token = _sanitize_text(token)
            full_answer += token
            yield sse_event({"type": "chunk", "text": token})

        try:
            await gen_task
        except asyncio.TimeoutError:
            yield sse_event({
                "type": "error",
                "message": "ominis-2.0 no respondió a tiempo. Verifica que el servicio esté disponible o intenta de nuevo.",
            })
            return
        except Exception as e:
            err_msg = str(e)
            if "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                yield sse_event({
                    "type": "error",
                    "message": "ominis-2.0 no respondió a tiempo. Verifica que el servicio esté disponible o intenta de nuevo.",
                })
            else:
                yield sse_event({"type": "error", "message": f"Error de ominis-2.0: {err_msg}"})
            return

        sources_list = _filter_cited_sources(full_answer, all_sources_list)
        charts: list[dict] = []
        answer_for_client = full_answer
        try:
            # 1) Prefer charts embedded by the report LLM (```chart block)
            chart_specs = parse_chart_specs_from_text(full_answer)
            if chart_specs:
                charts = render_chart_images(chart_specs)
                answer_for_client = strip_chart_block_from_text(full_answer)
            # 2) If no embedded charts and this is a research report, ask chart LLM to suggest from report
            if not charts and is_phase2:
                chart_specs = await generate_chart_specs(
                    question=body.question,
                    answer=full_answer,
                    documents=documents,
                    history=[msg.model_dump() for msg in body.history] if body.history else [],
                    generator=generator,
                    force=True,
                )
                charts = render_chart_images(chart_specs)
            # 3) Non-research: only suggest charts when question looks chart-related
            elif not charts:
                chart_specs = await generate_chart_specs(
                    question=body.question,
                    answer=full_answer,
                    documents=documents,
                    history=[msg.model_dump() for msg in body.history] if body.history else [],
                    generator=generator,
                )
                charts = render_chart_images(chart_specs)
            if charts:
                yield sse_event({"type": "charts", "charts": charts})
        except Exception as e:
            logger.error(f"Chart generation error: {e}", exc_info=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        yield sse_event({
            "type": "done",
            "answer": answer_for_client,
            "sources": sources_list,
            "charts": charts if charts else None,
            "model": public_model_id,
            "elapsed_ms": elapsed_ms,
            "is_report": is_phase2,  # Flag: this is a research report
        })

        asyncio.create_task(
            _log_query(
                question=body.question,
                answer=answer_for_client,
                sources=sources_list,
                elapsed_ms=elapsed_ms,
                model_used=public_model_id,
                rag_search=body.rag_search,
                web_search=body.web_search,
                pubmed_search=body.pubmed_search,
            )
        )

    except Exception as e:
        logger.error(f"Research streaming error: {e}", exc_info=True)
        yield sse_event({"type": "error", "message": str(e)})


@router.post("/query-research-stream")
async def query_research_stream(body: ResearchRequest, request: Request):
    """
    Research mode streaming endpoint.
    Uses ominis-2.0 (academic LLM) exclusively — per architecture.
    """
    return StreamingResponse(
        _research_stream_events(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/academic_query-stream")
async def academic_query_stream(body: ResearchRequest, request: Request):
    """
    Modo Investigación (ominis-2.0) — same as query-research-stream.
    Deterministic routing: research mode always uses ominis-2.0.
    """
    return StreamingResponse(
        _research_stream_events(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Non-streaming endpoint ---

@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest):
    """Non-streaming query endpoint using Haystack OllamaChatGenerator."""
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    public_model_id = manager.get_public_model_id(model_id)

    start_time = time.time()

    # Vision analysis
    has_image = body.image and len(body.image) > 50
    image_description = ""
    if has_image:
        vision_gen = manager.get_vision_generator()
        image_description = await analyze_image(
            image_b64=body.image,
            question=body.question,
            vision_generator=vision_gen,
        )

    # Gather sources
    raw_documents = await _gather_sources(
        question=body.question,
        rag_search=body.rag_search,
        web_search=body.web_search,
        pubmed_search=body.pubmed_search,
        num_sources=body.num_sources,
        manager=manager,
    )
    documents = _deduplicate_and_rank(raw_documents, max_total=8)

    # Build ChatMessages and generate
    messages = build_chat_messages(
        question=body.question,
        documents=documents,
        history=[msg.model_dump() for msg in body.history] if body.history else [],
        image_description=image_description,
        file_context=body.file_context or "",
    )

    generator = manager.get_generator(model_id)
    gen_result = generator.run(messages=messages)
    replies = gen_result.get("replies", [])
    answer = replies[0].text if replies else "No se pudo generar respuesta."

    all_sources = [
        _doc_to_source(doc) for doc in documents
        if doc.content and doc.meta.get("url")
    ]
    sources = _filter_cited_sources(answer, all_sources)
    charts: list[dict] = []
    try:
        chart_specs = await generate_chart_specs(
            question=body.question,
            answer=answer,
            documents=documents,
            history=[msg.model_dump() for msg in body.history] if body.history else [],
            generator=generator,
        )
        charts = render_chart_images(chart_specs)
    except Exception as e:
        logger.error(f"Chart generation error: {e}", exc_info=True)

    elapsed_ms = int((time.time() - start_time) * 1000)

    asyncio.create_task(
        _log_query(
            question=body.question,
            answer=answer,
            sources=sources,
            elapsed_ms=elapsed_ms,
            model_used=model_id,
            rag_search=body.rag_search,
            web_search=body.web_search,
            pubmed_search=body.pubmed_search,
        )
    )

    return QueryResponse(
        answer=answer,
        sources=sources,
        query=body.question,
        model=public_model_id,
        charts=charts if charts else None,
    )


# --- Query logging helper ---

async def _log_query(
    question: str,
    answer: str,
    sources: list[dict],
    elapsed_ms: int,
    model_used: str = "",
    rag_search: bool = True,
    web_search: bool = False,
    pubmed_search: bool = False,
    user_id: Optional[int] = None,
    api_key_id: Optional[int] = None,
):
    """Log a query to the database asynchronously."""
    try:
        from app.database import async_session
        from app.admin.models import QueryLog

        async with async_session() as db:
            log = QueryLog(
                question=question,
                answer=answer,
                sources_used=json.dumps(sources, ensure_ascii=False),
                model_used=model_used or settings.ollama_model,
                response_time_ms=elapsed_ms,
                user_id=user_id,
                api_key_id=api_key_id,
                rag_search=rag_search,
                web_search=web_search,
                pubmed_search=pubmed_search,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to log query: {e}")
