"""Semantic chunking: by headers, 400-600 tokens, 15% overlap. Outputs chunk records for health_chunks."""

import hashlib
import logging
import re
import uuid
from typing import Any

from pipeline import config as pipeline_config

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
MIN_TOKENS = 400
MAX_TOKENS = 600
OVERLAP_PCT = 0.15


def _approx_tokens(text: str) -> int:
    return max(0, len(text) // CHARS_PER_TOKEN)


def _split_by_headers(text: str) -> list[tuple[str, str]]:
    """Split text into (section_title, section_text)."""
    sections = []
    # Markdown-style headers and plain ALL CAPS lines as section breaks
    pattern = r"(?m)^(#{1,6}\s+.+?|(?:\n|^)([A-Z][A-Z\s]{8,}):?)\s*$"
    parts = re.split(pattern, text)
    current_title = "Contenido"
    current_text = []
    for i, part in enumerate(parts):
        if part is None or part == "":
            continue
        stripped = part.strip()
        if re.match(r"^#{1,6}\s+", stripped) or (len(stripped) > 8 and stripped.isupper() and " " in stripped):
            if current_text:
                sections.append((current_title, "\n".join(current_text)))
            current_title = stripped.lstrip("# ").strip()[:200]
            current_text = []
        else:
            current_text.append(part)
    if current_text:
        sections.append((current_title, "\n".join(current_text)))
    if not sections:
        sections.append(("Contenido", text))
    return sections


def _chunk_section(section_title: str, section_text: str, doc_id: str, meta: dict) -> list[dict[str, Any]]:
    """Split section into chunks of MAX_TOKENS with OVERLAP_PCT overlap."""
    chunks_out = []
    min_tok = pipeline_config.CHUNK_MIN_TOKENS if hasattr(pipeline_config, "CHUNK_MIN_TOKENS") else MIN_TOKENS
    max_tok = pipeline_config.CHUNK_MAX_TOKENS if hasattr(pipeline_config, "CHUNK_MAX_TOKENS") else MAX_TOKENS
    overlap_pct = pipeline_config.CHUNK_OVERLAP_PCT if hasattr(pipeline_config, "CHUNK_OVERLAP_PCT") else OVERLAP_PCT
    overlap_chars = int(max_tok * CHARS_PER_TOKEN * overlap_pct)
    start = 0
    text = section_text.strip()
    if not text:
        return []
    while start < len(text):
        end = min(start + max_tok * CHARS_PER_TOKEN, len(text))
        chunk_text = text[start:end]
        if end < len(text):
            # Try to break at sentence or newline
            last_break = max(
                chunk_text.rfind(". "),
                chunk_text.rfind("\n"),
                chunk_text.rfind("; "),
            )
            if last_break > (min_tok * CHARS_PER_TOKEN):
                end = start + last_break + 1
                chunk_text = text[start:end]
        chunk_text = chunk_text.strip()
        if _approx_tokens(chunk_text) < min_tok and start + len(chunk_text) < len(text):
            # Extend to reach min_tok
            extra = (min_tok * CHARS_PER_TOKEN) - len(chunk_text)
            end = min(start + len(chunk_text) + extra, len(text))
            chunk_text = text[start:end].strip()
        if not chunk_text:
            break
        chunk_id = str(uuid.uuid4())
        token_count = _approx_tokens(chunk_text)
        chunks_out.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "section": section_title,
            "chunk_text": chunk_text,
            "token_count": token_count,
            **meta,
        })
        start = end - overlap_chars
        if start >= len(text):
            break
    return chunks_out


def semantic_chunk_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn normalized docs (with doc_id, raw_text, title, institution, etc.) into chunk records."""
    all_chunks = []
    for doc in docs:
        doc_id = doc.get("doc_id")
        raw = (doc.get("raw_text") or "").strip()
        if not raw:
            continue
        title = (doc.get("title") or "")[:500]
        meta = {
            "title": title,
            "disease": "",
            "institution": (doc.get("institution") or "")[:256],
            "state": (doc.get("state") or "")[:64],
            "year": doc.get("year"),
            "document_type": (doc.get("document_type") or "")[:64],
            "country": (doc.get("country") or "")[:64],
            "evidence_level": "",
            "classifier_tag": "mexicano_directo" if (doc.get("country") or "").lower() in ("méxico", "mexico") else "internacional",
        }
        sections = _split_by_headers(raw)
        for section_title, section_text in sections:
            all_chunks.extend(_chunk_section(section_title, section_text, doc_id, meta))
    logger.info("Chunked %d docs into %d chunks", len(docs), len(all_chunks))
    return all_chunks
