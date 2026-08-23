"""
RAG query routes — Haystack 2.23 native architecture.

Uses OllamaChatGenerator with ChatMessage objects for proper chat/multimodal support.
Integrates web search (DuckDuckGo) and PubMed search as Haystack components.
Vision analysis uses OllamaChatGenerator + ImageContent natively.

SSE event format:
  data: {"type": "status", "message": "..."}\n\n
  data: {"type": "chunk", "text": "..."}\n\n
  data: {"type": "sources", "sources": [...]}\n\n
  data: {"type": "done", "answer": "...", "sources": [...], "sources_not_used": [...]}\n\n
"""

import asyncio
from collections import Counter
import io
import json
import logging
import math
import os
import re
import time
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_optional_user
from app.auth.models import RoleEnum, User
from app.database import get_db
from app.admin.models import ChatDefaults, LLMModelConfig

from haystack import Document
from haystack.dataclasses import ChatMessage, StreamingChunk

import httpx
import html2text

from app.config import DEFAULT_MODEL_ID, get_model_config, get_model_registry, get_settings, normalize_public_model_id
from app.rag.pipeline import (
    SYSTEM_PROMPT,
    _current_datetime_context,
    build_chat_messages,
    get_pipeline_manager,
    openai_chat_completion_generation_kwargs,
)
from app.rag.document_store import get_document_store
from app.rag.charting import generate_chart_specs, parse_chart_specs_from_text, render_chart_images, strip_chart_block_from_text
from app.rag.pdf_generator import generate_pdf
from app.rag.web_search import search_web
from app.rag.pubmed_search import search_pubmed
from app.rag.openscholar_search import search_openscholar
from app.rag.health_datastore import build_evidence_pack
from app.rag.vision import analyze_image
from app.rag.scraper import BROWSER_HEADERS
from app.rag.agents import run_bias_auditor_sync, run_evidence_extractor_sync
from app.rag.med42 import get_med42_generator, run_clinical_translator_sync
from app.rag.openscholar import (
    MODEL_CTX_LIMIT,
    MODEL_CTX_LIMIT_128K,
    build_academic_messages,
    build_section_messages,
    build_section_analysis_prompt,
    get_deepening_queries_prompt,
    get_detailed_outline_prompt,
    get_gap_analysis_prompt,
    get_openscholar_128k_generator,
)
from app.rag.research_quality import (
    deduplicate_and_rank_with_quality,
    extract_reference_metadata,
    format_apa as format_apa_ref,
    post_generation_qa,
    section_similarity_to_previous,
    build_delta_summary,
    REPETITION_SIMILARITY_THRESHOLD,
)
from app.rag.intent import (
    CLINICAL_RISK_LOW,
    conversation_only_default_intent,
    filter_documents_by_intent,
    get_rag_top_k_multiplier,
    heuristic_conversation_only,
    is_conversation_only_turn,
    orchestrate_route,
    run_metadata_intent_mapper,
    should_use_clinical_validator,
    ORCHESTRATOR_ROUTE_MEDICAL,
    ORCHESTRATOR_ROUTE_RESEARCH,
    ORCHESTRATOR_ROUTE_SIMPLE,
)
from app.rag.tool_orchestration import (
    apply_tool_plan_to_query_request,
    eff_from_body,
    format_tool_plan_message,
    infer_tool_sources_heuristic,
    plan_tools_for_query,
    suggest_tools_for_followup,
    tool_labels_es,
)
from app.rag.clinical_validator import (
    content_has_clinical_signals,
    run_clinical_validator_sync,
    format_validator_disclaimer,
    VALIDATOR_UNAVAILABLE_DISCLAIMER,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["query"])

# Approximate chars per token for input estimation (Spanish/English)
CHARS_PER_TOKEN = 4
# Reserve tokens so completion never exceeds model context (buffer large to account for underestimation)
OUTPUT_TOKEN_BUFFER = 1024
MIN_OUTPUT_TOKENS = 512
MAX_OUTPUT_TOKENS_CAP = 4096
# 8K model: never request more than this so input+output stays under 8192 even when estimate is low
MAX_OUTPUT_TOKENS_8K_SAFE = 2048


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
    model: Optional[str] = None  # Model variant (e.g. "ominis-2.0"); orchestrator may override
    research_mode: bool = False  # User toggled "Investigación" / web search; orchestrator may route to Research 128K
    research_2_1: Optional[bool] = None  # Deep research (section-by-section); used when orchestrator routes to research
    excluded_sources: list[str] = []  # When orchestrator routes to research: URLs user deselected from plan
    rag_search: bool = True
    web_search: bool = True
    pubmed_search: bool = True
    openscholar_search: bool = False  # Semantic Scholar / Open Scholar (default off)
    clinical_trials_search: bool = False  # ClinicalTrials.gov (Mexico); requires authenticated user on backend
    doctor_directory_search: bool = False  # Ingested doctor profiles (México); requires login
    allcan_search: bool = False  # All.Can México organizations (Strapi); requires login + server token
    tool_automation: bool = True  # When true, orchestrator sets search tools from intent + heuristics
    num_sources: int = 6  # more hits per backend when orchestrator enables several tools
    file_context: Optional[str] = None  # Extracted text from attached files


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    query: str
    model: str
    charts: Optional[list[dict]] = None
    sources_not_used: Optional[list[dict]] = None


class ResearchRequest(BaseModel):
    question: str
    history: list[HistoryMessage] = []
    image: Optional[str] = None
    model: Optional[str] = None
    research_model: Optional[Literal["openscholar", "openscholar_128k"]] = None  # user preference when both available
    research_2_1: Optional[bool] = None  # Deep multi-round + section-by-section (Dashboard > Opciones). None = use chat_defaults
    rag_search: bool = True
    web_search: bool = True
    pubmed_search: bool = True
    openscholar_search: bool = False
    clinical_trials_search: bool = False
    doctor_directory_search: bool = False
    allcan_search: bool = False
    num_sources: int = 10
    file_context: Optional[str] = None
    iterations: int = 5
    max_total_sources: int = 30
    max_follow_links: int = 25
    max_trusted_sources: int = 15
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


def _strip_invalid_citations(text: str, max_ref: int) -> str:
    """Remove citation numbers [N] where N > max_ref (hallucinated references)."""
    def _replace(m):
        n = int(m.group(1))
        if n < 1 or n > max_ref:
            return ""
        return m.group(0)
    return re.sub(r'\[(\d+)\]', _replace, text)


def _normalize_citation_markers(text: str, max_ref: int) -> str:
    """Normalize citations like (12) to [12] when they look like reference markers."""
    def _replace_paren(m):
        n = int(m.group(1))
        if 1 <= n <= max_ref:
            return f"[{n}]"
        return m.group(0)
    # Keep conservative: convert only single integer markers in parentheses.
    return re.sub(r'\((\d{1,3})\)', _replace_paren, text)


def _dedupe_repeated_paragraphs(text: str) -> str:
    """Remove consecutive repeated paragraphs (common LLM looping failure mode)."""
    if not text:
        return text
    paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paras:
        return text
    out: list[str] = []
    prev_core = ""
    for p in paras:
        norm = re.sub(r'\s+', ' ', p).strip().lower()
        # Ignore citation indices and numbers when detecting loops (e.g. same paragraph with [1] vs [2])
        core = re.sub(r'\[\d+\]|\(\d+\)|\d+[.,]?\d*%?', '', norm)
        core = re.sub(r'[^a-záéíóúñü\s]', '', core)
        core = re.sub(r'\s+', ' ', core).strip()
        if core and core == prev_core:
            continue
        out.append(p)
        prev_core = core
    return "\n\n".join(out)


_HEALTH_TERMS = {
    "salud", "medic", "clinical", "clínic", "hospital", "paciente", "telemed", "diagn", "enfermed",
    "mortal", "morbil", "epidemi", "treatment", "care", "health", "disease", "public health",
}
_OFFTOPIC_TERMS = {
    "mcdonald", "helados", "cine", "microempresa", "tributaria", "banca", "derecho municipal",
    "pagos internacionales", "ganadería", "agroindustrial", "matemáticas", "educación básica",
    "manejo forestal", "forestal sustentable", "bromelias", "epífitas", "biodiversidad",
    "anticoagulante oral", "osasunbide", "telessicolog", "estrés postraumático", "desastres naturales",
    "accesibilidad vial", "urban planning", "mexicali",
}


def _extract_topic_terms(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]{4,}", (text or "").lower())
    stop = {"sobre", "para", "entre", "desde", "hasta", "como", "donde", "cuando", "este", "esta", "these", "with", "from", "that"}
    return {t for t in tokens if t not in stop}


def _topic_is_health_related(topic: str) -> bool:
    t = (topic or "").lower()
    return any(k in t for k in _HEALTH_TERMS)


def _heuristic_source_score(doc: Document, topic_terms: set[str], enforce_health: bool) -> float:
    title = (doc.meta.get("title") or "").lower()
    content = (doc.content or "")[:1200].lower()
    text = f"{title} {content}"
    overlap = sum(1 for t in topic_terms if t in text)
    health_hits = sum(1 for k in _HEALTH_TERMS if k in text)
    offtopic_hits = sum(1 for k in _OFFTOPIC_TERMS if k in text)
    score = float(doc.score or 0.0) + (overlap * 0.25) + (health_hits * 0.08) - (offtopic_hits * 0.35)
    if enforce_health and health_hits == 0:
        score -= 1.0
    if _is_non_article_or_error_url(doc.meta.get("url", "")):
        score -= 1.0
    return score


def _select_docs_for_section(
    documents: list[Document],
    section_title: str,
    section_desc: str,
    focus: str,
    max_docs: int = 14,
) -> list[Document]:
    """Select the most relevant evidence subset for one section."""
    if len(documents) <= max_docs:
        return documents
    terms = _extract_topic_terms(f"{focus} {section_title} {section_desc}")
    enforce_health = _topic_is_health_related(focus)
    scored = [
        (doc, _heuristic_source_score(doc, terms, enforce_health))
        for doc in documents
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [d for d, s in scored if s > -0.25][:max_docs]
    return selected if selected else [d for d, _ in scored[:max_docs]]


def _filter_chat_documents_by_relevance(
    documents: list[Document],
    question: str,
    *,
    min_keep: int = 6,
    max_keep: int = 28,
) -> list[Document]:
    """
    Drop clearly off-topic documents before they reach chat synthesis and source UI.
    Uses heuristic score + source-type thresholds; keeps fallback top docs if overly strict.
    """
    if not documents:
        return documents
    topic_terms = _extract_topic_terms(question or "")
    enforce_health = _topic_is_health_related(question or "")
    scored: list[tuple[Document, float]] = []
    for d in documents:
        s = _heuristic_source_score(d, topic_terms, enforce_health)
        scored.append((d, s))
    scored.sort(key=lambda x: x[1], reverse=True)

    # Stricter for generic web pages; more permissive for curated/structured sources.
    per_type_min = {
        "web": 0.10,
        "webpage": 0.10,
        "rag": -0.20,
        "pdf": -0.20,
        "health_datastore": -0.20,
        "pubmed": -0.15,
        "openscholar": -0.15,
        "clinicaltrials": -0.20,
        "directorio_mx": -0.30,
        "allcan": -0.30,
    }

    kept: list[Document] = []
    seen: set[str] = set()
    per_type_count: dict[str, int] = {}
    per_type_cap = {
        "web": 6,
        "webpage": 6,
        "rag": 12,
        "pdf": 12,
        "health_datastore": 12,
        "pubmed": 8,
        "openscholar": 8,
        "clinicaltrials": 10,
        "directorio_mx": 10,
        "allcan": 10,
    }

    for d, s in scored:
        st = str((d.meta or {}).get("source_type", "unknown"))
        min_s = per_type_min.get(st, -0.10)
        if s < min_s:
            continue
        u = ((d.meta or {}).get("url") or "").strip()
        key = u or f"id:{getattr(d, 'id', '')}:{st}"
        if key in seen:
            continue
        c = per_type_count.get(st, 0)
        if c >= per_type_cap.get(st, 8):
            continue
        seen.add(key)
        per_type_count[st] = c + 1
        kept.append(d)
        if len(kept) >= max_keep:
            break

    if len(kept) >= min_keep:
        return kept
    # Safety fallback: avoid empty context on narrow queries.
    return [d for d, _ in scored[: min(max_keep, max(min_keep, 10))]]


def _likely_cold_gpu(settings) -> bool:
    """Heuristic: remote Ollama or Vast Serverless often implies cold GPU / long first token."""
    vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    if (getattr(settings, "vast_serverless_ollama_endpoint", "") or "").strip() and vk:
        return True
    u = (getattr(settings, "ollama_url", None) or "").strip()
    if not u:
        return False
    try:
        host = (urlparse(u).hostname or "").lower()
    except Exception:
        return True
    if not host:
        return True
    return host not in ("localhost", "127.0.0.1", "::1")


# --- SSE Helpers ---

def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _source_display_title(meta: dict) -> str:
    """Get a display title for a source; fallback to URL hostname when title is generic/empty.
    Strips OPENSCHOLAR prefix so the frontend never shows it in titles."""
    title = (meta.get("title") or "").strip()
    # Remove "OPENSCHOLAR — " or "OPENSCHOLAR - " prefix (case insensitive)
    if title.upper().startswith("OPENSCHOLAR"):
        rest = title[11:].lstrip()
        if rest.startswith("—") or rest.startswith("-"):
            title = rest[1:].strip()
        else:
            title = rest
    url = meta.get("url", "")
    if not title or title.lower() in ("url", "sin título", "sin titulo"):
        if url:
            try:
                return urlparse(url).netloc or url[:60]
            except Exception:
                return url[:60] if len(url) > 60 else url
        return "Sin título"
    return title


def _source_citation_label(meta: dict) -> str:
    """Build a citation-style display: 'Title - Authors - Year' (e.g. for article cards).
    Falls back to _source_display_title when we only have URL/title."""
    title = (meta.get("title") or "").strip()
    if title.upper().startswith("OPENSCHOLAR"):
        rest = title[11:].lstrip()
        if rest.startswith("—") or rest.startswith("-"):
            title = rest[1:].strip()
        else:
            title = rest
    authors = (meta.get("authors") or "").strip()
    year = str(meta.get("year") or "").strip()
    if not title or title.lower() in ("url", "sin título", "sin titulo"):
        return _source_display_title(meta)
    parts = [title]
    if authors:
        parts.append(authors)
    if year:
        parts.append(year)
    return " - ".join(parts)


def _clinical_trials_keywords_from_documents(documents: list[Document]) -> str:
    """English query.term keywords used for the CT.gov API (same for all trials in one fetch)."""
    for d in documents:
        meta = d.meta or {}
        if meta.get("source_type") == "clinicaltrials":
            kw = (meta.get("ct_search_keywords") or "").strip()
            if kw:
                return kw
    return ""


def _doc_to_source(doc: Document) -> dict:
    """Convert a Haystack Document to a source dict for the API response.
    Includes sourceType and meta.page_number for PDFs so the frontend can build #page=N links.
    Optional snippet (first 600 chars of content) for the preview modal.
    Title is citation-style (Title - Authors - Year) when metadata is available.
    """
    source_type = doc.meta.get("source_type", "rag")
    content = (doc.content or "").strip()
    snippet = content[:600] + ("…" if len(content) > 600 else "") if content else ""
    url = doc.meta.get("url", "")
    citation_label = _source_citation_label(doc.meta)
    out = {
        "title": citation_label,
        "url": url,
        "link": url,
        "attribution": citation_label,
        "score": round(doc.score or 0.0, 4) if doc.score else None,
        "type": source_type,
        "sourceType": source_type,
        "citation": doc.meta.get("citation", ""),
        "authors": doc.meta.get("authors", ""),
        "year": str(doc.meta.get("year", "")).strip() if doc.meta.get("year") else "",
        "journal": doc.meta.get("journal", ""),
        "doi": doc.meta.get("doi", ""),
        "snippet": snippet or None,
    }
    if source_type == "clinicaltrials":
        out["nctId"] = doc.meta.get("nct_id") or ""
        out["ctStartDate"] = doc.meta.get("ct_start_date") or ""
        out["ctLocationsSummary"] = doc.meta.get("ct_locations_summary") or ""
        fb = (doc.meta or {}).get("ct_fallback_search_url") or ""
        cl = (doc.meta or {}).get("ct_classic_show_url") or ""
        if fb:
            out["ctFallbackSearchUrl"] = fb
        if cl:
            out["ctClassicShowUrl"] = cl
    # Rich meta for deep links / UI: page, file name, short excerpt for PDF search anchors
    meta_out: dict = {}
    page_number = doc.meta.get("page_number")
    if page_number is not None:
        meta_out["page_number"] = int(page_number)
    if doc.meta.get("file_name"):
        meta_out["file_name"] = str(doc.meta["file_name"])
    # Stable chunk id when Haystack provides it (string/UUID — avoid casting to int in filters)
    did = getattr(doc, "id", None)
    if did:
        meta_out["chunk_id"] = str(did)
    excerpt = (content or "").replace("\n", " ").strip()
    if excerpt:
        meta_out["text_excerpt"] = excerpt[:240]
    if meta_out:
        out["meta"] = meta_out
    return out


def _deduplicate_and_rank(documents: list[Document], max_total: int = 10) -> list[Document]:
    """
    Deduplicate documents by URL, keeping the version with the MOST content.
    Then rank by relevance with a balanced mix of source types.
    """
    # For chunked corpora (RAG/PDF/health_datastore), several relevant chunks can share
    # the same URL (different pages). Deduping only by URL drops evidence.
    chunked_types = {"rag", "pdf", "health_datastore"}
    best_by_key: dict[str, Document] = {}

    def _doc_key(doc: Document) -> str:
        meta = doc.meta or {}
        url = (meta.get("url") or "").strip()
        if not url or not doc.content:
            return ""
        normalized = urlparse(url)._replace(fragment="").geturl().rstrip("/")
        source_type = str(meta.get("source_type", "rag") or "rag")
        if source_type in chunked_types:
            page = meta.get("page_number")
            chunk_id = meta.get("chunk_id") or getattr(doc, "id", None)
            if page is not None:
                return f"{normalized}#p:{page}"
            if chunk_id:
                return f"{normalized}#c:{chunk_id}"
            # Fallback: preserve more than one chunk from same URL by content prefix.
            prefix = re.sub(r"\s+", " ", (doc.content or "")[:180]).strip().lower()
            return f"{normalized}#t:{prefix}"
        return normalized

    for doc in documents:
        key = _doc_key(doc)
        if not key:
            continue
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = doc
        else:
            # Keep richer variant for same semantic key
            if len(doc.content or "") > len(existing.content or ""):
                best_by_key[key] = doc

    unique = list(best_by_key.values())

    def sort_key(d: Document) -> tuple:
        source_type = d.meta.get("source_type", "rag")
        score = d.score or 0
        # 1 Ominis, 2 OpenScholar, 3 PubMed, 4 Web
        type_priority = {
            "rag": 0,
            "pdf": 0,
            "health_datastore": 0,
            "clinicaltrials": 1,
            "directorio_mx": 1,
            "allcan": 1,
            "openscholar": 2,
            "pubmed": 3,
            "web": 4,
            "webpage": 4,
        }.get(source_type, 4)
        return (type_priority, -score)

    unique.sort(key=sort_key)
    return unique[:max_total]


def _merge_sources_for_chat(
    documents: list[Document],
    max_total: int,
    prioritize_clinical_trials: bool,
) -> list[Document]:
    """
    When ClinicalTrials.gov is enabled, keep trial registry docs in the context window:
    they used to share default priority with web and were often trimmed out.
    """
    if not prioritize_clinical_trials:
        return _deduplicate_and_rank(documents, max_total=max_total)

    def norm_url(d: Document) -> str:
        u = (d.meta or {}).get("url", "")
        if not u:
            return ""
        return urlparse(u)._replace(fragment="").geturl().rstrip("/")

    ct = [d for d in documents if (d.meta or {}).get("source_type") == "clinicaltrials"]
    rest = [d for d in documents if (d.meta or {}).get("source_type") != "clinicaltrials"]
    cap_ct = min(14, max_total)
    ct_ranked = _deduplicate_and_rank(ct, max_total=cap_ct)
    rest_ranked = _deduplicate_and_rank(rest, max_total=max_total)

    out: list[Document] = []
    seen: set[str] = set()
    for d in ct_ranked:
        u = norm_url(d)
        if u and u not in seen:
            seen.add(u)
            out.append(d)
    for d in rest_ranked:
        if len(out) >= max_total:
            break
        u = norm_url(d)
        if u and u not in seen:
            seen.add(u)
            out.append(d)
    return out[:max_total]


def _split_sources_by_citation(
    answer: str,
    all_sources: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Split retrieved sources into (cited, uncited) using [N] markers in the answer.
    When the answer has no [N] citations, returns (all_sources with ref_num, []) so the
    UI still shows a single list (undistinguishable case).
    """
    cited_nums: set[int] = set()
    for match in re.finditer(r"\[(\d+)\]", answer):
        cited_nums.add(int(match.group(1)))

    def _with_ref(i: int, src: dict) -> dict:
        out = dict(src)
        out["ref_num"] = i + 1
        return out

    if not all_sources:
        return [], []

    if not cited_nums:
        return [_with_ref(i, s) for i, s in enumerate(all_sources)], []

    cited: list[dict] = []
    uncited: list[dict] = []
    for i, source in enumerate(all_sources):
        ref_num = i + 1
        s = _with_ref(i, source)
        if ref_num in cited_nums:
            cited.append(s)
        else:
            uncited.append(s)
    return cited, uncited


def _filter_cited_sources(
    answer: str,
    all_sources: list[dict],
) -> list[dict]:
    """Sources actually cited in the answer ([N] markers). Delegates to _split_sources_by_citation."""
    cited, _ = _split_sources_by_citation(answer, all_sources)
    return cited


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
        "clinicaltrials.gov",
        "sciencedirect.com",
        "nature.com",
        "thelancet.com",
        "bmj.com",
    )
    return any(d in domain for d in trusted)


def _truncate_step(text: str, max_len: int, suffix: str = "...") -> str:
    """Truncate for research step display; always append suffix when cutting."""
    if not text:
        return ""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)].rstrip() + suffix


def _source_priority(doc: Document) -> tuple:
    """Order: Ominis (rag) > OpenScholar > PubMed > Web. Lower type_priority = higher importance."""
    source_type = doc.meta.get("source_type", "rag")
    url = doc.meta.get("url", "")
    score = doc.score or 0
    trusted = 0 if _is_trustworthy_domain(url) else 1
    # 1 Ominis, 2 OpenScholar, 3 PubMed, 4 Web
    type_priority = {
        "rag": 0,
        "pdf": 0,
        "health_datastore": 0,
        "clinicaltrials": 1,
        "directorio_mx": 1,
        "allcan": 1,
        "openscholar": 2,
        "pubmed": 3,
        "web": 4,
        "webpage": 4,
    }.get(source_type, 4)
    return (trusted, type_priority, -score)


def _is_non_article_or_error_url(url: str) -> bool:
    """True if URL is clearly not an article (404 page, CDN, NCBI homepage, etc.)."""
    if not url:
        return True
    url_lower = url.lower()
    # CDN, generic NCBI home, or non-article paths
    if "cdn.ncbi" in url_lower or "cdn." in url_lower:
        return True
    if "ncbi.nlm.nih.gov" in url_lower or "ncbi.nlm.nih.gov" in url_lower:
        # Keep pubmed.ncbi.nlm.nih.gov/12345 style; drop bare domain or non-article
        path = url.split(".nih.gov", 1)[-1] if ".nih.gov" in url_lower else ""
        if not path or path.strip("/") in ("", " ", "/"):
            return True
        if "/pubmed/" not in url_lower and "/pmc/" not in url_lower and path.count("/") < 2:
            return True
    return False


def _doc_is_error_or_non_article(doc: Document, failed_urls: set[str]) -> bool:
    """True if document should be excluded (failed fetch, 404, homepage, etc.)."""
    url = (doc.meta or {}).get("url", "")
    if url in failed_urls:
        return True
    if _is_non_article_or_error_url(url):
        return True
    title = ((doc.meta or {}).get("title") or "").lower()
    content_snippet = (doc.content or "")[:500].lower()
    # Exclude error pages or generic pages
    if "404" in title or "page not found" in title or "error" in title and "ncbi" in title:
        return True
    if "404" in content_snippet[:200] and "page not found" in content_snippet[:300]:
        return True
    if title == "national center for biotechnology information" or "welcome to ncbi" in content_snippet[:400]:
        return True
    return False


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


def _is_captcha_or_error_page(text: str, url: str = "") -> bool:
    """True if the fetched page is a captcha, JS gate, or error page (e.g. Semantic Scholar)."""
    if not (text or "").strip():
        return True
    t = (text or "").lower()[:2000]
    if "javascript is disabled" in t or "not a robot" in t or "captcha" in t or "enable javascript" in t:
        return True
    if "semanticscholar.org" in (url or "").lower() and ("verify" in t or "robot" in t):
        return True
    return False


def _looks_like_pdf_url(url: str) -> bool:
    u = (url or "").lower()
    return ".pdf" in u or "/pdf/" in u


def _question_needs_structured_evidence(question: str) -> bool:
    q = (question or "").lower()
    return bool(re.search(r"\b(presupuesto|ppef|pef|mdp|millones|monto|montos|cifra|cifras|tabla|cuadro|anexo|recorte)\b", q))


async def _fetch_pdf_text(url: str, timeout: float = 20.0) -> tuple[str, str]:
    """
    Fetch PDF bytes and extract text. Returns (title, text).
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
            if "application/pdf" not in content_type and not _looks_like_pdf_url(url):
                return "", ""
            pdf_bytes = resp.content
    except Exception as e:
        logger.warning("PDF fetch failed for %s: %s", url, e)
        return "", ""

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: list[str] = []
        for i, page in enumerate(reader.pages[:40]):  # hard cap for latency
            t = (page.extract_text() or "").strip()
            if t:
                pages.append(f"[Página {i+1}]\n{t}")
        text = "\n\n".join(pages).strip()
        title = ""
        if reader.metadata:
            title = str(getattr(reader.metadata, "title", "") or "").strip()
        return title, text[:30000]
    except Exception as e:
        logger.warning("PDF parse failed for %s: %s", url, e)
        return "", ""


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
            if "application/pdf" in content_type or _looks_like_pdf_url(url):
                title, text = await _fetch_pdf_text(url, timeout=timeout)
                return title, text, []
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
    if _is_captcha_or_error_page(text, url):
        return "", "", []
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
        _current_datetime_context()
        + "\n\n"
        + "Eres un planificador de investigación en salud para México. "
        "Aplica a CUALQUIER tema clínico, médico o de investigación en salud. "
        "Evalúa si la pregunta es viable para investigar. Devuelve SOLO JSON válido sin texto extra."
    )
    user = (
        "Evalúa la siguiente pregunta y genera un plan de investigación. "
        "Si la pregunta no tiene sentido, es gibberish, o no es investigable, "
        "pon viable=false.\n"
        "REGLA CRÍTICA: Si el usuario proporcionó ESPECIFICACIONES Y ACLARACIONES, "
        "úsalas para ACOTAR el tema y el enfoque, pero DISTINGUE:\n"
        "(1) PARÁMETROS DEL REPORTE (no son términos de búsqueda): alcance geográfico (ej. solo México), "
        "periodo temporal (ej. últimos 6 meses), público meta (ej. profesionales e investigadores en salud). "
        "El público meta indica PARA QUIÉN se escribe el reporte; NUNCA generes consultas de búsqueda sobre "
        "\"profesionales de la salud\", \"investigadores en salud\" ni similares.\n"
        "(2) TEMA Y SUBTEMAS A INVESTIGAR: el tema central y los subtemas que el usuario pide incluir "
        "(ej. Receta Digital, Telemedicina, IA) SÍ deben convertirse en consultas de búsqueda.\n"
        "Las queries deben ser SOLO sobre el tema sustantivo y subtemas solicitados; puedes incluir "
        "geografía o fechas DENTRO de la misma consulta (ej. \"reforma LGS salud digital México\"), "
        "pero NUNCA consultas cuyo objetivo sea el público meta.\n"
        "\n"
        "Formato JSON:\n"
        "{"
        "\"viable\": true/false, "
        "\"reason\": \"razón si no es viable\", "
        "\"focus\": \"enfoque específico de la investigación\", "
        "\"queries\": [\"consulta1\", \"query2\", \"consulta3\", \"query4\", \"consulta5\", \"query6\", \"query7\", \"query8\"], "
        "\"sections\": [\"Resumen ejecutivo\", \"Contexto epidemiológico\", \"Mecanismos y fisiopatología\", \"Diagnóstico y clasificación\", \"Hallazgos principales\", \"Análisis detallado\", \"Tratamientos y comparativos\", \"Guías clínicas\", \"Perspectivas para México\", \"Discusión\", \"Limitaciones\", \"Conclusiones\"]"
        "}\n"
        "REGLAS PARA QUERIES:\n"
        "- Genera 6-8 consultas MUY ESPECÍFICAS al tema sustantivo (y subtemas pedidos).\n"
        "- NUNCA generes consultas que busquen \"público meta\", \"para quién\" o perfiles de audiencia (ej. profesionales, investigadores).\n"
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
        "queries": queries[:10],
        "sections": sections[:18],
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
        "Aplica a cualquier tema clínico, médico o de investigación en salud. "
        "Tu tarea es analizar la pregunta del usuario Y el historial de conversación completo "
        "para generar las mejores consultas de búsqueda posibles. "
        "Devuelve SOLO un JSON válido sin texto extra.\n\n"
        "REGLAS:\n"
        "- Genera 2-4 consultas optimizadas para buscar en PubMed, web y bases de datos.\n"
        "- Analiza TODO el historial para entender el contexto completo, no solo el último mensaje.\n"
        "- NUNCA generes consultas sobre el público meta o \"para quién\" es el reporte (ej. profesionales de la salud, investigadores). Esos son parámetros del reporte, no temas de búsqueda.\n"
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


async def _get_deepening_queries(
    focus: str,
    research_notes: list[str],
    generator,
    backend_openai_model: str,
) -> list[str]:
    """Research 2.1: generate 3-5 queries to deepen on the most relevant findings."""
    if not research_notes or len(research_notes) < 2:
        return []
    sys_prompt, user_prompt = get_deepening_queries_prompt(focus, research_notes)
    messages = [
        ChatMessage.from_system(sys_prompt),
        ChatMessage.from_user(user_prompt),
    ]
    try:
        loop = asyncio.get_event_loop()
        gk = openai_chat_completion_generation_kwargs(
            backend_openai_model, temperature=0.3, num_predict=1024
        )
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: generator.run(messages=messages, generation_kwargs=gk)),
            timeout=60.0,
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        obj = _extract_json_object(text) or {}
        queries = obj.get("queries", [])
        if isinstance(queries, list) and queries:
            return [str(q) for q in queries[:5]]
    except Exception as e:
        logger.warning("Deepening queries generation failed: %s", e)
    return []


async def _score_source_relevance(
    topic: str,
    user_spec: str,
    documents: list[Document],
    generator,
    min_keep: int = 8,
    max_keep: int = 16,
) -> tuple[list[Document], str]:
    """
    Use LLM to score and filter documents for relevance to the research topic.
    Returns (filtered documents in relevance order, reason string for chain-of-thought).
    """
    if not documents or len(documents) <= 5:
        return documents, ""

    max_keep = max(min_keep, max_keep)
    target_keep = min(max_keep, len(documents))
    enforce_health = _topic_is_health_related(f"{topic} {user_spec}")
    topic_terms = _extract_topic_terms(f"{topic} {user_spec}")

    source_list = ""
    for i, doc in enumerate(documents):
        title = doc.meta.get("title", "Sin título")[:60]
        url = doc.meta.get("url", "")
        content_preview = (doc.content or "")[:180].replace("\n", " ")
        source_list += f"[{i}] {title} — {content_preview} — URL: {url}\n"

    system = (
        "Eres un evaluador de relevancia de fuentes para investigación médica/científica. "
        "Piensa paso a paso: (1) ¿Qué pregunta concreta responde esta investigación? "
        "(2) Para cada fuente, ¿aporta evidencia directa (estudios, datos, guías) o solo mención marginal? "
        "(3) Ordena por relevancia: las que aportan más al tema primero. "
        "Aplica a cualquier tema clínico o de investigación en salud. "
        "Devuelve SOLO un objeto JSON válido."
    )
    user = (
        f"TEMA DE INVESTIGACIÓN: {topic}\n"
        f"ESPECIFICACIONES DEL USUARIO: {user_spec}\n\n"
        f"FUENTES ENCONTRADAS:\n{source_list}\n"
        "Reglas: Incluye SOLO fuentes que aporten datos, métodos o hallazgos DIRECTOS sobre el tema. "
        "EXCLUYE: menciones marginales, temas distintos, páginas de error o genéricas. "
        f"Selecciona entre {min_keep} y {target_keep} fuentes (si hay suficientes relevantes). "
        "Ordena por relevancia (más específicas primero).\n"
        'Formato JSON: {"relevant": [índices en orden de relevancia], "reason": "1-2 líneas explicando por qué elegiste estas fuentes y en qué orden (cadena de razonamiento)."}'
    )

    # Heuristic ranking fallback / backfill to avoid tiny or noisy sets.
    scored = [
        (doc, _heuristic_source_score(doc, topic_terms, enforce_health))
        for doc in documents
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    heuristic_ranked = [d for d, s in scored if s > -0.25]
    if not heuristic_ranked:
        heuristic_ranked = [d for d, _ in scored]

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
        reason = (obj.get("reason") or "").strip() if isinstance(obj.get("reason"), str) else ""
        if isinstance(relevant_indices, list):
            seen: set[int] = set()
            filtered = []
            for i in relevant_indices:
                if isinstance(i, int) and 0 <= i < len(documents) and i not in seen:
                    seen.add(i)
                    filtered.append(documents[i])
            if filtered:
                # Cap upper bound, and ensure minimum with heuristic backfill.
                filtered = filtered[:target_keep]
                if len(filtered) < min_keep:
                    for d in heuristic_ranked:
                        if d not in filtered:
                            filtered.append(d)
                        if len(filtered) >= min(min_keep, len(documents)):
                            break
                logger.info("Relevance filter: %s → %s sources", len(documents), len(filtered))
                return filtered, reason
    except Exception as e:
        logger.warning(f"Relevance scoring failed: {e}")

    fallback = heuristic_ranked[:target_keep]
    if len(fallback) < min_keep:
        fallback = (heuristic_ranked + documents)[: min(min_keep, len(documents))]
    return fallback, ""


async def _gather_sources(
    question: str,
    rag_search: bool,
    web_search: bool,
    pubmed_search: bool,
    openscholar_search: bool,
    num_sources: int,
    manager,
    refined_queries: list[str] | None = None,
    intent: dict | None = None,
    clinical_trials_search: bool = False,
    ct_model_id: str | None = None,
    clinical_trials_allowed: bool = False,
    doctor_directory_search: bool = False,
    allcan_search: bool = False,
    doctor_directory_allowed: bool = False,
    allcan_allowed: bool = False,
    db: AsyncSession | None = None,
) -> list[Document]:
    """
    Gather documents from all enabled search sources in parallel.
    RAG retrieval is filtered by orchestrator intent: we request more candidates when
    intent has retrieval_constraints/depth so that after in-memory taxonomy filter we keep enough.
    """
    tasks = []

    # RAG retrieval: request enough candidates so specific DataStore docs (e.g. ASQ Modoris) can appear
    top_k_mult = get_rag_top_k_multiplier(intent)
    rag_top_k = max(num_sources * top_k_mult, 24)

    logger.info("RAG search enabled: %s. Query: %s", rag_search, question[:80])

    if rag_search:
        async def do_rag(q: str = question):
            try:
                text_embedder = manager.get_text_embedder()
                retriever = manager.get_retriever()
                embed_result = text_embedder.run(text=q)
                query_embedding = embed_result["embedding"]
                result = retriever.run(
                    query_embedding=query_embedding,
                    top_k=rag_top_k,
                )
                docs = result.get("documents", [])
                logger.info("RAG: retriever.run returned %s docs (raw). Query: %s", len(docs), q[:80])
                if docs:
                    top_scores = [d.score for d in docs[:5]]
                    logger.info("RAG: Top 5 scores (raw): %s", top_scores)

                valid = []
                for d in docs:
                    score = d.score or 0
                    # Lower threshold 0.5 -> 0.35 so relevant DataStore docs (e.g. ASQ Modoris) are not dropped
                    if d.content and d.meta.get("url") and score >= 0.35:
                        d.meta["source_type"] = d.meta.get("source_type", "rag")
                        valid.append(d)
                valid.sort(key=lambda d: d.score or 0, reverse=True)
                out = valid[: num_sources * 2]
                if docs and not out:
                    logger.warning(
                        "RAG: all %s docs filtered (score < 0.35 or missing url). Top score: %s. Query: %s",
                        len(docs), (docs[0].score if docs else None), q[:80],
                    )
                return out
            except Exception as e:
                logger.error(f"RAG retrieval error: {e}", exc_info=True)
                return []

        tasks.append(do_rag())

        # Keyword search: find docs by exact terms (acronyms, proper nouns) that vector search misses
        async def do_rag_keyword():
            try:
                from app.rag.document_store import _build_pgvector_conn_str
                import psycopg2
                conn_str = _build_pgvector_conn_str()
                conn = psycopg2.connect(conn_str)
                cur = conn.cursor()
                stop_words = {"qué", "que", "cómo", "como", "cuál", "cual", "por", "para", "con", "sin", "los", "las", "del", "una", "uno", "este", "esta", "ese", "esa", "son", "está", "hay", "más", "muy", "todo", "sobre", "entre"}
                words = [w.strip("¿?¡!.,;:()\"'") for w in question.split() if len(w.strip("¿?¡!.,;:()\"'")) >= 3 and w.strip("¿?¡!.,;:()\"'").lower() not in stop_words]
                if not words:
                    conn.close()
                    return []
                # Strategy: find source_ids from rag_sources by title/URL match, then fetch their chunks
                src_conditions = []
                src_params = []
                for w in words[:4]:
                    src_conditions.append("(title ILIKE %s OR source_url ILIKE %s)")
                    src_params.extend([f"%{w}%", f"%{w}%"])
                cur.execute(
                    f"SELECT id FROM rag_sources WHERE ({' OR '.join(src_conditions)}) AND status = 'active' LIMIT 10",
                    src_params,
                )
                source_ids = [r[0] for r in cur.fetchall()]
                if not source_ids:
                    conn.close()
                    logger.info("RAG keyword: no rag_sources match words %s", words[:4])
                    return []
                # Fetch chunks for these sources (fast: indexed by meta->source_id)
                placeholders = ",".join(["%s"] * len(source_ids))
                cur.execute(
                    f'SELECT id, content, meta FROM "public"."haystack_documents" WHERE (meta->>%s) IN ({placeholders}) LIMIT %s',
                    ["source_id"] + [str(s) for s in source_ids] + [rag_top_k],
                )
                rows = cur.fetchall()
                conn.close()
                logger.info("RAG keyword: %s chunks from %s sources for words %s", len(rows), len(source_ids), words[:4])
                from haystack import Document as HDoc
                import json as _json
                kw_docs = []
                for row in rows:
                    doc_id, content, meta_raw = row
                    meta = meta_raw if isinstance(meta_raw, dict) else (_json.loads(meta_raw) if isinstance(meta_raw, str) else {})
                    if content and meta.get("url"):
                        meta["source_type"] = meta.get("source_type", "rag")
                        kw_docs.append(HDoc(id=doc_id, content=content, meta=meta, score=0.8))
                return kw_docs[:num_sources * 2]
            except Exception as e:
                logger.warning("RAG keyword search error: %s", e)
                return []

        tasks.append(do_rag_keyword())

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

    # Open Scholar (Semantic Scholar) — academic paper search
    if openscholar_search:
        async def do_openscholar():
            try:
                return await search_openscholar(question, max_results=num_sources)
            except Exception as e:
                logger.error(f"Open Scholar search error: {e}", exc_info=True)
                return []
        tasks.append(do_openscholar())

    # Health datastore (nightly Mexican health: FAISS + OpenSearch)
    if get_settings().health_datastore_enabled:
        async def do_health_datastore():
            try:
                pack = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: build_evidence_pack(question, top_k=num_sources)
                )
                from haystack import Document
                docs = []
                for i, item in enumerate(pack):
                    meta = item.get("metadata", {})
                    docs.append(Document(
                        content=item.get("chunk_text", ""),
                        meta={
                            "title": meta.get("title", ""),
                            "url": meta.get("source_url", ""),
                            "source_type": "health_datastore",
                            "citation": item.get("citation", ""),
                            "year": meta.get("year"),
                            "institution": meta.get("institution", ""),
                        },
                    ))
                return docs
            except Exception as e:
                logger.warning("Health datastore search error: %s", e)
                return []
        tasks.append(do_health_datastore())

    # Also search with refined queries if provided (more phrasings -> better chance to hit DataStore docs like ASQ Modoris)
    if refined_queries:
        for rq in refined_queries:
            if rag_search:
                async def do_rag_refined(q=rq):
                    return await do_rag(q)
                tasks.append(do_rag_refined())
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
            if openscholar_search:
                async def do_openscholar_refined(q=rq):
                    try:
                        return await search_openscholar(q, max_results=num_sources)
                    except Exception:
                        return []
                tasks.append(do_openscholar_refined())

    if clinical_trials_search and clinical_trials_allowed and ct_model_id:
        async def do_clinical_trials():
            try:
                from app.rag.clinical_trials_search import fetch_clinical_trials_documents

                size = min(24, max(num_sources * 2, 16))
                docs, _kw = await fetch_clinical_trials_documents(
                    question, manager, ct_model_id, max_results=size
                )
                return docs
            except Exception as e:
                logger.warning("Clinical trials search error: %s", e)
                return []

        tasks.append(do_clinical_trials())

    if doctor_directory_search and doctor_directory_allowed and db is not None:
        async def do_doctor_directory():
            try:
                from app.rag.directory_tools_search import fetch_doctor_directory_documents

                size = min(24, max(num_sources * 2, 12))
                return await fetch_doctor_directory_documents(db, question, max_results=size)
            except Exception as e:
                logger.warning("Doctor directory search error: %s", e)
                return []

        tasks.append(do_doctor_directory())

    if allcan_search and allcan_allowed:
        async def do_allcan():
            try:
                from app.rag.directory_tools_search import fetch_allcan_documents

                size = min(32, max(num_sources * 2, 16))
                return await fetch_allcan_documents(question, max_results=size)
            except Exception as e:
                logger.warning("All.Can search error: %s", e)
                return []

        tasks.append(do_allcan())

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

    # Targeted enrichment: web PDF snippets often lack table/figure values (e.g., budget PDFs).
    # For structured-evidence questions, fetch and parse top PDF URLs before synthesis.
    if web_search and combined and _question_needs_structured_evidence(question):
        pdf_candidates: list[Document] = []
        for d in combined:
            meta = d.meta or {}
            st = str(meta.get("source_type", ""))
            url = str(meta.get("url", "") or "")
            if st in {"web", "webpage"} and url and _looks_like_pdf_url(url):
                pdf_candidates.append(d)
        if pdf_candidates:
            pdf_candidates = pdf_candidates[: min(6, max(3, num_sources))]
            enrich_tasks = [_fetch_pdf_text((d.meta or {}).get("url", ""), timeout=25.0) for d in pdf_candidates]
            enriched = await asyncio.gather(*enrich_tasks, return_exceptions=True)
            for d, payload in zip(pdf_candidates, enriched):
                if isinstance(payload, Exception):
                    continue
                title, text = payload
                if text and len(text) > 300:
                    if title:
                        d.meta["title"] = title
                    d.meta["source_type"] = "pdf"
                    d.content = text
            logger.info("Web PDF enrichment: %s candidates processed", len(pdf_candidates))

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

# Guest (unauthenticated) can only use this model
GUEST_ONLY_MODEL_ID = "ominis-2.0"

# OpenScholar 128K (research mode; when OPENSCHOLAR_128K_API_URL is set, e.g. Vast.ai)
ACADEMIC_MODEL_ID_128K = "ominis-2.0-research-128k"


def _backend_openai_model_for_research_stream(public_model_id: str) -> str:
    """
    Backend OpenAI model id for the active research generator (maps public UI id + registry).
    Used to build per-request generation_kwargs (max_tokens vs max_completion_tokens, temperature rules).
    """
    reg = get_model_registry()
    if public_model_id == ACADEMIC_MODEL_ID_128K and "research-128k" in reg:
        return (get_model_config("research-128k").openai_model or "").strip()
    if "research-8k" in reg:
        c8 = get_model_config("research-8k")
        b = (c8.openai_api_base or "").strip()
        if b and "placeholder.invalid" not in b:
            return (c8.openai_model or "").strip()
    for _mid, cfg in reg.items():
        if getattr(cfg, "public_id", "") == public_model_id and getattr(cfg, "use_openai", False):
            return (cfg.openai_model or "").strip()
    return (getattr(get_settings(), "openscholar_model", None) or "openscholar").strip()


def _openai_non_chat_model_user_message(api_error_text: str) -> str | None:
    """
    OpenAI returns this when the configured model id is not allowed on POST /v1/chat/completions
    (e.g. legacy completions-only models, embeddings, or a mismatched proxy deployment).
    """
    low = (api_error_text or "").lower()
    if "not a chat model" in low or "not supported in the v1/chat/completions" in low:
        return (
            "Error al generar el reporte. El **modelo backend** de investigación no es un modelo de **chat** para esa API "
            "(no admite `/v1/chat/completions`). En el panel **LLMs**, edita **research-128k** o **research-8k**: "
            "usa un id de modelo de chat de OpenAI, p. ej. `gpt-5.4`, `gpt-4o` o `gpt-4o-mini` (confírmalo con «Listar modelos»). "
            "Evita modelos solo de completions (`text-…`), embeddings o audio. "
            f"Detalle: {api_error_text}"
        )
    return None


def _research_128k_available() -> bool:
    import os

    s = get_settings()
    if (getattr(s, "openscholar_128k_api_url", "") or "").strip():
        return True
    if (getattr(s, "vast_serverless_openscholar_128k_endpoint", "") or "").strip():
        return bool((getattr(s, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip())
    return False


def _get_research_generator_and_model_id():
    """
    Prefer dashboard-configured research-8k (OpenAI, Anthropic, vLLM, etc.), then legacy 128K URL, else default chat.
    """
    manager = get_pipeline_manager()
    reg = get_model_registry()
    if "research-8k" in reg:
        cfg8 = get_model_config("research-8k")
        base = (cfg8.openai_api_base or "").strip()
        if base and "placeholder.invalid" not in base:
            try:
                gen = manager.get_generator("research-8k")
                return gen, cfg8.public_id, ""
            except Exception as e:
                logger.warning("research-8k generator unavailable (%s); trying 128K fallback", e)
    if _research_128k_available():
        try:
            return get_openscholar_128k_generator(), ACADEMIC_MODEL_ID_128K, ""
        except ValueError:
            pass
    return manager.get_generator(), manager.get_public_model_id(DEFAULT_MODEL_ID), "Ominis 2.0 Research 128K no configurado. Usando Ominis 2.0."


def _research_context_token_budget(public_model_id: str) -> int:
    """Use dashboard context_window for research slots (large models / long reports)."""
    mid = "research-128k" if public_model_id == ACADEMIC_MODEL_ID_128K else "research-8k"
    reg = get_model_registry()
    if mid not in reg:
        return MODEL_CTX_LIMIT_128K if public_model_id == ACADEMIC_MODEL_ID_128K else MODEL_CTX_LIMIT
    cfg = get_model_config(mid)
    try:
        cw = int(getattr(cfg, "context_window", MODEL_CTX_LIMIT) or MODEL_CTX_LIMIT)
    except (TypeError, ValueError):
        cw = MODEL_CTX_LIMIT
    cap = MODEL_CTX_LIMIT_128K if public_model_id == ACADEMIC_MODEL_ID_128K else 200_000
    return max(MODEL_CTX_LIMIT, min(cw, cap))


async def _researcher_allowed_chat_model_ids(db: AsyncSession) -> set[str]:
    """Model IDs that SuperAdmin has marked as available for researchers (default True if not set)."""
    registry = get_model_registry()
    result = await db.execute(select(LLMModelConfig).where(LLMModelConfig.model_id.in_(registry.keys())))
    rows = {r.model_id: r for r in result.scalars().all()}
    allowed = set()
    for model_id in registry.keys():
        row = rows.get(model_id)
        if getattr(row, "available_for_researcher", None) is False:
            continue
        allowed.add(model_id)
    return allowed


def _model_access(user: User | None, model_id: str, researcher_allowed: set[str]) -> tuple[bool, str | None]:
    """
    Returns (allowed, reason_code).
    reason_code: None if allowed; else "login_required" | "researcher_only" | "request_superadmin".
    """
    if user is None:
        if model_id == GUEST_ONLY_MODEL_ID:
            return True, None
        return False, "login_required"
    if user.role in (RoleEnum.admin, RoleEnum.superadmin):
        return True, None
    if model_id == ACADEMIC_MODEL_ID_128K and _research_128k_available():
        return True, None
    if model_id in researcher_allowed:
        return True, None
    return False, "request_superadmin"


@router.get("/health-datastore/status")
async def health_datastore_status():
    """Return health datastore status: enabled, doc/chunk counts, and a quick retrieval test. No auth required for ops check."""
    from app.rag.health_datastore import build_evidence_pack
    settings = get_settings()
    result = {
        "enabled": settings.health_datastore_enabled,
        "health_docs": 0,
        "health_chunks": 0,
        "evidence_pack_test_count": 0,
        "opensearch_url_set": bool((settings.opensearch_url or "").strip()),
    }
    if not settings.health_datastore_enabled:
        return result
    try:
        import psycopg2
        import re
        url = getattr(settings, "database_url_sync", "") or (settings.database_url or "")
        url = re.sub(r"postgresql\+\w+://", "postgresql://", url)
        if url:
            conn = psycopg2.connect(url)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM health_docs")
            result["health_docs"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM health_chunks")
            result["health_chunks"] = cur.fetchone()[0]
            cur.close()
            conn.close()
        pack = await asyncio.get_event_loop().run_in_executor(
            None, lambda: build_evidence_pack("salud México diabetes", top_k=5)
        )
        result["evidence_pack_test_count"] = len(pack)
    except Exception as e:
        result["error"] = str(e)
    return result


@router.get("/health-datastore/recent-activity")
async def health_datastore_recent_activity(limit: int = 20):
    """Return last N ingested health docs (source_url, title, source_type, date_ingested) for dashboard."""
    settings = get_settings()
    if not settings.health_datastore_enabled:
        return {"items": [], "note": "Health datastore disabled"}
    limit = min(max(1, limit), 100)
    try:
        import psycopg2
        import re
        url = getattr(settings, "database_url_sync", "") or (settings.database_url or "")
        url = re.sub(r"postgresql\+\w+://", "postgresql://", url)
        if not url:
            return {"items": []}
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """SELECT title, source_url, source_type, date_ingested
               FROM health_docs
               ORDER BY date_ingested DESC
               LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        items = [
            {
                "title": r[0] or "",
                "source_url": r[1] or "",
                "source_type": r[2] or "",
                "date_ingested": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]
        return {"items": items}
    except Exception as e:
        return {"items": [], "error": str(e)}

@router.get("/models")
async def list_models(
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """List available Ominis models (chat + research 128K). With optional auth, each model includes allowed and reason."""
    manager = get_pipeline_manager()
    chat_models = list(manager.available_models)
    if _research_128k_available():
        chat_models.append({
            "id": ACADEMIC_MODEL_ID_128K,
            "displayName": "Ominis 2.0 Research 128K",
            "description": "Investigación profunda, contexto largo 128K (modelo configurable en dashboard)",
            "isDefault": False,
        })
    researcher_allowed = await _researcher_allowed_chat_model_ids(db) if user is not None else set()
    result_models = []
    for m in chat_models:
        mid = m["id"]
        allowed, reason = _model_access(user, mid, researcher_allowed)
        result_models.append({**m, "allowed": allowed, **({"reason": reason} if reason else {})})

    # Default model: from chat_defaults if set and present in list, else DEFAULT_MODEL_ID
    default_id = DEFAULT_MODEL_ID
    try:
        row = (await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))).scalar_one_or_none()
        if row and getattr(row, "default_model", None):
            candidate = normalize_public_model_id((row.default_model or "").strip()) or ""
            if candidate and any(x["id"] == candidate for x in result_models):
                default_id = candidate
    except Exception:
        pass
    return {"models": result_models, "default": default_id}


# --- Streaming endpoint ---

@router.post("/query-stream")
async def query_stream(
    body: QueryRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Streaming query endpoint using Haystack OllamaChatGenerator.
    Supports RAG, web search, PubMed, and vision (multimodal).
    Model access: guests only ominis-2.0; researchers see SuperAdmin-allowed models; others get 403 with reason.
    """
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    researcher_allowed = await _researcher_allowed_chat_model_ids(db) if db else set()
    default_public_id = manager.get_public_model_id(DEFAULT_MODEL_ID)
    # Dashboard toggle: when public access is disabled, block anonymous visitors.
    public_access_enabled = True
    try:
        result = await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))
        row = result.scalar_one_or_none()
        public_access_enabled = bool(getattr(row, "public_access_enabled", True))
    except Exception as e:
        logger.warning("Could not read chat_defaults.public_access_enabled; defaulting to enabled: %s", e)

    async def main_stream():
        if not public_access_enabled and user is None:
            yield sse_event({"type": "error", "message": "registration_required"})
            return
        # Send first byte immediately so frontend does not stay on "Pensando"
        yield sse_event({
            "type": "status",
            "message": "Conectando...",
            "model": default_public_id,
        })
        # Orchestrator: intent and route (run intent whenever we have a question so we can auto-enable web for recency)
        has_image = bool(body.image and len(body.image) > 50)
        has_file = bool((body.file_context or "").strip())
        intent = None
        q_text = (body.question or "").strip()
        if q_text:
            if heuristic_conversation_only(body.question) and not has_image and not has_file:
                intent = conversation_only_default_intent()
                logger.info("Intent mapper skipped (heuristic conversation-only)")
            elif (
                not has_image
                and not has_file
                and not body.research_mode
                and len(q_text) <= 180
            ):
                # Fast path: for normal short chat turns, rely on deterministic heuristics
                # to avoid slow first-token latency when DEFAULT_MODEL_ID is GPT-5.x.
                heur_ts = infer_tool_sources_heuristic(body.question, None)
                if any(heur_ts.values()):
                    intent = {"tool_sources": heur_ts}
                logger.info("Intent mapper skipped (fast heuristic mode)")
            else:
                try:
                    intent = await asyncio.wait_for(
                        run_metadata_intent_mapper(
                            question=body.question,
                            history=[msg.model_dump() for msg in body.history] if body.history else None,
                            generator=manager.get_generator(DEFAULT_MODEL_ID),
                        ),
                        timeout=8.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Intent mapper timeout (8s); using heuristic fallback")
        conv_only = is_conversation_only_turn(body.question, intent, has_image, has_file)
        if conv_only:
            logger.info(
                "Orchestrator: conversation-only turn — skipping RAG/web/PubMed/OpenScholar/clinical trials and research mode",
            )
            body.research_mode = False
            body.rag_search = False
            body.web_search = False
            body.pubmed_search = False
            body.openscholar_search = False
            body.clinical_trials_search = False
            body.doctor_directory_search = False
            body.allcan_search = False
            if intent:
                intent = {
                    **intent,
                    "needs_recent_info": False,
                    "needs_pubmed": False,
                    "needs_long_context": False,
                    "needs_evidence_sources": False,
                    "clinical_risk": CLINICAL_RISK_LOW,
                }
            route = ORCHESTRATOR_ROUTE_SIMPLE
        else:
            if not body.research_mode and getattr(body, "tool_automation", True):
                plan = plan_tools_for_query(body.question, intent)
                eff = apply_tool_plan_to_query_request(body, plan["sources"], user=user)
                yield sse_event({
                    "type": "status",
                    "message": format_tool_plan_message(eff),
                    "phase": "tool_plan",
                    "tools": tool_labels_es(eff),
                    "model": default_public_id,
                })
            route = orchestrate_route(body.question, has_image, has_file, body.research_mode, intent)

        logger.info("Orchestrator route: %s (research_mode=%s, clinical_risk=%s)", route, body.research_mode, (intent or {}).get("clinical_risk"))

        if route == ORCHESTRATOR_ROUTE_RESEARCH and _research_128k_available() and _model_access(user, ACADEMIC_MODEL_ID_128K, researcher_allowed)[0]:
            research_body = ResearchRequest(
                question=body.question,
                history=body.history or [],
                image=body.image,
                model=None,
                research_2_1=body.research_2_1,
                rag_search=body.rag_search,
                web_search=body.web_search,
                pubmed_search=body.pubmed_search,
                openscholar_search=body.openscholar_search,
                clinical_trials_search=body.clinical_trials_search,
                doctor_directory_search=body.doctor_directory_search,
                allcan_search=body.allcan_search,
                num_sources=10,
                file_context=body.file_context,
                iterations=5,
                max_total_sources=30,
                max_follow_links=25,
                max_trusted_sources=15,
                time_budget_seconds=900,
                excluded_sources=getattr(body, "excluded_sources", None) or [],
                excluded_topics=[],
            )
            async for evt in _research_stream_events(
                research_body,
                research_2_1=_should_use_research_21(research_body),
                user=user,
                db=db,
            ):
                yield evt
            return

        # Chat path
        chat_model_id = model_id
        if route == ORCHESTRATOR_ROUTE_MEDICAL:
            chat_model_id = "ominis-2.0-med"
        elif route == ORCHESTRATOR_ROUTE_SIMPLE:
            chat_model_id = DEFAULT_MODEL_ID

        allowed, reason = _model_access(user, chat_model_id, researcher_allowed)
        if not allowed:
            chat_model_id = DEFAULT_MODEL_ID
            allowed, reason = _model_access(user, chat_model_id, researcher_allowed)
        if not allowed:
            yield sse_event({"type": "error", "message": reason or "Model not allowed"})
            return

        async for evt in _chat_event_generator(
            body=body,
            intent=intent,
            route=route,
            model_id=chat_model_id,
            manager=manager,
            researcher_allowed=researcher_allowed,
            user=user,
            db=db,
        ):
            yield evt

    return StreamingResponse(
        main_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _tool_transparency_system_suffix(body: QueryRequest) -> str | None:
    """Tell the model which search backends ran so it can acknowledge web vs OMINIS honestly."""
    parts: list[str] = []
    if body.rag_search:
        parts.append("OMINIS (base indexada)")
    if body.web_search:
        parts.append("búsqueda web")
    if body.pubmed_search:
        parts.append("PubMed")
    if body.openscholar_search:
        parts.append("OpenScholar")
    if getattr(body, "clinical_trials_search", False):
        parts.append("ClinicalTrials.gov")
    if getattr(body, "doctor_directory_search", False):
        parts.append("Directorio de médicos MX")
    if getattr(body, "allcan_search", False):
        parts.append("All.Can México")
    if not parts:
        return None
    return (
        "TRANSPARENCIA SOBRE HERRAMIENTAS (no repitas esta lista literalmente):\n"
        "Para esta respuesta se activaron: "
        + ", ".join(parts)
        + ".\n"
        "Si la búsqueda web está en esa lista y el usuario pedía un dato concreto que no aparecía en los documentos OMINIS, "
        "empieza tu respuesta con UNA frase breve en español mexicano, por ejemplo: "
        "\"Como no encontré esa información en la base indexada OMINIS, activé la búsqueda web para complementar.\" "
        "Adapta la frase al caso. Si no se usó la web, no digas que la activaste. Si no hubo datos en las fuentes, dilo con claridad."
    )


async def _chat_event_generator(
    *,
    body: QueryRequest,
    intent: dict | None,
    route: str,
    model_id: str,
    manager,
    researcher_allowed: set,
    user: User | None,
    db: AsyncSession | None = None,
):
    use_128k = False
    research_generator = None
    public_model_id = manager.get_public_model_id(model_id)
    model_id_for_config = model_id
    cfg = get_model_config(model_id_for_config)
    logger.info(
        "query-stream: model_id=%s (route=%s) -> Ollama url=%s ollama_model=%s",
        model_id, route, (cfg.ollama_url or "").rstrip("/"), cfg.ollama_model,
    )

    async def event_generator():
        start_time = time.time()
        full_answer = ""
        chunk_count = 0
        sources_list = []

        try:
            # "Conectando..." already sent by main_stream before intent/route
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

            # Intent already computed in main_stream; use it for filtering/refinement
            generator = research_generator if use_128k else manager.get_generator(model_id)
            history_dicts = [msg.model_dump() for msg in body.history] if body.history else None
            ct_allowed = user is not None
            tools_allowed = ct_allowed
            any_search = (
                body.rag_search
                or body.web_search
                or body.pubmed_search
                or body.openscholar_search
                or (body.clinical_trials_search and ct_allowed)
                or (body.doctor_directory_search and tools_allowed)
                or (body.allcan_search and tools_allowed)
            )

            # Status: searching (explicit by tool so users can see orchestration decisions)
            search_parts = []
            status_steps: list[str] = []
            if body.rag_search:
                search_parts.append("OMINIS")
                status_steps.append("Consultando base indexada OMINIS...")
            if body.web_search:
                search_parts.append("Web")
                status_steps.append("Buscando en la web fuentes recientes y oficiales...")
            if body.pubmed_search:
                search_parts.append("PubMed")
                status_steps.append("Buscando evidencia biomédica en PubMed...")
            if body.openscholar_search:
                search_parts.append("OpenScholar")
                status_steps.append("Investigando en OpenScholar para evidencia académica...")
            if body.clinical_trials_search and ct_allowed:
                search_parts.append("ClinicalTrials.gov")
                status_steps.append("Consultando ClinicalTrials.gov (criterio México)...")
            if body.doctor_directory_search and tools_allowed:
                search_parts.append("Directorio MX")
                status_steps.append("Consultando Directorio MX para especialistas...")
            if body.allcan_search and tools_allowed:
                search_parts.append("All.Can México")
                status_steps.append("Consultando All.Can México para organizaciones de apoyo...")

            if search_parts:
                status_msg = f"Plan de búsqueda activado: {', '.join(search_parts)}."
            else:
                status_msg = "Generando respuesta..."

            yield sse_event({
                "type": "status",
                "message": status_msg,
                "model": public_model_id,
            })
            for step in status_steps:
                yield sse_event({
                    "type": "status",
                    "message": step,
                    "model": public_model_id,
                })

            if any_search:
                yield sse_event({
                    "type": "status",
                    "message": "Analizando consulta...",
                    "model": public_model_id,
                })
                yield sse_event({
                    "type": "status",
                    "message": "Interpretando intención y preparando consultas de búsqueda...",
                    "model": public_model_id,
                })
            refined_queries: list[str] = []

            # Refine queries only when at least one search backend is on (skip for conversation-only turns)
            if any_search and (
                (history_dicts and len(history_dicts) > 0)
                or body.web_search
                or body.pubmed_search
                or body.openscholar_search
                or (body.clinical_trials_search and ct_allowed)
                or (body.doctor_directory_search and tools_allowed)
                or (body.allcan_search and tools_allowed)
            ):
                refined_queries = await _refine_search_query(
                    question=body.question,
                    history=history_dicts,
                    generator=generator,
                )
                if refined_queries:
                    logger.info(f"LLM-refined queries: {refined_queries}")
                    preview = " | ".join(q.strip() for q in refined_queries[:3] if q.strip())
                    if preview:
                        yield sse_event({
                            "type": "status",
                            "message": f"Consultas clave: {preview}",
                            "model": public_model_id,
                        })
            elif any_search:
                yield sse_event({
                    "type": "status",
                    "message": "Usando la pregunta original como consulta de búsqueda.",
                    "model": public_model_id,
                })

            if any_search:
                effective_queries = [q.strip() for q in (refined_queries or [body.question]) if (q or "").strip()]
                if effective_queries:
                    yield sse_event({
                        "type": "status",
                        "message": "Consultas enviadas: " + " | ".join(effective_queries[:3]),
                        "model": public_model_id,
                    })

            # Gather sources (RAG request uses intent for top_k so post-filter has enough candidates)
            raw_documents = await _gather_sources(
                question=body.question,
                rag_search=body.rag_search,
                web_search=body.web_search,
                pubmed_search=body.pubmed_search,
                openscholar_search=body.openscholar_search,
                num_sources=body.num_sources,
                manager=manager,
                refined_queries=refined_queries if refined_queries else None,
                intent=intent,
                clinical_trials_search=body.clinical_trials_search,
                ct_model_id=model_id if body.clinical_trials_search and ct_allowed else None,
                clinical_trials_allowed=ct_allowed,
                doctor_directory_search=body.doctor_directory_search,
                allcan_search=body.allcan_search,
                doctor_directory_allowed=tools_allowed,
                allcan_allowed=tools_allowed,
                db=db,
            )
            if any_search:
                st_counts = Counter((d.meta or {}).get("source_type", "unknown") for d in raw_documents)
                labels = {
                    "rag": "OMINIS",
                    "web": "Web",
                    "pubmed": "PubMed",
                    "openscholar": "OpenScholar",
                    "clinicaltrials": "ClinicalTrials.gov",
                    "directorio_mx": "Directorio MX",
                    "allcan": "All.Can México",
                }
                pieces = [f"{labels.get(k, k)}={v}" for k, v in st_counts.items() if v > 0]
                if pieces:
                    yield sse_event({
                        "type": "status",
                        "message": "Resultados preliminares: " + ", ".join(pieces) + ".",
                        "model": public_model_id,
                    })
                # Stream top findings so users can see what was actually retrieved before synthesis.
                top_hits: list[str] = []
                for d in raw_documents[:8]:
                    meta = d.meta or {}
                    st = str(meta.get("source_type", "unknown"))
                    lbl = labels.get(st, st.upper())
                    title = (meta.get("title") or "").strip()
                    url = (meta.get("url") or "").strip()
                    host = ""
                    if url:
                        try:
                            host = urlparse(url).netloc.replace("www.", "")
                        except Exception:
                            host = ""
                    if not title and host:
                        title = host
                    if title:
                        top_hits.append(f"[{lbl}] {title[:90]}")
                    if len(top_hits) >= 4:
                        break
                if top_hits:
                    yield sse_event({
                        "type": "status",
                        "message": "Fuentes encontradas (muestra): " + " | ".join(top_hits),
                        "model": public_model_id,
                    })

            # RAG filtered by orchestrator: keep only docs whose taxonomy matches retrieval_constraints
            if intent and body.rag_search and raw_documents:
                rag_docs = [d for d in raw_documents if (d.meta or {}).get("source_type") == "rag"]
                other_docs = [d for d in raw_documents if (d.meta or {}).get("source_type") != "rag"]
                before = len(rag_docs)
                filtered_rag = filter_documents_by_intent(rag_docs, intent)
                if before != len(filtered_rag) or (intent.get("retrieval_constraints") and any(intent["retrieval_constraints"].get(d) for d in ("institucion", "tipo_documento", "dominio_salud", "territorio", "vigencia"))):
                    logger.info("RAG filtered by intent: %s -> %s docs (constraints=%s)", before, len(filtered_rag), list((k, v) for k, v in (intent.get("retrieval_constraints") or {}).items() if v))
                raw_documents = filtered_rag + other_docs

            # Drop off-topic/noisy hits before they affect synthesis and source UI.
            if raw_documents:
                before_rel = len(raw_documents)
                raw_documents = _filter_chat_documents_by_relevance(raw_documents, body.question)
                if len(raw_documents) != before_rel:
                    yield sse_event({
                        "type": "status",
                        "message": f"Filtro de relevancia: {before_rel} → {len(raw_documents)} fuentes útiles.",
                        "model": public_model_id,
                    })

            documents = _merge_sources_for_chat(
                raw_documents,
                max_total=24,
                prioritize_clinical_trials=bool(body.clinical_trials_search and ct_allowed),
            )

            ct_keywords_sse = _clinical_trials_keywords_from_documents(documents)

            all_sources_list = []
            for i, doc in enumerate(documents):
                if doc.content and doc.meta.get("url"):
                    s = _doc_to_source(doc)
                    s["ref_num"] = i + 1
                    all_sources_list.append(s)

            if all_sources_list:
                src_evt: dict = {"type": "sources", "sources": all_sources_list}
                if ct_keywords_sse:
                    src_evt["clinical_trials_keywords"] = ct_keywords_sse
                yield sse_event(src_evt)

            yield sse_event({
                "type": "status",
                "message": "Preparando contexto y respuesta...",
                "model": public_model_id,
            })

            # Step 2: Build ChatMessage objects (Haystack native); use per-model system prompt if set
            model_cfg = get_model_config(model_id_for_config)
            # Power and Med benefit from smaller prompts for faster time-to-first-token
            fast_prefill_models = ("ominis-2.0-med",)
            chat_docs = documents[:4] if model_id_for_config in fast_prefill_models else documents
            chat_max_content = 400 if model_id_for_config in fast_prefill_models else 800
            history_list = [msg.model_dump() for msg in body.history] if body.history else []
            if model_id_for_config in fast_prefill_models and len(history_list) > 4:
                # Keep last 2 exchanges (user + assistant each) to reduce prompt size
                history_list = history_list[-4:]
            messages = build_chat_messages(
                question=body.question,
                documents=chat_docs,
                history=history_list,
                image_description=image_description,
                file_context=body.file_context or "",
                system_prompt=getattr(model_cfg, "system_prompt", None) or None,
                max_content_per_doc=chat_max_content,
                med_orchestrator=(model_id_for_config == "ominis-2.0-med"),
                refiner_hint=(model_id_for_config == DEFAULT_MODEL_ID),
                extra_system_suffix=_tool_transparency_system_suffix(body),
            )

            # Step 3: Stream generation via OllamaChatGenerator
            chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

            def streaming_callback(chunk: StreamingChunk):
                text = chunk.content
                if text:
                    chunk_queue.put_nowait(text)

            generator = research_generator if use_128k else manager.get_generator(model_id)

            _s_gpu = get_settings()
            # Remote Ollama cold-start hints are misleading when this model uses OpenAI / Anthropic / etc.
            _uses_remote_ollama = not (
                getattr(model_cfg, "use_openai", False) or getattr(model_cfg, "use_anthropic", False)
            )
            _cold_gpu = _uses_remote_ollama and _likely_cold_gpu(_s_gpu)
            yield sse_event({
                "type": "status",
                "message": (
                    "Iniciando GPU (30s–5 min si está fría). Puedes esperar en esta pantalla…"
                    if _cold_gpu
                    else "Conectando con el modelo…"
                ),
                "model": public_model_id,
                "phase": "gpu_warmup" if _cold_gpu else "connecting",
            })

            async def run_generator():
                loop = asyncio.get_event_loop()
                try:
                    return await loop.run_in_executor(
                        None,
                        lambda: generator.run(
                            messages=messages,
                            streaming_callback=streaming_callback,
                        ),
                    )
                finally:
                    # Always unblock the SSE loop if the executor raises (e.g. OpenAI 400 unknown model).
                    try:
                        chunk_queue.put_nowait(None)
                    except Exception:
                        pass

            gen_task = asyncio.create_task(run_generator())

            # First-token deadline: cold GPU load (localhost Docker Ollama, Vast, serverless) often exceeds 120s.
            _s = _s_gpu
            _qst = float(getattr(_s, "query_stream_generation_timeout", 0) or 0)
            _vct = float(getattr(_s, "vast_serverless_client_timeout", 900) or 900)
            _baseline = max(_vct, 600.0)
            if _qst > 0:
                generation_timeout = _qst
            elif model_id == "ominis-2.0-med":
                generation_timeout = max(180.0, _baseline)
            else:
                generation_timeout = _baseline
            heartbeat_interval = 25.0 if generation_timeout >= 600 else 20.0
            wait_elapsed = 0.0

            # Refiner phase: when Ominis 2.0 outputs [REFINAR:med] or [REFINAR:research], we stream a second response
            REFINAR_MED = "[REFINAR:med]"
            REFINAR_RESEARCH = "[REFINAR:research]"
            stream_buffer = ""
            emitted_len = 0
            refiner_phase: Optional[str] = None  # "med" | "research"

            while True:
                try:
                    token = await asyncio.wait_for(chunk_queue.get(), timeout=heartbeat_interval)
                except asyncio.TimeoutError:
                    wait_elapsed += heartbeat_interval
                    if wait_elapsed >= generation_timeout:
                        yield sse_event({"type": "error", "message": "Generation timed out"})
                        break
                    status_extra = " Med puede tardar un momento en la primera respuesta." if model_id == "ominis-2.0-med" else ""
                    yield sse_event({
                        "type": "status",
                        "message": "El modelo está generando... (puede tardar un momento)" + status_extra,
                        "model": public_model_id,
                        "phase": "waiting_first_token",
                        "waitSeconds": int(wait_elapsed),
                    })
                    continue

                if token is None:
                    break

                wait_elapsed = 0.0  # reset so timeout only applies when no tokens arrive
                token = _sanitize_text(token)
                stream_buffer += token
                rest = stream_buffer[emitted_len:]
                # Check for refiner tag (longer first to avoid partial match)
                if REFINAR_RESEARCH in rest:
                    pos = rest.find(REFINAR_RESEARCH)
                    to_emit = rest[:pos]
                    if to_emit:
                        full_answer += to_emit
                        chunk_count += 1
                        yield sse_event({"type": "chunk", "text": to_emit})
                    emitted_len += pos + len(REFINAR_RESEARCH)
                    refiner_phase = "research"
                elif REFINAR_MED in rest:
                    pos = rest.find(REFINAR_MED)
                    to_emit = rest[:pos]
                    if to_emit:
                        full_answer += to_emit
                        chunk_count += 1
                        yield sse_event({"type": "chunk", "text": to_emit})
                    emitted_len += pos + len(REFINAR_MED)
                    refiner_phase = "med"
                else:
                    # Emit only the part that cannot start a tag (hold back up to 18 chars)
                    max_hold = 18
                    if len(rest) > max_hold:
                        safe = rest[:-max_hold]
                        full_answer += safe
                        chunk_count += 1
                        yield sse_event({"type": "chunk", "text": safe})
                        emitted_len = len(stream_buffer) - max_hold
                    elif rest and "[" not in rest:
                        full_answer += rest
                        chunk_count += 1
                        yield sse_event({"type": "chunk", "text": rest})
                        emitted_len = len(stream_buffer)

            # Emit any remaining buffer (after last possible tag)
            if emitted_len < len(stream_buffer):
                tail = stream_buffer[emitted_len:]
                full_answer += tail
                chunk_count += 1
                yield sse_event({"type": "chunk", "text": tail})

            await gen_task

            # Second phase: if Ominis 2.0 requested Med or Research, stream a follow-up
            if refiner_phase == "med":
                yield sse_event({
                    "type": "status",
                    "message": "Consultando Ominis Med para una opinión clínica más precisa...",
                    "model": public_model_id,
                })
                try:
                    med_gen = manager.get_generator("ominis-2.0-med")
                    med_cfg = get_model_config("ominis-2.0-med")
                    med_messages = build_chat_messages(
                        question=body.question,
                        documents=[],  # no extra docs for refiner
                        history=history_list + [{"role": "user", "content": body.question}, {"role": "assistant", "content": full_answer}],
                        image_description=image_description,
                        file_context=body.file_context or "",
                        system_prompt=getattr(med_cfg, "system_prompt", None) or None,
                        max_content_per_doc=400,
                        med_orchestrator=True,
                        refiner_hint=False,
                    )
                    med_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
                    def med_cb(chunk: StreamingChunk):
                        if chunk.content:
                            med_queue.put_nowait(chunk.content)

                    async def run_med():
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: med_gen.run(messages=med_messages, streaming_callback=med_cb),
                        )
                        await med_queue.put(None)

                    task_med = asyncio.create_task(run_med())
                    while True:
                        try:
                            tok = await asyncio.wait_for(med_queue.get(), timeout=30.0)
                        except asyncio.TimeoutError:
                            yield sse_event({"type": "status", "message": "Ominis Med está generando...", "model": public_model_id})
                            continue
                        if tok is None:
                            break
                        tok = _sanitize_text(tok)
                        full_answer += tok
                        chunk_count += 1
                        yield sse_event({"type": "chunk", "text": tok})
                    await task_med
                except Exception as e:
                    logger.warning("Refiner Med phase failed: %s", e)
                    full_answer += "\n\n(Ominis Med no disponible para refinar en este momento.)"
                    yield sse_event({"type": "chunk", "text": "\n\n(Ominis Med no disponible para refinar en este momento.)"})
            elif refiner_phase == "research":
                # Suggested extra sources are sent on `done` as suggested_add_tools; no footer chunk.
                pass

            # Any clinical response validated by Ominis 2.0 Med when enabled
            use_validator = (
                (intent and should_use_clinical_validator(intent, documents))
                or content_has_clinical_signals(body.question, full_answer)
            )
            if use_validator:
                try:
                    logger.info("Running clinical validator (Ominis 2.0 Med) for query stream")
                    clinic_gen = manager.get_generator("ominis-2.0-med")
                    validator_out = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: run_clinical_validator_sync(
                            body.question,
                            full_answer,
                            clinic_gen,
                        ),
                    )
                    disclaimer = format_validator_disclaimer(validator_out)
                    if disclaimer:
                        full_answer += disclaimer
                except Exception as e:
                    logger.warning("Clinical validator skip: %s", e)
                    full_answer += VALIDATOR_UNAVAILABLE_DISCLAIMER

            sources_list, sources_not_used = _split_sources_by_citation(full_answer, all_sources_list)
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
            # Output token estimate: streaming chunk count (Ollama often 1 chunk ≈ 1 token)
            tokens_per_sec = (chunk_count / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else None

            done_evt: dict = {
                "type": "done",
                "answer": full_answer,
                "sources": sources_list,
                "charts": charts if charts else None,
                "model": public_model_id,
                "elapsed_ms": elapsed_ms,
            }
            if sources_not_used:
                done_evt["sources_not_used"] = sources_not_used
            if ct_keywords_sse:
                done_evt["clinical_trials_keywords"] = ct_keywords_sse
            try:
                suggested_add = suggest_tools_for_followup(
                    body.question,
                    full_answer,
                    intent,
                    eff_from_body(body),
                    user=user,
                )
                if suggested_add:
                    done_evt["suggested_add_tools"] = suggested_add
            except Exception as ex:
                logger.debug("suggested_add_tools skip: %s", ex)
            yield sse_event(done_evt)

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
                    output_tokens=chunk_count,
                    tokens_per_second=tokens_per_sec,
                )
            )

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            err_msg = str(e)
            if model_id == "ominis-2.0-med" and ("not found" in err_msg.lower() or "404" in err_msg):
                err_msg = (
                    "El modelo Med42 no está instalado en el servidor Ollama. "
                    "Un administrador debe ejecutar en el servidor GPU: ollama pull med42 (o el nombre del modelo en OLLAMA_MED_MODEL)."
                )
            yield sse_event({"type": "error", "message": err_msg})

    async for evt in event_generator():
        yield evt


async def _research_stream_events(
    body: ResearchRequest,
    research_2_1: bool = False,
    user: User | None = None,
    db: AsyncSession | None = None,
):
    """
    Research/academic mode: OpenScholar 128K when OPENSCHOLAR_128K_API_URL is set (e.g. Vast.ai).
    When research_2_1=True: deep multi-round (second round from conclusions) + section-by-section report + final assembly.
    """
    # En modo investigación siempre activar las cuatro búsquedas (orden de importancia: Ominis, OpenScholar, PubMed, Web)
    body.rag_search = True
    body.web_search = True
    body.pubmed_search = True
    body.openscholar_search = True

    manager = get_pipeline_manager()
    generator, public_model_id, degradation_msg = _get_research_generator_and_model_id()
    research_api_model = _backend_openai_model_for_research_stream(public_model_id)
    logger.info("Research mode: using %s", public_model_id)
    gather_kw = {
        "clinical_trials_search": body.clinical_trials_search,
        "ct_model_id": (
            DEFAULT_MODEL_ID if body.clinical_trials_search and user is not None else None
        ),
        "clinical_trials_allowed": user is not None,
        "doctor_directory_search": body.doctor_directory_search,
        "allcan_search": body.allcan_search,
        "doctor_directory_allowed": user is not None,
        "allcan_allowed": user is not None,
        "db": db,
    }

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

        history_dicts = [msg.model_dump() for msg in body.history] if body.history else []
        is_phase2 = False
        if history_dicts and len(history_dicts) >= 2:
            for msg in history_dicts:
                if msg.get("role") == "assistant" and "?" in (msg.get("content") or "") and len(msg.get("content", "")) > 50:
                    is_phase2 = True
                    break

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
            original_topic = ""
            user_answers = ""
            for msg in history_dicts:
                if msg.get("role") == "user":
                    if not original_topic:
                        original_topic = msg.get("content", "")
                    else:
                        user_answers += msg.get("content", "") + "\n"
            user_answers += body.question
            plan_input = (
                f"{original_topic}\n\n"
                "ESPECIFICACIONES DEL USUARIO (alcance geográfico, periodo, público meta, subtemas a incluir/excluir):\n"
                f"{user_answers}\n"
                "Genera el plan: focus, queries (solo sobre el tema y subtemas; no sobre público meta) y sections."
            )
            plan = await _build_research_plan(plan_input, generator)

        queries = plan.get("queries", [])
        research_notes: list[str] = []

        if not is_phase2:
            collected: list[Document] = []
            yield sse_event({"type": "status", "message": "Buscando fuentes iniciales...", "model": public_model_id})
            seed_queries = queries[:3] if queries else [body.question]
            for q in seed_queries:
                docs = await _gather_sources(
                    question=q,
                    rag_search=body.rag_search, web_search=body.web_search,
                    pubmed_search=body.pubmed_search, openscholar_search=body.openscholar_search,
                    num_sources=min(max(body.num_sources, 5), 8), manager=manager,
                    **gather_kw,
                )
                collected.extend(docs)
            # Phase 1: filter by topic (drop obvious off-topic), then LLM relevance for plan sources.
            candidates = _merge_sources_for_chat(
                collected,
                max_total=30,
                prioritize_clinical_trials=bool(body.clinical_trials_search and user is not None),
            )
            topic_terms = _extract_topic_terms(body.question)
            enforce_health = _topic_is_health_related(body.question)
            scored = [(d, _heuristic_source_score(d, topic_terms, enforce_health)) for d in candidates]
            scored.sort(key=lambda x: x[1], reverse=True)
            # Drop clearly off-topic (negative or very low score) so plan only shows relevant seeds.
            plan_candidates = [d for d, s in scored if s > -0.3][:25]
            if not plan_candidates:
                plan_candidates = [d for d, _ in scored[:15]]
            try:
                ranked, _ = await _score_source_relevance(
                    topic=body.question,
                    user_spec="",
                    documents=plan_candidates,
                    generator=generator,
                    min_keep=5,
                    max_keep=10,
                )
                if len(ranked) >= 5:
                    collected = ranked[:10]
                else:
                    collected = plan_candidates[:10]
            except Exception:
                collected = plan_candidates[:10]
        else:
            collected = []
            seen_urls: set[str] = set()
            read_urls: set[str] = set()
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

            focus = plan.get("focus", "")
            yield emit_step("plan", f"Plan: {focus}", result=f"{len(queries)} consultas",
                reasoning=f"Definiendo el plan de investigación para abordar: {focus[:80]}{'...' if len(focus) > 80 else ''}. Consultas iniciales: {len(queries)}.")

            search_queries = []
            for q in (queries or []):
                # APIs often return 0 for very long queries; use a short search phrase.
                short_q = (q[:120] + "...") if len(q) > 120 else q
                search_queries.append(short_q.strip() or q)
            if not search_queries:
                search_queries = [original_topic[:120] if len(original_topic or "") > 120 else (original_topic or body.question)]

            for i, q in enumerate(search_queries):
                yield sse_event({"type": "status", "message": f"Buscando ({i+1}/{len(search_queries)}): {q[:50]}...", "model": public_model_id})
                yield emit_step("search", f"Buscando: {q}",
                    reasoning=f"Buscaré en PubMed, web y bases locales información sobre: {q[:60]}{'...' if len(q) > 60 else ''}. Es relevante para el tema de {focus[:40]}{'...' if len(focus) > 40 else ''}.")
                docs = await _gather_sources(
                    question=q, rag_search=body.rag_search,
                    web_search=body.web_search, pubmed_search=body.pubmed_search,
                    openscholar_search=body.openscholar_search,
                    num_sources=body.num_sources, manager=manager,
                    **gather_kw,
                )
                collected.extend(docs)
                total_found += len(docs)
                yield emit_step("search_result", f"Resultados: {q[:40]}", result=f"{len(docs)} fuentes",
                    reasoning=f"Encontré {len(docs)} fuentes. Evaluando cuáles profundizar para el reporte.")

            if total_found == 0 and (original_topic or body.question):
                yield emit_step("refine", "Búsqueda inicial sin resultados; refinando consultas",
                    reasoning="La búsqueda no devolvió fuentes. Generando consultas alternativas más cortas.")
                fallback_queries = await _refine_search_query(
                    question=original_topic or body.question,
                    history=history_dicts, generator=generator,
                )
                for q in (fallback_queries or [])[:4]:
                    q_short = q[:100].strip() if len(q) > 100 else q
                    docs = await _gather_sources(
                        question=q_short, rag_search=body.rag_search,
                        web_search=body.web_search, pubmed_search=body.pubmed_search,
                        openscholar_search=body.openscholar_search,
                        num_sources=body.num_sources, manager=manager,
                        **gather_kw,
                    )
                    collected.extend(docs)
                    total_found += len(docs)
                    yield emit_step("search_result", f"Refinada: {q_short[:40]}", result=f"{len(docs)} fuentes",
                        reasoning=f"Me interesaron {len(docs)} fuentes. Las incorporaré al análisis.")

            # Do NOT add extra search queries from user_answers here. The plan already incorporated
            # scope (geography, timeframe, audience). Audience (público meta) is for the report, not
            # for search; generating queries from it produces nonsensical searches like
            # "Profesionales de la Salud en México".

            candidates = deduplicate_and_rank_with_quality(
                collected,
                focus or original_topic or body.question,
                max_total=50,
                use_quality_score=True,
                rerank_if_available=True,
            )
            candidates.sort(key=_source_priority)
            yield emit_step("filter", f"{len(collected)} → {len(candidates)} únicas",
                reasoning=f"Filtrando duplicados: de {len(collected)} resultados a {len(candidates)} fuentes únicas para leer.")

            # Read at least 15–20% of candidates or 10 sources, whichever is more (so we can judge relevance); cap at max_follow_links
            min_sources_to_read = max(12, math.ceil(len(candidates) * 0.20))
            read_limit = min(max(min_sources_to_read, body.max_follow_links), 40)
            read_deadline = time.time() + 600
            fetched_count = 0
            follow_urls: list[str] = []
            readable = []
            for d in candidates:
                url = d.meta.get("url", "")
                if url and url not in seen_urls:
                    readable.append(d)

            yield emit_step("read_start", f"Leyendo hasta {read_limit} de {len(readable)} fuentes (mín. {min_sources_to_read} para evaluar relevancia)",
                reasoning=f"Leyendo al menos el 15-20% más relevante de las fuentes encontradas para poder decidir cuáles incluir en el reporte.")

            for doc in readable:
                if time.time() > read_deadline or fetched_count >= read_limit:
                    yield emit_step("read_skip", f"Límite alcanzado: {fetched_count}/{read_limit} leídas",
                        reasoning="Respetando el límite de fuentes para garantizar un reporte enfocado y completo.")
                    break
                url = doc.meta.get("url", "")
                seen_urls.add(url)
                title_hint = doc.meta.get("title", "")[:120]
                yield sse_event({"type": "status", "message": f"Leyendo ({fetched_count+1}/{len(readable)}): {(doc.meta.get('title') or '')[:50] or url[:40]}...", "model": public_model_id})
                yield emit_step("read", f"Leyendo: {title_hint}", url=url,
                    reasoning=f"Leyendo esta fuente para extraer datos relevantes sobre {focus[:50]}{'...' if len(focus) > 50 else ''}.")
                try:
                    title, text, links = await _fetch_url_content(url)
                except Exception as e:
                    yield emit_step("read_fail", f"Error: {title_hint}", url=url, result=str(e)[:80],
                        reasoning="No pude extraer contenido de esta fuente. Continuando con otras.")
                    continue
                if text and len(text) > 50 and not _is_captcha_or_error_page(text, url):
                    ref_meta = extract_reference_metadata(text, url)
                    meta = {"title": title or title_hint, "url": url, "source_type": doc.meta.get("source_type", "webpage")}
                    meta.update({k: v for k, v in ref_meta.items() if k != "url" and v})
                    collected.append(Document(
                        content=text,
                        meta=meta,
                    ))
                    fetched_count += 1
                    total_read += 1
                    read_urls.add(url)
                    preview = text[:200].replace("\n", " ")
                    research_notes.append(f"{title or title_hint}: {preview}")
                    yield emit_step("read_done", f"{title or title_hint}", url=url, result=f"{len(text)} chars — {preview[:80]}",
                        reasoning=f"Hallazgo: {preview[:120]}... Tomando nota para citar en el reporte.")
                    for link in links:
                        if _is_trustworthy_domain(link) and link not in seen_urls:
                            follow_urls.append(link)
                elif doc.content and len(doc.content.strip()) > 30:
                    # Semantic Scholar / API often returns captcha on fetch; keep abstract from search.
                    collected.append(Document(
                        content=doc.content,
                        meta={"title": doc.meta.get("title") or title_hint, "url": url, "source_type": doc.meta.get("source_type", "webpage")},
                    ))
                    fetched_count += 1
                    total_read += 1
                    read_urls.add(url)
                    preview = (doc.content or "")[:200].replace("\n", " ")
                    research_notes.append(f"{title_hint}: {preview}")
                    yield emit_step("read_done", f"{title_hint}", url=url, result=f"abstract — {preview[:80]}",
                        reasoning="Usando resumen de la API (página bloqueada). Tomando nota para citar en el reporte.")
                else:
                    yield emit_step("read_fail", f"Sin contenido útil", url=url, result=f"{len(text or '')} chars",
                        reasoning="Contenido no útil. Marcando para no incluir en el reporte.")

            if follow_urls and time.time() < read_deadline:
                unique_follows = []
                for link in follow_urls:
                    if link not in seen_urls and len(unique_follows) < read_limit:
                        unique_follows.append(link)
                if unique_follows:
                    yield emit_step("follow", f"Siguiendo {len(unique_follows)} enlaces confiables",
                        reasoning=f"Explorando enlaces adicionales de fuentes confiables para ampliar la investigación.")
                    for link in unique_follows:
                        if time.time() > read_deadline or fetched_count >= read_limit + 10:
                            break
                        seen_urls.add(link)
                        yield sse_event({"type": "status", "message": f"Siguiendo: {link[:50]}...", "model": public_model_id})
                        yield emit_step("read", "Enlace", url=link,
                            reasoning="Leyendo enlace secundario para completar el contexto.")
                        title, text, _ = await _fetch_url_content(link)
                        if text and len(text) > 50:
                            collected.append(Document(
                                content=text,
                                meta={"title": title or "", "url": link, "source_type": "webpage"},
                            ))
                            fetched_count += 1
                            total_read += 1
                            read_urls.add(link)
                            research_notes.append(f"{title or link[:40]}: {(text or '')[:200].replace(chr(10), ' ')}")
                            yield emit_step("read_done", f"{title or link[:40]}", url=link, result=f"{len(text)} chars",
                                reasoning="Contenido adicional útil. Incorporando al análisis.")

            elapsed_search = int(time.time() - start_time)
            yield emit_step("complete", "Investigación completa", result=f"{total_found} encontradas, {total_read} leídas, {elapsed_search}s",
                reasoning=f"Consolidando lo que he encontrado: {total_found} fuentes encontradas, {total_read} leídas. Preparando el reporte con citas específicas.")
            logger.info(f"Deep research: {total_found} found, {total_read} read, {fetched_count} fetched, {elapsed_search}s")

            # Research 2.1: ROUND 2 — deepen on findings
            if research_2_1 and research_notes:
                yield sse_event({"type": "status", "message": "Ronda 2: profundizando en hallazgos...", "model": public_model_id})
                yield emit_step("round2", "Profundizando en hallazgos clave",
                    reasoning="Analizando las notas de lectura para identificar áreas que requieren mayor profundidad.")
                deepening = await _get_deepening_queries(focus, research_notes, generator, research_api_model)
                for q in deepening:
                    yield sse_event({"type": "status", "message": f"Profundizando: {q[:50]}...", "model": public_model_id})
                    yield emit_step("search", f"Profundización: {q}",
                        reasoning=f"Buscando evidencia adicional sobre: {q[:60]}")
                    docs = await _gather_sources(
                        question=q, rag_search=body.rag_search,
                        web_search=body.web_search, pubmed_search=body.pubmed_search,
                        openscholar_search=body.openscholar_search,
                        num_sources=body.num_sources, manager=manager,
                        **gather_kw,
                    )
                    collected.extend(docs)
                    total_found += len(docs)
                    # Read new sources immediately
                    new_candidates = _deduplicate_and_rank(docs, max_total=8)
                    for nd in new_candidates:
                        nurl = nd.meta.get("url", "")
                        if nurl and nurl not in seen_urls and time.time() < read_deadline:
                            seen_urls.add(nurl)
                            try:
                                t, txt, _ = await _fetch_url_content(nurl)
                                if txt and len(txt) > 50:
                                    ref_meta = extract_reference_metadata(txt, nurl)
                                    meta = {"title": t or "", "url": nurl, "source_type": "webpage"}
                                    meta.update({k: v for k, v in ref_meta.items() if k != "url" and v})
                                    collected.append(Document(content=txt, meta=meta))
                                    total_read += 1
                                    read_urls.add(nurl)
                                    research_notes.append(f"{t or nurl[:40]}: {txt[:200].replace(chr(10), ' ')}")
                                    yield emit_step("read_done", f"{t or nurl[:40]}", url=nurl, result=f"{len(txt)} chars",
                                        reasoning="Fuente adicional de ronda 2. Incorporando al análisis.")
                            except Exception:
                                pass

            # Research 2.1: ROUND 3 — gap analysis (what's still missing?)
            if research_2_1 and research_notes:
                yield sse_event({"type": "status", "message": "Ronda 3: analizando lagunas de conocimiento...", "model": public_model_id})
                yield emit_step("round3", "Análisis de lagunas de conocimiento",
                    reasoning="Revisando toda la evidencia recopilada para identificar qué falta para un reporte completo y riguroso.")
                try:
                    gap_sys, gap_usr = get_gap_analysis_prompt(focus, research_notes, user_answers if 'user_answers' in locals() else "")
                    gap_msgs = [ChatMessage.from_system(gap_sys), ChatMessage.from_user(gap_usr)]
                    loop = asyncio.get_event_loop()
                    gap_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda om=research_api_model: generator.run(
                                messages=gap_msgs,
                                generation_kwargs=openai_chat_completion_generation_kwargs(
                                    om, temperature=0.3, num_predict=1024
                                ),
                            ),
                        ),
                        timeout=60.0,
                    )
                    gap_text = (gap_result.get("replies", [{}])[0].text or "") if gap_result.get("replies") else ""
                    gap_data = _extract_json_object(gap_text) or {}
                    gap_queries = gap_data.get("queries", [])
                    gaps_identified = gap_data.get("gaps", [])
                    if gaps_identified:
                        yield emit_step("gaps", f"Lagunas identificadas: {len(gaps_identified)}",
                            reasoning="Lagunas: " + "; ".join(g[:60] for g in gaps_identified[:5]))
                    for q in gap_queries[:4]:
                        yield sse_event({"type": "status", "message": f"Llenando laguna: {q[:50]}...", "model": public_model_id})
                        yield emit_step("search", f"Laguna: {q}",
                            reasoning=f"Buscando evidencia para llenar: {q[:60]}")
                        docs = await _gather_sources(
                            question=q, rag_search=body.rag_search,
                            web_search=body.web_search, pubmed_search=body.pubmed_search,
                            openscholar_search=body.openscholar_search,
                            num_sources=body.num_sources, manager=manager,
                            **gather_kw,
                        )
                        collected.extend(docs)
                        total_found += len(docs)
                        new_candidates = _deduplicate_and_rank(docs, max_total=6)
                        for nd in new_candidates:
                            nurl = nd.meta.get("url", "")
                            if nurl and nurl not in seen_urls and time.time() < read_deadline:
                                seen_urls.add(nurl)
                                try:
                                    t, txt, _ = await _fetch_url_content(nurl)
                                    if txt and len(txt) > 50:
                                        ref_meta = extract_reference_metadata(txt, nurl)
                                        meta = {"title": t or "", "url": nurl, "source_type": "webpage"}
                                        meta.update({k: v for k, v in ref_meta.items() if k != "url" and v})
                                        collected.append(Document(content=txt, meta=meta))
                                        total_read += 1
                                        read_urls.add(nurl)
                                        research_notes.append(f"{t or nurl[:40]}: {txt[:200].replace(chr(10), ' ')}")
                                except Exception:
                                    pass
                except Exception as e:
                    logger.warning("Research 2.1 gap analysis failed: %s", e)

        final_max = body.max_total_sources * 2 if research_2_1 else body.max_total_sources
        if is_phase2:
            documents = deduplicate_and_rank_with_quality(
                collected,
                focus or original_topic or body.question,
                max_total=final_max,
                use_quality_score=True,
                rerank_if_available=True,
            )
        else:
            documents = _merge_sources_for_chat(
                collected,
                max_total=final_max,
                prioritize_clinical_trials=bool(body.clinical_trials_search and user is not None),
            )
        if body.excluded_sources:
            excluded_set = set(body.excluded_sources)
            before = len(documents)
            documents = [d for d in documents if d.meta.get("url", "") not in excluded_set]
            if is_phase2 and before != len(documents):
                yield emit_step("filter", f"Excluidas {before - len(documents)} fuentes por el usuario",
                    reasoning="Respetando las fuentes que el usuario decidió excluir del plan.")
        if is_phase2 and research_2_1 and "read_urls" in locals() and read_urls:
            before = len(documents)
            documents = [d for d in documents if d.meta.get("url", "") in read_urls]
            if before != len(documents):
                yield emit_step("filter", f"Filtradas {before - len(documents)} no leídas",
                    reasoning=f"Research 2.1 solo conserva fuentes realmente leídas ({len(documents)}).")

        if is_phase2 and len(documents) > 5 and not research_2_1:
            # Non-2.1: LLM relevance filter (may aggressively reduce sources)
            yield sse_event({"type": "status", "message": "Evaluando relevancia de fuentes...", "model": public_model_id})
            yield emit_step("relevance", f"Evaluando {len(documents)} fuentes para relevancia",
                reasoning=f"Identificando cuáles de {len(documents)} fuentes son más relevantes para el tema del usuario.")
            documents, relevance_reason = await _score_source_relevance(
                topic=original_topic,
                user_spec=user_answers,
                documents=documents,
                generator=generator,
                min_keep=8,
                max_keep=14,
            )
            reasoning_done = relevance_reason if relevance_reason else f"Seleccionadas las {len(documents)} fuentes más pertinentes para elaborar el reporte."
            yield emit_step("relevance_done", f"{len(documents)} fuentes relevantes seleccionadas",
                reasoning=reasoning_done)
        elif is_phase2 and research_2_1 and len(documents) > 5:
            # Research 2.1: prioritize but keep enough breadth for multi-section synthesis.
            yield sse_event({"type": "status", "message": "Priorizando fuentes para Research 2.1...", "model": public_model_id})
            documents, relevance_reason = await _score_source_relevance(
                topic=original_topic,
                user_spec=user_answers,
                documents=documents,
                generator=generator,
                min_keep=12,
                max_keep=22,
            )
            reasoning_done = relevance_reason if relevance_reason else f"Priorizadas {len(documents)} fuentes relevantes para Research 2.1."
            yield emit_step("relevance_done", f"{len(documents)} fuentes priorizadas para el reporte",
                reasoning=reasoning_done)

        # Abort phase 2 if no documents: avoid generating an empty report
        if is_phase2 and len(documents) == 0:
            msg = (
                "No se encontraron fuentes para generar el reporte. "
                "Posibles causas: búsquedas sin resultados, timeouts o fuentes excluidas. "
                "Revisa que **RAG**, **Web** y/o **PubMed** estén activos en las opciones de búsqueda e intenta de nuevo, "
                "o reformula el tema."
            )
            yield sse_event({"type": "chunk", "text": msg})
            yield sse_event({
                "type": "done",
                "answer": msg,
                "sources": [],
                "model": public_model_id,
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "is_report": False,
            })
            return

        all_sources_list = []
        for i, doc in enumerate(documents):
            if doc.content and doc.meta.get("url"):
                s = _doc_to_source(doc)
                s["ref_num"] = i + 1
                all_sources_list.append(s)
        ct_kw_research = _clinical_trials_keywords_from_documents(documents)
        if all_sources_list:
            # En fase 2 no enviamos la lista completa; solo las fuentes citadas en el payload "done".
            if not is_phase2:
                rs_evt: dict = {"type": "sources", "sources": all_sources_list}
                if ct_kw_research:
                    rs_evt["clinical_trials_keywords"] = ct_kw_research
                yield sse_event(rs_evt)
            if is_phase2:
                yield emit_step("sources", f"{len(all_sources_list)} fuentes para el reporte",
                    reasoning=f"Generando reporte con {len(all_sources_list)} fuentes, citando científicamente cada origen.")
                if plan and plan.get("sections"):
                    yield emit_step("structure", "Estructura del reporte",
                        reasoning="Secciones: " + " → ".join(plan["sections"]))

        yield sse_event({
            "type": "status",
            "message": "Generando reporte..." if is_phase2 else "Preparando plan...",
            "model": public_model_id,
        })

        # Optional: Evidence Extractor + Bias Auditor (phase 2 only, Qwen) — skip for Research 2.1
        evidence_extracts: dict | list = {}
        bias_audit: dict = {}
        if is_phase2 and len(documents) >= 2 and not research_2_1:
            try:
                qwen_gen = manager.get_generator()
                loop = asyncio.get_event_loop()
                evidence_extracts = await loop.run_in_executor(
                    None,
                    lambda: run_evidence_extractor_sync(qwen_gen, documents, max_docs=10),
                ) or {}
                bias_audit = await loop.run_in_executor(
                    None,
                    lambda: run_bias_auditor_sync(qwen_gen, evidence_extracts),
                ) or {}
            except Exception as e:
                logger.warning("Research agents (evidence/bias) failed: %s", e)

        if research_2_1 and is_phase2:
            import tempfile, os
            # Research 2.1 Deep: multi-iteration, per-section clinical analysis, detailed outline
            # ──────────────────────────────────────────────────────────────────────────────────────
            # STEP A: Design detailed outline from all evidence
            yield sse_event({"type": "status", "message": "Diseñando estructura detallada del documento...", "model": public_model_id})
            yield emit_step("outline", "Diseñando índice detallado del documento",
                reasoning=f"Analizando {len(research_notes)} notas de investigación para crear una estructura exhaustiva y específica al tema.")
            detailed_sections = []
            try:
                outline_sys, outline_usr = get_detailed_outline_prompt(
                    focus, research_notes, body.question,
                    user_answers if 'user_answers' in locals() else "",
                )
                outline_msgs = [ChatMessage.from_system(outline_sys), ChatMessage.from_user(outline_usr)]
                loop = asyncio.get_event_loop()
                outline_result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda om=research_api_model: generator.run(
                            messages=outline_msgs,
                            generation_kwargs=openai_chat_completion_generation_kwargs(
                                om, temperature=0.3, num_predict=2048
                            ),
                        ),
                    ),
                    timeout=90.0,
                )
                outline_text = (outline_result.get("replies", [{}])[0].text or "") if outline_result.get("replies") else ""
                outline_data = _extract_json_object(outline_text) or {}
                raw_sections = outline_data.get("sections", [])
                for s in raw_sections:
                    if isinstance(s, dict) and s.get("title"):
                        detailed_sections.append(s)
                    elif isinstance(s, str):
                        detailed_sections.append({"title": s, "description": "", "needs_clinical": False, "needs_chart": False})
            except Exception as e:
                logger.warning("Research 2.1 outline failed: %s", e)
            if len(detailed_sections) < 5:
                detailed_sections = [
                    {"title": s, "description": "", "needs_clinical": False, "needs_chart": False}
                    for s in plan.get("sections", ["Resumen ejecutivo", "Contexto epidemiológico", "Mecanismos y fisiopatología",
                        "Diagnóstico y clasificación", "Hallazgos principales", "Análisis comparativo",
                        "Tratamientos actuales", "Guías clínicas", "Perspectivas para México",
                        "Discusión", "Limitaciones", "Conclusiones"])
                ]
            # References are built programmatically at the end; avoid generating duplicated "Referencias" sections.
            detailed_sections = [
                s for s in detailed_sections
                if "referenc" not in (s.get("title", "").lower()) and "bibliograf" not in (s.get("title", "").lower())
            ]
            # Always ensure Resumen ejecutivo is first and Conclusiones is last
            section_titles = [s["title"] for s in detailed_sections]
            if "Resumen ejecutivo" not in section_titles:
                detailed_sections.insert(0, {"title": "Resumen ejecutivo", "description": "Síntesis de hallazgos principales", "needs_clinical": False, "needs_chart": False})
            for i, s in enumerate(list(detailed_sections)):
                if s.get("title", "").strip().lower() == "conclusiones" and i != len(detailed_sections) - 1:
                    detailed_sections.append(detailed_sections.pop(i))
                    break
            yield emit_step("outline_done", f"Índice: {len(detailed_sections)} secciones",
                reasoning="Índice: " + " → ".join(s["title"] for s in detailed_sections))

            # Narrative spine for coherence across sections
            narrative_thread = ""
            try:
                thread_messages = [
                    ChatMessage.from_system(
                        "Eres editor científico. Diseña un hilo conductor para un reporte. "
                        "Responde SOLO con 5-7 viñetas cortas (cada una <= 18 palabras), en español, "
                        "que conecten problema -> evidencia -> comparación -> límites -> implicaciones."
                    ),
                    ChatMessage.from_user(
                        f"Tema: {body.question}\n"
                        f"Enfoque: {focus}\n"
                        f"Secciones: {' | '.join(s['title'] for s in detailed_sections[:20])}\n"
                        "Escribe el hilo conductor."
                    ),
                ]
                loop = asyncio.get_event_loop()
                thread_result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda om=research_api_model: generator.run(
                            messages=thread_messages,
                            generation_kwargs=openai_chat_completion_generation_kwargs(
                                om, temperature=0.2, num_predict=320
                            ),
                        ),
                    ),
                    timeout=45.0,
                )
                thread_replies = thread_result.get("replies", [])
                narrative_thread = (thread_replies[0].text or "").strip() if thread_replies else ""
                if narrative_thread:
                    yield emit_step("structure", "Hilo conductor definido",
                        reasoning=_truncate_step(narrative_thread, 280))
            except Exception as e:
                logger.warning("Research 2.1 narrative thread failed: %s", e)

            # STEP B: Persist outline and write sections to temp dir
            tmp_dir = tempfile.mkdtemp(prefix="research21_")
            outline_path = os.path.join(tmp_dir, "outline.json")
            with open(outline_path, "w") as f:
                json.dump({"focus": focus, "question": body.question, "sections": detailed_sections, "total_sources": len(documents)}, f, ensure_ascii=False)
            logger.info("Research 2.1 outline saved: %s (%d sections)", outline_path, len(detailed_sections))

            # STEP C: Write each section (with clinical analysis + chart/table per section)
            med42_gen = get_med42_generator()
            section_texts = []
            previous_sections_summary = ""
            for sec_idx, sec_info in enumerate(detailed_sections):
                sec_title = sec_info.get("title", f"Sección {sec_idx+1}")
                sec_desc = sec_info.get("description", "")
                needs_clinical = sec_info.get("needs_clinical", False)
                needs_chart = sec_info.get("needs_chart", False)
                section_docs = _select_docs_for_section(
                    documents=documents,
                    section_title=sec_title,
                    section_desc=sec_desc,
                    focus=focus,
                    max_docs=16 if public_model_id == ACADEMIC_MODEL_ID_128K else 10,
                )
                local_to_global = {
                    i + 1: (documents.index(d) + 1)
                    for i, d in enumerate(section_docs)
                }
                yield sse_event({"type": "status", "message": f"Redactando ({sec_idx+1}/{len(detailed_sections)}): {sec_title}...", "model": public_model_id})
                yield emit_step("writing", f"Sección {sec_idx+1}/{len(detailed_sections)}: {sec_title}",
                    reasoning=f"Redactando «{sec_title}»"
                    + (f" — {sec_desc[:80]}" if sec_desc else "")
                    + (". Incluirá perspectiva clínica." if needs_clinical else "")
                    + (". Incluirá tabla/gráfica si los datos lo ameritan." if needs_chart else ""))

                # Per-section clinical analysis from Ominis Med (if flagged and Med42 available)
                clinical_hint = ""
                if needs_clinical and med42_gen:
                    try:
                        docs_summary = "\n".join(
                            f"[{i+1}] {d.meta.get('title','')}: {(d.content or '')[:400]}"
                            for i, d in enumerate(section_docs[:12])
                        )
                        clin_sys, clin_usr = build_section_analysis_prompt(sec_title, sec_desc, focus, docs_summary)
                        clin_msgs = [ChatMessage.from_system(clin_sys), ChatMessage.from_user(clin_usr)]
                        loop = asyncio.get_event_loop()
                        clin_result = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda m=clin_msgs: med42_gen.run(messages=m)),
                            timeout=60.0,
                        )
                        clinical_hint = (clin_result.get("replies", [{}])[0].text or "").strip() if clin_result.get("replies") else ""
                    except Exception as e:
                        logger.warning("Research 2.1 clinical hint for %s failed: %s", sec_title, e)

                # Build and run section generation
                # Use up to 2500 chars per doc for long-context model
                content_per_doc = 2500 if public_model_id == ACADEMIC_MODEL_ID_128K else 1500
                messages_sec = build_section_messages(
                    sec_title, section_docs, {"sections": [s["title"] for s in detailed_sections]},
                    body.question, focus, max_content_per_doc=content_per_doc,
                    previous_sections_summary=previous_sections_summary,
                    clinical_hint=clinical_hint,
                    section_description=sec_desc,
                    narrative_thread=narrative_thread,
                )
                section_timeout = 240.0 if sec_idx >= len(detailed_sections) - 2 else 180.0
                try:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda m=messages_sec, om=research_api_model: generator.run(
                                messages=m,
                                generation_kwargs=openai_chat_completion_generation_kwargs(
                                    om, temperature=0.3, num_predict=4096
                                ),
                            ),
                        ),
                        timeout=section_timeout,
                    )
                    replies = result.get("replies", [])
                    section_text = (replies[0].text or "").strip() if replies else ""
                except Exception as e:
                    logger.warning("Research 2.1 section %s failed: %s", sec_title, e)
                    raw = str(e)
                    hint = _openai_non_chat_model_user_message(raw) or raw
                    if len(hint) > 800:
                        hint = hint[:797] + "…"
                    section_text = f"\n## {sec_title}\n\n(Sección no generada por error: {hint})"

                section_text = _normalize_citation_markers(section_text, len(section_docs))

                # Remap local section citations [1]-[k] to global citations [1]-[N].
                def _remap_local_citation(m: re.Match) -> str:
                    idx = int(m.group(1))
                    global_idx = local_to_global.get(idx)
                    return f"[{global_idx}]" if global_idx else ""

                section_text = re.sub(r"\[(\d+)\]", _remap_local_citation, section_text)
                section_text = _strip_invalid_citations(section_text, len(documents))
                section_text = _dedupe_repeated_paragraphs(section_text)
                # Persist section to temp file
                sec_path = os.path.join(tmp_dir, f"section_{sec_idx:02d}.md")
                with open(sec_path, "w") as f:
                    f.write(section_text)
                # Persist per-section source chunks used by citations (for audit/debug)
                cited_nums = sorted(
                    set(int(m) for m in re.findall(r'\[(\d+)\]', section_text) if 1 <= int(m) <= len(documents))
                )
                sec_sources = []
                for n in cited_nums:
                    d = documents[n - 1]
                    sec_sources.append({
                        "ref_num": n,
                        "title": d.meta.get("title", "Sin título"),
                        "url": d.meta.get("url", ""),
                        "chunk_preview": (d.content or "")[:500],
                    })
                sec_sources_path = os.path.join(tmp_dir, f"section_{sec_idx:02d}_sources.json")
                with open(sec_sources_path, "w") as f:
                    json.dump(sec_sources, f, ensure_ascii=False)
                section_texts.append(section_text)
                sanitized = _sanitize_text(section_text)
                full_answer += sanitized + "\n\n"
                yield sse_event({"type": "chunk", "text": sanitized + "\n\n"})

                # Anti-repetition: if new section is too similar to previous summary, use delta summary for next section
                try:
                    embedder = manager.get_text_embedder()
                    sim = section_similarity_to_previous(section_text, previous_sections_summary, embedder, max_chars=2000)
                    if sim >= REPETITION_SIMILARITY_THRESHOLD:
                        previous_sections_summary = build_delta_summary(previous_sections_summary, section_text, max_length=2800)
                    else:
                        summary_line = f"«{sec_title}»: {section_text[:300].replace(chr(10), ' ')}..."
                        previous_sections_summary += summary_line + "\n"
                except Exception as e:
                    logger.warning("Research 2.1 section similarity/delta failed: %s", e)
                    summary_line = f"«{sec_title}»: {section_text[:300].replace(chr(10), ' ')}..."
                    previous_sections_summary += summary_line + "\n"

            # STEP D: Title + intro (small LLM call)
            yield sse_event({"type": "status", "message": "Generando título e introducción...", "model": public_model_id})
            combined = "\n\n".join(section_texts)
            intro_block = ""
            try:
                intro_user = (
                    "Se escribió el siguiente reporte de investigación por secciones. Tu tarea: escribe ÚNICAMENTE:\n"
                    "(1) Una línea con el título del reporte precedido de #\n"
                    "(2) Tres o cuatro párrafos de introducción que contextualicen el tema, "
                    "expliquen la importancia de la investigación y adelanten los hallazgos principales.\n"
                    "No incluyas el resto del reporte ni referencias.\n\n"
                    + (combined[:15000] if combined else "")
                )
                intro_messages = [
                    ChatMessage.from_system("Responde en español mexicano. Solo título e introducción. Nada más."),
                    ChatMessage.from_user(intro_user),
                ]
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda om=research_api_model: generator.run(
                            messages=intro_messages,
                            generation_kwargs=openai_chat_completion_generation_kwargs(
                                om, temperature=0.2, num_predict=1024
                            ),
                        ),
                    ),
                    timeout=60.0,
                )
                replies = result.get("replies", [])
                intro_block = (replies[0].text or "").strip() if replies else ""
                if intro_block:
                    intro_block = intro_block.strip() + "\n\n"
            except Exception as e:
                logger.warning("Research 2.1 title+intro failed: %s", e)

            # STEP E: References — only include actually-cited sources (APA-style when metadata available)
            cited_nums = set(int(m) for m in re.findall(r'\[(\d+)\]', combined) if int(m) >= 1 and int(m) <= len(documents))
            ref_lines = []
            for n in sorted(cited_nums):
                doc = documents[n - 1]
                meta = dict(doc.meta or {})
                if doc.content or meta.get("url"):
                    extracted = extract_reference_metadata(doc.content or "", meta.get("url", ""))
                    meta.update({k: v for k, v in extracted.items() if v and k not in ("url",)})
                if not meta.get("title"):
                    meta["title"] = "Sin título"
                if not meta.get("url"):
                    meta["url"] = ""
                ref_lines.append(format_apa_ref(meta, ref_num=n))
            references_block = "\n\n## Referencias\n\n" + "\n\n".join(ref_lines) if ref_lines else ""
            logger.info("Research 2.1 references: %d cited out of %d total documents", len(cited_nums), len(documents))

            full_doc = intro_block + combined + references_block
            full_doc = _normalize_citation_markers(full_doc, len(documents))
            full_doc = _strip_invalid_citations(full_doc, len(documents))
            full_doc = _dedupe_repeated_paragraphs(full_doc)
            full_answer = _sanitize_text(full_doc)
            yield sse_event({"type": "chunk", "text": full_answer})

            # Save final document to temp
            final_path = os.path.join(tmp_dir, "final_report.md")
            with open(final_path, "w") as f:
                f.write(full_answer)
            logger.info("Research 2.1 final report saved: %s (%d chars, %d sections)", final_path, len(full_answer), len(detailed_sections))
        else:
            ctx_budget = _research_context_token_budget(public_model_id)
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
                evidence_extracts=evidence_extracts if evidence_extracts else None,
                bias_audit=bias_audit if bias_audit else None,
                context_token_budget=ctx_budget,
            )

            if is_phase2:
                ctx_limit = ctx_budget
                input_tokens = _estimate_input_tokens_from_messages(messages)
                space_for_output = ctx_limit - input_tokens - OUTPUT_TOKEN_BUFFER
                max_tokens_cap = 8192 if public_model_id == ACADEMIC_MODEL_ID_128K else MAX_OUTPUT_TOKENS_CAP
                max_tokens = max(MIN_OUTPUT_TOKENS, min(max_tokens_cap, space_for_output))
                research_gen_kwargs = openai_chat_completion_generation_kwargs(
                    research_api_model, temperature=0.3, num_predict=max_tokens
                )
                logger.info("Research report: input_tokens≈%s, max_tokens=%s", input_tokens, max_tokens)
            else:
                research_gen_kwargs = openai_chat_completion_generation_kwargs(
                    research_api_model, temperature=0.3, num_predict=800
                )

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
                    logger.error(f"Research generation failed: {e}", exc_info=True)
                    raise
                finally:
                    chunk_queue.put_nowait(None)
                return result

            gen_task = asyncio.create_task(asyncio.wait_for(run_generator(), timeout=300.0))
            while True:
                try:
                    token = await asyncio.wait_for(chunk_queue.get(), timeout=310.0)
                except asyncio.TimeoutError:
                    gen_task.cancel()
                    try:
                        await gen_task
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass
                    yield sse_event({
                        "type": "error",
                        "message": "El servidor de investigación no respondió a tiempo. Intenta de nuevo o acota el alcance.",
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
                    "message": "El servidor de investigación no respondió a tiempo. Intenta de nuevo o acota el alcance.",
                })
                return
            except Exception as e:
                raw = str(e)
                msg = _openai_non_chat_model_user_message(raw) or f"Error al generar el reporte: {raw}"
                yield sse_event({"type": "error", "message": msg})
                return

        # Optional: Clinical Translator (Med42) — append implications when configured and phase 2
        # (Research 2.1 handles clinical per-section; only run global for non-2.1)
        if is_phase2 and not research_2_1 and full_answer and get_med42_generator():
            try:
                _med_gen = get_med42_generator()
                loop = asyncio.get_event_loop()
                clinical_section = await loop.run_in_executor(
                    None,
                    lambda: run_clinical_translator_sync(_med_gen, full_answer),
                )
                if clinical_section:
                    full_answer += "\n\n## Implicaciones clínicas (Med42)\n\n" + clinical_section
            except Exception as e:
                logger.warning("Med42 clinical translator failed: %s", e)

        full_answer = _normalize_citation_markers(full_answer, len(documents))
        full_answer = _strip_invalid_citations(full_answer, len(documents))
        full_answer = _dedupe_repeated_paragraphs(full_answer)
        sources_list, sources_not_used = _split_sources_by_citation(full_answer, all_sources_list)
        charts: list[dict] = []
        answer_for_client = full_answer
        quality_result = None
        if is_phase2 and documents:
            try:
                quality_result = post_generation_qa(full_answer, documents, max_docs=len(documents))
                yield sse_event({"type": "research_quality", "quality": quality_result})
            except Exception as qa_err:
                logger.warning("Research post-QA failed: %s", qa_err)
        try:
            chart_specs = parse_chart_specs_from_text(full_answer)
            if chart_specs:
                yield sse_event({"type": "status", "message": "Generando gráfica...", "model": public_model_id})
                charts = render_chart_images(chart_specs)
                answer_for_client = strip_chart_block_from_text(full_answer)
            # In research (phase2): only use charts embedded in the report; do not force chart generation
            if not charts and is_phase2:
                pass
            elif not charts:
                chart_specs = await generate_chart_specs(
                    question=body.question, answer=full_answer, documents=documents,
                    history=[msg.model_dump() for msg in body.history] if body.history else [],
                    generator=generator,
                )
                if chart_specs:
                    yield sse_event({"type": "status", "message": "Generando gráfica...", "model": public_model_id})
                charts = render_chart_images(chart_specs)
            if charts:
                yield sse_event({"type": "charts", "charts": charts})
        except Exception as e:
            logger.error(f"Chart generation error: {e}", exc_info=True)
        elapsed_ms = int((time.time() - start_time) * 1000)
        # Report title for PDF filename: prefer first # heading; if it's generic use sanitized question
        report_title = "Reporte OMINIS"
        for line in (answer_for_client or "").split("\n"):
            s = line.strip()
            if s.startswith("#"):
                report_title = s.lstrip("#").strip() or report_title
                break
        if is_phase2 and (not report_title or report_title == "Resumen ejecutivo"):
            # Use question-based title for PDF (e.g. "Salud Digital y Reforma LGS")
            raw = (body.question or "").strip()
            if raw:
                report_title = raw[:80].replace("\n", " ").strip() or report_title
        # Plan phase (not is_phase2): keep all plan sources so the user can check/uncheck; report phase: cited vs uncited
        done_sources = all_sources_list if not is_phase2 else sources_list
        payload = {
            "type": "done",
            "answer": answer_for_client,
            "sources": done_sources,
            "charts": charts if charts else None,
            "model": public_model_id,
            "elapsed_ms": elapsed_ms,
            "is_report": is_phase2,
            "report_title": report_title if is_phase2 else None,
        }
        if is_phase2 and sources_not_used:
            payload["sources_not_used"] = sources_not_used
        if ct_kw_research:
            payload["clinical_trials_keywords"] = ct_kw_research
        if quality_result is not None:
            payload["research_quality"] = quality_result
        if degradation_msg:
            payload["degradation"] = degradation_msg
        yield sse_event(payload)
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
        raw = str(e)
        msg = _openai_non_chat_model_user_message(raw) or raw
        yield sse_event({"type": "error", "message": msg})


def _should_use_research_21(body: ResearchRequest) -> bool:
    """True when Research 2.1 (deep multi-round + section-by-section) is requested and 128K is available."""
    use_21 = body.research_2_1 is True
    return bool(use_21 and _research_128k_available())


@router.post("/query-research-stream")
async def query_research_stream(
    body: ResearchRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Research mode streaming (OpenScholar 128K when configured, e.g. Vast.ai). Research 2.1 if enabled."""
    # Dashboard toggle: when public access is disabled, block anonymous visitors.
    public_access_enabled = True
    try:
        result = await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))
        row = result.scalar_one_or_none()
        public_access_enabled = bool(getattr(row, "public_access_enabled", True))
    except Exception as e:
        logger.warning("Could not read chat_defaults.public_access_enabled; defaulting to enabled: %s", e)

    if not public_access_enabled and user is None:
        async def blocked_events():
            yield sse_event({"type": "error", "message": "registration_required"})

        return StreamingResponse(
            blocked_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    events = _research_stream_events(body, research_2_1=_should_use_research_21(body), user=user)
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/academic_query-stream")
async def academic_query_stream(
    body: ResearchRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Modo Investigación (OpenScholar 128K). Requires login. Research 2.1 if enabled in options."""
    if user is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "model_not_allowed", "reason": "login_required"},
        )
    events = _research_stream_events(
        body,
        research_2_1=_should_use_research_21(body),
        user=user,
        db=db,
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Non-streaming endpoint ---

@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming query endpoint using Haystack OllamaChatGenerator."""
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    public_model_id = manager.get_public_model_id(model_id)
    # Dashboard toggle: when public access is disabled, block anonymous visitors.
    public_access_enabled = True
    try:
        result = await db.execute(select(ChatDefaults).where(ChatDefaults.id == 1))
        row = result.scalar_one_or_none()
        public_access_enabled = bool(getattr(row, "public_access_enabled", True))
    except Exception as e:
        logger.warning("Could not read chat_defaults.public_access_enabled; defaulting to enabled: %s", e)
    if not public_access_enabled and user is None:
        raise HTTPException(status_code=403, detail={"code": "registration_required", "reason": "login_required"})

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
    ct_allowed = user is not None
    raw_documents = await _gather_sources(
        question=body.question,
        rag_search=body.rag_search,
        web_search=body.web_search,
        pubmed_search=body.pubmed_search,
        openscholar_search=body.openscholar_search,
        num_sources=body.num_sources,
        manager=manager,
        clinical_trials_search=body.clinical_trials_search,
        ct_model_id=model_id if body.clinical_trials_search and ct_allowed else None,
        clinical_trials_allowed=ct_allowed,
        doctor_directory_search=body.doctor_directory_search,
        allcan_search=body.allcan_search,
        doctor_directory_allowed=ct_allowed,
        allcan_allowed=ct_allowed,
        db=db,
    )
    documents = _merge_sources_for_chat(
        raw_documents,
        max_total=8,
        prioritize_clinical_trials=bool(body.clinical_trials_search and ct_allowed),
    )

    # Build ChatMessages and generate; use per-model system prompt if set
    model_cfg = get_model_config(model_id)
    messages = build_chat_messages(
        question=body.question,
        documents=documents,
        history=[msg.model_dump() for msg in body.history] if body.history else [],
        image_description=image_description,
        file_context=body.file_context or "",
        system_prompt=getattr(model_cfg, "system_prompt", None) or None,
        extra_system_suffix=_tool_transparency_system_suffix(body),
    )

    generator = manager.get_generator(model_id)
    gen_result = generator.run(messages=messages)
    replies = gen_result.get("replies", [])
    answer = replies[0].text if replies else "No se pudo generar respuesta."

    all_sources = [
        _doc_to_source(doc) for doc in documents
        if doc.content and doc.meta.get("url")
    ]
    sources, sources_not_used = _split_sources_by_citation(answer, all_sources)
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
        sources_not_used=sources_not_used if sources_not_used else None,
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
    output_tokens: Optional[int] = None,
    tokens_per_second: Optional[float] = None,
):
    """Log a query to the database asynchronously (fire-and-forget)."""
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
                tokens_used=output_tokens,
                tokens_per_second=tokens_per_second,
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
