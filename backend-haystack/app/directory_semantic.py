"""
Semantic + accent-insensitive helpers for Doctor Directory (Postgres) and All.Can (Strapi).

Uses multilingual sentence-transformers (default: paraphrase-multilingual-MiniLM-L12-v2) or,
when EMBEDDING_SERVICE_URL is set, the same external /embed API as the RAG pipeline.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from typing import Any

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)


def fold_accents(s: str) -> str:
    """Lowercase ASCII-ish fold: México -> mexico (for extra LIKE patterns)."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def like_patterns_for_token(token: str) -> list[str]:
    """Patterns for SQL ILIKE: raw lower + accent-folded variant."""
    t = token.strip().lower()
    if len(t) < 1:
        return []
    folded = fold_accents(t)
    out = [f"%{t}%"]
    if folded != t:
        out.append(f"%{folded}%")
    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def tokenize_query(q: str) -> list[str]:
    """Split on whitespace; keep tokens length >= 2."""
    return [w for w in re.split(r"\s+", (q or "").strip()) if len(w) >= 2]


@lru_cache(maxsize=1)
def _sentence_transformer_model():
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    name = (getattr(settings, "directory_semantic_embedding_model", None) or "").strip() or (
        "paraphrase-multilingual-MiniLM-L12-v2"
    )
    logger.info("Loading directory semantic embedding model: %s", name)
    return SentenceTransformer(name)


def embed_texts_semantic(texts: list[str]) -> list[list[float]]:
    """Embed texts; returns L2-normalized vectors as lists (cosine = dot product)."""
    if not texts:
        return []
    settings = get_settings()
    if (settings.embedding_service_url or "").strip():
        from app.rag.embedder import _embed_batch

        vecs = _embed_batch(texts)
        out: list[list[float]] = []
        for v in vecs:
            arr = np.array(v, dtype=np.float32)
            n = np.linalg.norm(arr)
            if n > 0:
                arr = arr / n
            out.append(arr.tolist())
        return out
    model = _sentence_transformer_model()
    arr = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return [row.astype(np.float32).tolist() for row in arr]


def semantic_rank_by_query(
    query_text: str,
    doc_texts: list[str],
    top_k: int,
) -> list[tuple[int, float]]:
    """
    Returns list of (index, score) sorted by descending cosine similarity.
    """
    if not doc_texts:
        return []
    qt = (query_text or "").strip()
    if not qt:
        return [(i, 0.0) for i in range(min(len(doc_texts), top_k))]
    qv = embed_texts_semantic([qt])[0]
    dv = embed_texts_semantic(doc_texts)
    q = np.array(qv, dtype=np.float32)
    m = np.array(dv, dtype=np.float32)
    scores = m @ q
    order = np.argsort(-scores)
    out: list[tuple[int, float]] = []
    for idx in order[:top_k]:
        ii = int(idx)
        out.append((ii, float(scores[ii])))
    return out


def doctor_search_blob(p: Any) -> str:
    """Single string for embedding (doctor profile)."""
    parts: list[str] = [p.display_name or "", p.specialty_label or ""]
    sj = getattr(p, "specialties_json", None)
    if sj and isinstance(sj, list):
        parts.append(" ".join(str(x) for x in sj[:30]))
    if getattr(p, "locality", None):
        parts.append(str(p.locality))
    if getattr(p, "region", None):
        parts.append(str(p.region))
    if getattr(p, "description", None):
        parts.append(str(p.description)[:2500])
    sv = getattr(p, "services_json", None)
    if sv and isinstance(sv, list):
        parts.append(" ".join(str(x) for x in sv[:50]))
    return " ".join(x for x in parts if x).strip() or (p.display_name or "doctor")


def allcan_org_blob(row: dict[str, Any]) -> str:
    """Single string for embedding (All.Can organization)."""
    parts: list[str] = []
    for key in ("name", "type", "specialty", "state", "city", "address", "description"):
        v = row.get(key)
        if v:
            parts.append(str(v))
    return " ".join(parts).strip() or str(row.get("name") or "organization")


def build_doctor_query_text(q: str, specialty: str, city: str) -> str:
    bits = [x.strip() for x in [q, specialty, city] if x and x.strip()]
    return ". ".join(bits) if bits else "medical doctor directory Mexico"


def build_allcan_query_text(q: str, type_: str, state: str, specialty: str, city: str) -> str:
    bits = [x.strip() for x in [q, type_, state, specialty, city] if x and x.strip()]
    return ". ".join(bits) if bits else "cancer patient organization Mexico All.Can"


def allcan_row_matches_filters(
    row: dict[str, Any],
    q: str,
    org_type: str,
    state: str,
    specialty: str,
    city: str,
) -> bool:
    """Accent-folded substring checks for All.Can rows (shared with API + RAG)."""

    def _has(hay: str, needle: str) -> bool:
        if not needle.strip():
            return True
        h = fold_accents(hay or "")
        n = fold_accents(needle.strip())
        return n in h

    def blob(r: dict[str, Any]) -> str:
        parts = [
            str(r.get("name") or ""),
            str(r.get("type") or ""),
            str(r.get("specialty") or ""),
            str(r.get("state") or ""),
            str(r.get("city") or ""),
            str(r.get("address") or ""),
            str(r.get("description") or ""),
        ]
        return " ".join(parts)

    if org_type.strip() and not _has(str(row.get("type") or ""), org_type):
        return False
    if state.strip() and not _has(str(row.get("state") or ""), state):
        return False
    if specialty.strip() and not _has(str(row.get("specialty") or ""), specialty):
        return False
    if city.strip() and not (
        _has(str(row.get("city") or ""), city) or _has(str(row.get("address") or ""), city)
    ):
        return False
    if q.strip() and not _has(blob(row), q):
        return False
    return True


def build_doctor_lexical_clause(
    q: str,
    specialty: str,
    city: str,
    match_mode: str,
):
    """
    Build SQLAlchemy filter for doctor directory: lexical match with accent-folded LIKE patterns.
    Returns None if no filters; otherwise a combined clause.
    """
    from sqlalchemy import and_, cast, func, or_, String

    from app.doctor_directory.models import DoctorDirectoryProfile

    fields = [
        DoctorDirectoryProfile.display_name,
        DoctorDirectoryProfile.description,
        DoctorDirectoryProfile.specialty_label,
        DoctorDirectoryProfile.locality,
        DoctorDirectoryProfile.region,
        cast(DoctorDirectoryProfile.services_json, String),
    ]

    def lower_like(field, pat: str):
        return func.lower(field).like(pat)

    parts: list = []

    if (q or "").strip():
        words = tokenize_query(q)
        if not words:
            words = [q.strip()]
        word_clauses = []
        for w in words:
            patts = like_patterns_for_token(w)
            if not patts:
                continue
            word_clauses.append(
                or_(*[lower_like(f, p) for f in fields for p in patts]),
            )
        if word_clauses:
            parts.append(and_(*word_clauses) if len(word_clauses) > 1 else word_clauses[0])

    if (specialty or "").strip():
        st = specialty.strip()
        patts = like_patterns_for_token(st)
        if patts:
            parts.append(or_(*[lower_like(DoctorDirectoryProfile.specialty_label, p) for p in patts]))

    if (city or "").strip():
        ct = city.strip()
        patts = like_patterns_for_token(ct)
        if patts:
            loc = [lower_like(DoctorDirectoryProfile.locality, p) for p in patts]
            reg = [lower_like(DoctorDirectoryProfile.region, p) for p in patts]
            parts.append(or_(*(loc + reg)))

    if not parts:
        return None
    if match_mode == "or" and len(parts) > 1:
        return or_(*parts)
    return and_(*parts)
