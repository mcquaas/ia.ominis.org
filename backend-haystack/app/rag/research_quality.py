"""
Research quality module: re-ranking, academic quality scoring, reference metadata,
anti-repetition checks, and post-generation QA for the deep research pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from haystack import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-ranking (FlagEmbedding cross-encoder)
# ---------------------------------------------------------------------------

_reranker = None


def get_reranker():
    """Lazy-load FlagReranker for semantic re-ranking. Returns None if unavailable."""
    global _reranker
    if _reranker is not None:
        return _reranker
    try:
        from FlagEmbedding import FlagReranker
        try:
            _reranker = FlagReranker(model="BAAI/bge-reranker-v2-m3", use_fp16=True)
        except Exception:
            _reranker = FlagReranker(model="BAAI/bge-reranker-base", use_fp16=True)
        logger.info("Research quality: FlagReranker loaded")
        return _reranker
    except Exception as e:
        logger.warning("Research quality: FlagReranker not available: %s", e)
        return None


def rerank_documents(
    query: str,
    documents: list[Document],
    top_k: int = 20,
    max_content_len: int = 800,
) -> list[Document]:
    """
    Re-rank documents by query-document relevance using a cross-encoder.
    Returns top_k documents in relevance order. If reranker is unavailable, returns original order.
    """
    if not query or not documents:
        return documents[:top_k]
    reranker = get_reranker()
    if reranker is None:
        return documents[:top_k]
    try:
        pairs = []
        for d in documents:
            content = (d.content or "")[:max_content_len].replace("\n", " ")
            pairs.append((query, content))
        scores = reranker.compute_score(pairs)
        if isinstance(scores, (int, float)):
            scores = [scores]
        indexed = list(zip(documents, scores, strict=False))
        indexed.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in indexed[:top_k]]
    except Exception as e:
        logger.warning("Re-ranking failed: %s", e)
        return documents[:top_k]


# ---------------------------------------------------------------------------
# Academic quality scoring (evidence level, DOI, year, peer-reviewed)
# ---------------------------------------------------------------------------

# Evidence level weights: higher = prefer for scientific reports
EVIDENCE_LEVEL_SCORE = {
    "systematic_review": 1.0,
    "metaanalysis": 0.95,
    "rct": 0.9,
    "clinical_trial": 0.85,
    "guideline": 0.85,
    "observational": 0.7,
    "peer_reviewed": 0.8,
    "article": 0.65,
    "report": 0.6,
    "webpage": 0.4,
    "rag": 0.6,
    "pubmed": 0.75,
    "openscholar": 0.8,
    "health_datastore": 0.7,
}


def academic_quality_score(doc: Document) -> float:
    """
    Compute a 0–1 score for academic/scientific quality using meta and content hints.
    """
    score = 0.5
    meta = doc.meta or {}
    source_type = (meta.get("source_type") or "web").lower()
    score += EVIDENCE_LEVEL_SCORE.get(source_type, 0.4) * 0.25

    if meta.get("doi"):
        score += 0.15
    if meta.get("year"):
        try:
            y = int(str(meta["year"])[:4])
            if 2018 <= y <= 2030:
                score += 0.1
            elif 2010 <= y < 2018:
                score += 0.05
        except (ValueError, TypeError):
            pass
    if meta.get("journal") or meta.get("citation"):
        score += 0.05
    if meta.get("authors"):
        score += 0.05

    url = (meta.get("url") or "").lower()
    if "pubmed" in url or "ncbi" in url or "pmc" in url:
        score += 0.1
    if "sciencedirect" in url or "nature.com" in url or "thelancet" in url or "bmj" in url:
        score += 0.1
    if ".gob.mx" in url or "who.int" in url or "paho" in url:
        score += 0.05

    content = (doc.content or "")[:500].lower()
    if "systematic review" in content or "meta-analysis" in content or "meta-análisis" in content:
        score += 0.08
    if "randomized" in content or "ensayo clínico" in content or "rct" in content:
        score += 0.05
    return min(1.0, score)


def _is_trustworthy_domain(url: str) -> bool:
    domain = url.lower()
    trusted = (
        ".gob.mx", ".gov", ".edu", "who.int", "paho.org", "nih.gov",
        "ncbi.nlm.nih.gov", "pubmed", "sciencedirect", "nature.com",
        "thelancet", "bmj.com", "cochrane",
    )
    return any(d in domain for d in trusted)


def deduplicate_and_rank_with_quality(
    documents: list[Document],
    query: str,
    max_total: int,
    *,
    url_normalize: bool = True,
    use_quality_score: bool = True,
    rerank_if_available: bool = True,
) -> list[Document]:
    """
    Deduplicate by URL (keep longest content), then rank by:
    1) optional cross-encoder re-ranking vs query,
    2) academic quality score,
    3) source type priority and trusted domain.
    """
    from urllib.parse import urlparse
    url_best: dict[str, Document] = {}
    for doc in documents:
        url = doc.meta.get("url", "")
        if not url or not doc.content:
            continue
        if url_normalize:
            normalized = urlparse(url)._replace(fragment="").geturl().rstrip("/")
        else:
            normalized = url
        existing = url_best.get(normalized)
        if existing is None:
            url_best[normalized] = doc
        else:
            if len(doc.content or "") > len(existing.content or ""):
                url_best[normalized] = doc
    unique = list(url_best.values())

    if rerank_if_available and query and len(unique) > 1:
        unique = rerank_documents(query, unique, top_k=max_total * 2, max_content_len=600)

    if use_quality_score:
        # Order of importance: 1 Ominis (rag), 2 OpenScholar, 3 PubMed, 4 Web
        def sort_key(d: Document) -> tuple:
            q = academic_quality_score(d)
            st = d.meta.get("source_type", "web")
            type_priority = {"rag": 0, "health_datastore": 0, "openscholar": 1, "pubmed": 2, "web": 3, "webpage": 3}.get(st, 3)
            trusted = 0 if _is_trustworthy_domain(d.meta.get("url", "") or "") else 1
            return (trusted, type_priority, -q)
    else:
        def sort_key(d: Document) -> tuple:
            st = d.meta.get("source_type", "web")
            type_priority = {"rag": 0, "health_datastore": 0, "openscholar": 1, "pubmed": 2, "web": 3, "webpage": 3}.get(st, 3)
            return (type_priority, -(d.score or 0))
    unique.sort(key=sort_key)
    return unique[:max_total]


# ---------------------------------------------------------------------------
# Reference metadata extraction and APA/BibTeX
# ---------------------------------------------------------------------------

def extract_reference_metadata(text: str, url: str = "") -> dict[str, Any]:
    """
    Extract DOI, authors, title, journal, year from text/HTML snippet.
    """
    meta: dict[str, Any] = {}
    if not text:
        return meta
    text_lower = text[:12000]
    doi_m = re.search(r"10\.\d{4,}/[^\s\]\)<>]+", text_lower)
    if doi_m:
        meta["doi"] = doi_m.group(0).rstrip(".,;")
    year_m = re.search(r"\b(19[89]\d|20[0-2]\d)\b", text_lower)
    if year_m:
        meta["year"] = year_m.group(1)
    if "<" in text_lower and ">" in text_lower:
        key_map = {
            "citation_title": "title",
            "citation_author": "authors",
            "citation_journal": "journal",
            "citation_doi": "doi",
            "citation_publication_date": "year",
        }
        for name, pat in (
            ("citation_title", r'citation_title["\']?\s*content=["\']([^"\']+)'),
            ("citation_author", r'citation_author["\']?\s*content=["\']([^"\']+)'),
            ("citation_journal", r'citation_journal["\']?\s*content=["\']([^"\']+)'),
            ("citation_doi", r'citation_doi["\']?\s*content=["\']([^"\']+)'),
            ("citation_publication_date", r'citation_publication_date["\']?\s*content=["\']([^"\']+)'),
        ):
            m = re.search(pat, text_lower, re.I)
            if m:
                val = m.group(1).strip()
                key = key_map.get(name, name.replace("citation_", ""))
                if name == "citation_publication_date" and len(val) >= 4:
                    meta["year"] = val[:4]
                elif name == "citation_doi":
                    meta["doi"] = val
                else:
                    meta[key] = val
    if url:
        meta["url"] = url
    return meta


def format_apa(meta: dict[str, Any], ref_num: Optional[int] = None) -> str:
    """Format a single reference in APA-like style."""
    parts = []
    authors = meta.get("authors") or meta.get("citation_author") or ""
    title = meta.get("title") or meta.get("citation_title") or "Sin título"
    journal = meta.get("journal") or meta.get("citation_journal") or ""
    year = str(meta.get("year") or "")[:4] if meta.get("year") else ""
    doi = meta.get("doi") or ""
    url = meta.get("url") or ""

    if ref_num is not None:
        parts.append(f"[{ref_num}]")
    if authors:
        parts.append(f"{authors}.")
    parts.append(f"*{title}*.")
    if journal:
        parts.append(f"*{journal}*.")
    if year:
        parts.append(f"({year}).")
    if doi:
        parts.append(f"https://doi.org/{doi}")
    elif url:
        parts.append(url)
    return " ".join(p for p in parts if p).strip()


def format_bibtex(meta: dict[str, Any], key: str = "ref") -> str:
    """Format a single reference in BibTeX (optional)."""
    authors = meta.get("authors") or meta.get("citation_author") or "Unknown"
    title = meta.get("title") or meta.get("citation_title") or "No title"
    journal = meta.get("journal") or meta.get("citation_journal") or ""
    year = str(meta.get("year") or "")[:4] if meta.get("year") else ""
    doi = meta.get("doi") or ""
    url = meta.get("url") or ""
    entry = f"@article{{{key},\n  author = {{{authors}}},\n  title = {{{title}}},\n"
    if journal:
        entry += f"  journal = {{{journal}}},\n"
    if year:
        entry += f"  year = {{{year}}},\n"
    if doi:
        entry += f"  doi = {{{doi}}},\n"
    if url:
        entry += f"  url = {{{url}}},\n"
    entry += "}"
    return entry


# ---------------------------------------------------------------------------
# Anti-repetition: similarity of new section vs previous content
# ---------------------------------------------------------------------------

def section_similarity_to_previous(
    new_section_text: str,
    previous_sections_summary: str,
    text_embedder,
    max_chars: int = 2000,
) -> float:
    """Return cosine similarity (0–1) between new section and previous sections summary."""
    if not new_section_text or not previous_sections_summary or not text_embedder:
        return 0.0
    try:
        a = (new_section_text or "")[:max_chars].replace("\n", " ")
        b = (previous_sections_summary or "")[:max_chars].replace("\n", " ")
        if not a.strip() or not b.strip():
            return 0.0
        out_a = text_embedder.run(text=a)
        out_b = text_embedder.run(text=b)
        emb_a = out_a.get("embedding") or (out_a.get("embeddings") or [None])[0]
        emb_b = out_b.get("embedding") or (out_b.get("embeddings") or [None])[0]
        if not emb_a or not emb_b:
            return 0.0
        import math
        dot = sum(x * y for x, y in zip(emb_a, emb_b, strict=True))
        na = math.sqrt(sum(x * x for x in emb_a))
        nb = math.sqrt(sum(x * x for x in emb_b))
        if na * nb == 0:
            return 0.0
        sim = dot / (na * nb)
        return max(0.0, min(1.0, (sim + 1) / 2))
    except Exception as e:
        logger.warning("Section similarity check failed: %s", e)
        return 0.0


REPETITION_SIMILARITY_THRESHOLD = 0.72


def build_delta_summary(previous_sections_summary: str, new_section_text: str, max_length: int = 2800) -> str:
    """Delta summarization: append short summary of new section to avoid repetition context bloat."""
    if not new_section_text:
        return previous_sections_summary or ""
    first_line = new_section_text.strip().split("\n")[0][:200].strip()
    delta_line = f"Nueva sección añadida (resumen): {first_line}..."
    combined = (previous_sections_summary or "").strip() + "\n" + delta_line
    return combined[:max_length].strip()


# ---------------------------------------------------------------------------
# Post-generation QA
# ---------------------------------------------------------------------------

def post_generation_qa(
    report_text: str,
    documents: list[Document],
    max_docs: int = 50,
) -> dict[str, Any]:
    """Evaluate report quality: citation integrity, coverage. Returns score, alerts, cited_indices."""
    cited = set()
    for m in re.finditer(r"\[(\d+)\]", report_text):
        n = int(m.group(1))
        if 1 <= n <= max_docs:
            cited.add(n)
    num_citations = len(cited)
    total_docs = len(documents)
    alerts = []
    score = 0.8

    if total_docs == 0:
        score = 0.3
        alerts.append("No hay fuentes en el reporte.")
    else:
        if num_citations == 0:
            score = min(score, 0.4)
            alerts.append("El reporte no contiene citas [N].")
        else:
            coverage = num_citations / min(total_docs, 25)
            if coverage >= 0.5:
                score += 0.1
            if coverage < 0.2:
                alerts.append("Pocas fuentes citadas respecto al total disponible.")
        if total_docs > 5 and num_citations < 3:
            alerts.append("Se recomienda citar más fuentes para un reporte científico.")
    if len(report_text) < 500:
        score = min(score, 0.6)
        alerts.append("El reporte es muy breve.")
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 2),
        "alerts": alerts,
        "cited_count": num_citations,
        "total_sources": total_docs,
        "cited_indices": list(cited),
    }
