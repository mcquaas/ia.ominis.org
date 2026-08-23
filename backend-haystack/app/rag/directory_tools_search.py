"""Doctor directory (Postgres) and All.Can organizations (Strapi) as supplementary RAG sources."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from haystack import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.allcan_directory.strapi_client import fetch_organizations_all_pages
from app.config import get_settings
from app.directory_semantic import (
    allcan_org_blob,
    allcan_row_matches_filters,
    build_doctor_lexical_clause,
    build_doctor_query_text,
    doctor_search_blob,
    semantic_rank_by_query,
)
from app.doctor_directory.models import DoctorDirectoryProfile

logger = logging.getLogger(__name__)


def _doctor_profile_to_document(p: DoctorDirectoryProfile, semantic_score: float | None = None) -> Document:
    lines = [
        f"Nombre: {p.display_name}",
        f"Especialidad: {p.specialty_label or '—'}",
    ]
    if p.locality or p.region:
        lines.append(f"Ubicación: {', '.join(x for x in [p.locality, p.region] if x)}")
    if p.description:
        lines.append(f"Descripción: {(p.description or '')[:1200]}")
    if p.street_address:
        lines.append(f"Dirección: {p.street_address}")
    content = "\n".join(lines)
    title = f"{p.display_name} — {p.specialty_label or 'Directorio médico (México)'}"
    sc = 0.72 if semantic_score is None else float(max(0.35, min(0.95, 0.45 + 0.45 * float(semantic_score))))
    return Document(
        content=content,
        meta={
            "title": title,
            "url": p.profile_url,
            "source_type": "directorio_mx",
        },
        score=sc,
    )


async def fetch_doctor_directory_documents(
    db: AsyncSession,
    question: str,
    max_results: int = 16,
) -> list[Document]:
    q = (question or "").strip()[:400]
    if not q:
        return []
    filt = build_doctor_lexical_clause(q, "", "", "and")
    stmt = select(DoctorDirectoryProfile)
    if filt is not None:
        stmt = stmt.where(filt)
    settings = get_settings()
    cap = int(getattr(settings, "directory_semantic_max_candidates", 600) or 600)
    broad_lim = int(getattr(settings, "directory_semantic_broad_fallback_limit", 2000) or 2000)
    stmt = stmt.order_by(DoctorDirectoryProfile.id.asc()).limit(cap)
    rows = (await db.execute(stmt)).scalars().all()
    if len(rows) < 80:
        broad_stmt = select(DoctorDirectoryProfile).order_by(DoctorDirectoryProfile.id.asc()).limit(broad_lim)
        rows2 = (await db.execute(broad_stmt)).scalars().all()
        seen = {r.id for r in rows}
        for r in rows2:
            if r.id not in seen:
                seen.add(r.id)
                rows.append(r)
    blobs = [doctor_search_blob(p) for p in rows]
    qtext = build_doctor_query_text(q, "", "")
    try:
        ranked = await asyncio.to_thread(semantic_rank_by_query, qtext, blobs, max_results)
    except Exception as e:
        logger.warning("Doctor directory RAG semantic failed: %s", e)
        return [_doctor_profile_to_document(p) for p in rows[:max_results]]
    out: list[Document] = []
    for idx, sc in ranked:
        if idx >= len(rows):
            continue
        out.append(_doctor_profile_to_document(rows[idx], semantic_score=sc))
    return out


def _org_to_document(row: dict[str, Any], semantic_score: float | None = None) -> Document | None:
    name = (row.get("name") or "").strip()
    if not name:
        return None
    oid = row.get("id")
    parts = [f"Organización: {name}"]
    for label, key in (
        ("Tipo", "type"),
        ("Especialidad", "specialty"),
        ("Estado", "state"),
        ("Ciudad", "city"),
        ("Dirección", "address"),
    ):
        v = row.get(key)
        if v:
            parts.append(f"{label}: {v}")
    if row.get("description"):
        parts.append(f"Descripción: {str(row.get('description'))[:800]}")
    if row.get("phone"):
        parts.append(f"Teléfono: {row.get('phone')}")
    content = "\n".join(parts)
    url = (row.get("url") or "").strip()
    if not url:
        url = f"https://www.allcan.mx/mapa-interactivo-all-can#{oid or name}"
    title = f"{name} — All.Can México"
    sc = 0.7 if semantic_score is None else float(max(0.35, min(0.95, 0.45 + 0.45 * float(semantic_score))))
    return Document(
        content=content,
        meta={
            "title": title,
            "url": url,
            "source_type": "allcan",
            "allcan_id": oid,
        },
        score=sc,
    )


async def fetch_allcan_documents(question: str, max_results: int = 24) -> list[Document]:
    settings = get_settings()
    base = (getattr(settings, "allcan_strapi_url", None) or "").strip().rstrip("/")
    token = (getattr(settings, "allcan_strapi_api_token", None) or "").strip()
    if not base or not token:
        return []
    q = (question or "").strip()[:200]
    if not q:
        return []
    try:
        rows = await fetch_organizations_all_pages(base, token, max_rows=500)
    except Exception as e:
        logger.warning("All.Can fetch error: %s", e)
        return []
    filtered = [r for r in rows if allcan_row_matches_filters(r, q, "", "", "", "")]
    pool = filtered if filtered else rows[: min(200, len(rows))]
    blobs = [allcan_org_blob(r) for r in pool]
    try:
        ranked = await asyncio.to_thread(semantic_rank_by_query, q, blobs, max_results)
    except Exception as e:
        logger.warning("All.Can RAG semantic failed: %s", e)
        out: list[Document] = []
        for r in pool[:max_results]:
            doc = _org_to_document(r)
            if doc:
                out.append(doc)
        return out
    out: list[Document] = []
    for idx, sc in ranked:
        if idx >= len(pool):
            continue
        doc = _org_to_document(pool[idx], semantic_score=sc)
        if doc:
            out.append(doc)
    return out[:max_results]
