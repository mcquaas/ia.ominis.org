"""Admin: start scrape, list runs. Authenticated users: search ingested doctors."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from sqlalchemy import func, select, text

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import RoleEnum, User
from app.database import get_db
from app.doctor_directory.csv_export import profiles_to_csv_bytes
from app.doctor_directory.models import DoctorDirectoryProfile, DoctorDirectoryScrapeRun, DoctorScrapeStatus
from app.doctor_directory.doctoralia import SOURCE_SITE as DOCTORALIA_SITE
from app.doctor_directory.doctoranytime import SOURCE_SITE as DOCTORANYTIME_SITE
from app.doctor_directory.service import run_source_scrape
from app.doctor_directory.topdoctors import SOURCE_SITE as TOPDOCTORS_SITE
from app.config import get_settings
from app.directory_semantic import (
    build_doctor_lexical_clause,
    build_doctor_query_text,
    doctor_search_blob,
    semantic_rank_by_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["doctor-directory"])


class DoctorScrapeStartRequest(BaseModel):
    source: str = Field(
        default="topdoctors_mx",
        description="topdoctors_mx | doctoralia_mx | doctoranytime_mx",
    )
    max_profiles: int = Field(default=50, ge=1, le=5000)
    delay_seconds: float = Field(default=0.6, ge=0.0, le=30.0)


class DoctorScrapeStartResponse(BaseModel):
    run_id: int
    message: str


class ScrapeRunOut(BaseModel):
    id: int
    source_site: str
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    max_profiles: int
    profiles_attempted: int
    profiles_upserted: int
    profiles_failed: int
    error_message: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class SourceAppearanceOut(BaseModel):
    source_site: str
    profile_slug: str
    profile_url: str
    last_scraped_at: Optional[str]
    scrape_run_id: Optional[int]
    rating_value: Optional[float]
    rating_count: Optional[int]


class DoctorProfileOut(BaseModel):
    id: int
    source_site: str
    profile_url: str
    source_appearances: list[SourceAppearanceOut] = Field(default_factory=list)
    display_name: str
    specialty_label: Optional[str]
    specialties_json: Optional[list]
    description: Optional[str]
    image_url: Optional[str]
    street_address: Optional[str]
    locality: Optional[str]
    region: Optional[str]
    postal_code: Optional[str]
    country_code: Optional[str]
    services_json: Optional[list]
    phones_json: Optional[list]
    emails_json: Optional[list]
    external_reviews_json: Optional[list]
    rating_value: Optional[float]
    rating_count: Optional[int]
    rating_best: Optional[float]
    rating_worst: Optional[float]
    last_scraped_at: str
    scrape_run_id: Optional[int]

    class Config:
        from_attributes = True


class DoctorSearchResponse(BaseModel):
    total: int
    results: list[DoctorProfileOut]
    disclaimer: str


class DoctorDirectoryStatsOut(BaseModel):
    total_profiles: int
    by_source: dict[str, int]
    last_scraped_at: Optional[str]


def _run_to_out(r: DoctorDirectoryScrapeRun) -> ScrapeRunOut:
    return ScrapeRunOut(
        id=r.id,
        source_site=r.source_site,
        status=r.status.value if isinstance(r.status, DoctorScrapeStatus) else str(r.status),
        started_at=r.started_at.isoformat() if r.started_at else None,
        finished_at=r.finished_at.isoformat() if r.finished_at else None,
        max_profiles=r.max_profiles,
        profiles_attempted=r.profiles_attempted,
        profiles_upserted=r.profiles_upserted,
        profiles_failed=r.profiles_failed,
        error_message=r.error_message,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )


def _appearances_to_out(raw) -> list[SourceAppearanceOut]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else []
    out: list[SourceAppearanceOut] = []
    for a in items:
        if not isinstance(a, dict):
            continue
        out.append(
            SourceAppearanceOut(
                source_site=str(a.get("source_site") or ""),
                profile_slug=str(a.get("profile_slug") or ""),
                profile_url=str(a.get("profile_url") or ""),
                last_scraped_at=a.get("last_scraped_at"),
                scrape_run_id=a.get("scrape_run_id"),
                rating_value=a.get("rating_value"),
                rating_count=a.get("rating_count"),
            )
        )
    return out


def _profile_to_out(p: DoctorDirectoryProfile) -> DoctorProfileOut:
    return DoctorProfileOut(
        id=p.id,
        source_site=p.source_site,
        profile_url=p.profile_url,
        source_appearances=_appearances_to_out(p.source_appearances),
        display_name=p.display_name,
        specialty_label=p.specialty_label,
        specialties_json=p.specialties_json,
        description=p.description,
        image_url=p.image_url,
        street_address=p.street_address,
        locality=p.locality,
        region=p.region,
        postal_code=p.postal_code,
        country_code=p.country_code,
        services_json=p.services_json,
        phones_json=p.phones_json,
        emails_json=p.emails_json,
        external_reviews_json=p.external_reviews_json,
        rating_value=p.rating_value,
        rating_count=p.rating_count,
        rating_best=p.rating_best,
        rating_worst=p.rating_worst,
        last_scraped_at=p.last_scraped_at.isoformat() if p.last_scraped_at else "",
        scrape_run_id=p.scrape_run_id,
    )


@router.post(
    "/api/doctor-directory/scrape",
    response_model=DoctorScrapeStartResponse,
)
async def start_doctor_scrape(
    body: DoctorScrapeStartRequest,
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db=Depends(get_db),
):
    site_map = {
        "topdoctors_mx": TOPDOCTORS_SITE,
        "doctoralia_mx": DOCTORALIA_SITE,
        "doctoranytime_mx": DOCTORANYTIME_SITE,
    }
    if body.source not in site_map:
        raise HTTPException(
            status_code=400,
            detail="Unsupported source (use topdoctors_mx, doctoralia_mx, or doctoranytime_mx)",
        )
    run = DoctorDirectoryScrapeRun(
        source_site=site_map[body.source],
        status=DoctorScrapeStatus.pending,
        max_profiles=body.max_profiles,
        extra={"delay_seconds": body.delay_seconds, "source_key": body.source},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    rid = run.id
    asyncio.create_task(run_source_scrape(rid, body.source, body.max_profiles, body.delay_seconds))
    return DoctorScrapeStartResponse(run_id=rid, message="Scrape started in background")


@router.get("/api/doctor-directory/runs", response_model=list[ScrapeRunOut])
async def list_scrape_runs(
    limit: int = Query(default=30, ge=1, le=200),
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db=Depends(get_db),
):
    q = (
        await db.execute(
            select(DoctorDirectoryScrapeRun).order_by(DoctorDirectoryScrapeRun.id.desc()).limit(limit)
        )
    ).scalars().all()
    return [_run_to_out(r) for r in q]


@router.get("/api/doctor-directory/stats", response_model=DoctorDirectoryStatsOut)
async def doctor_directory_stats(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db=Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(DoctorDirectoryProfile))).scalar_one()
    by_rows = (
        await db.execute(
            text(
                """
                WITH per_doc AS (
                  SELECT
                    p.id,
                    CASE
                      WHEN p.source_appearances IS NULL OR jsonb_array_length(p.source_appearances) = 0
                        THEN ARRAY['unknown'::text]
                      ELSE COALESCE(
                        ARRAY(
                          SELECT DISTINCT COALESCE(elem->>'source_site', 'unknown')
                          FROM jsonb_array_elements(p.source_appearances) AS elem
                        ),
                        ARRAY['unknown'::text]
                      )
                    END AS sources
                  FROM doctor_directory_profiles p
                ),
                expanded AS (
                  SELECT id, unnest(sources) AS src FROM per_doc
                )
                SELECT src, COUNT(*)::int AS cnt FROM expanded GROUP BY src ORDER BY src
                """
            )
        )
    ).all()
    by_source = {str(row[0]): int(row[1]) for row in by_rows}
    last = (
        await db.execute(select(func.max(DoctorDirectoryProfile.last_scraped_at)))
    ).scalar_one()
    return DoctorDirectoryStatsOut(
        total_profiles=int(total or 0),
        by_source=by_source,
        last_scraped_at=last.isoformat() if last else None,
    )


@router.get("/api/doctor-directory/export.csv")
async def export_doctor_directory_csv(
    _: User = Depends(require_role(RoleEnum.admin, RoleEnum.developer)),
    db=Depends(get_db),
):
    """Full dump of doctor_directory_profiles as UTF-8 CSV (admin/developer)."""
    data = await profiles_to_csv_bytes(db)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="doctor_directory_mexico.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/doctor-directory/search", response_model=DoctorSearchResponse)
async def search_doctors(
    q: str = Query(default="", max_length=400),
    specialty: str = Query(default="", max_length=200),
    city: str = Query(default="", max_length=200),
    match_mode: str = Query(
        default="and",
        description="and: all non-empty filters must match. or: at least one non-empty filter must match.",
    ),
    limit: int = Query(default=20, ge=1, le=50),
    semantic: bool = Query(
        default=True,
        description="When true (default), rank matches by multilingual semantic similarity (Oncología ≈ Oncology).",
    ),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    _ = current_user
    mode = (match_mode or "and").strip().lower()
    if mode not in ("and", "or"):
        mode = "and"

    filt = build_doctor_lexical_clause(q, specialty, city, mode)
    count_base = select(func.count()).select_from(DoctorDirectoryProfile)
    if filt is not None:
        count_base = count_base.where(filt)
    total = (await db.execute(count_base)).scalar_one()

    has_user_query = bool(q.strip() or specialty.strip() or city.strip())
    settings = get_settings()
    cap = int(getattr(settings, "directory_semantic_max_candidates", 600) or 600)
    broad_lim = int(getattr(settings, "directory_semantic_broad_fallback_limit", 2000) or 2000)

    if semantic and has_user_query:
        stmt = select(DoctorDirectoryProfile)
        if filt is not None:
            stmt = stmt.where(filt)
        stmt = stmt.order_by(DoctorDirectoryProfile.id.asc()).limit(cap)
        rows = (await db.execute(stmt)).scalars().all()
        if len(rows) < 80 and (q or "").strip():
            bf = build_doctor_lexical_clause("", specialty, city, "and")
            broad_stmt = select(DoctorDirectoryProfile).order_by(DoctorDirectoryProfile.id.asc()).limit(broad_lim)
            if bf is not None:
                broad_stmt = broad_stmt.where(bf)
            rows2 = (await db.execute(broad_stmt)).scalars().all()
            seen = {r.id for r in rows}
            for r in rows2:
                if r.id not in seen:
                    seen.add(r.id)
                    rows.append(r)
        blobs = [doctor_search_blob(p) for p in rows]
        qtext = build_doctor_query_text(q, specialty, city)
        try:
            ranked = await asyncio.to_thread(semantic_rank_by_query, qtext, blobs, min(limit, len(blobs)))
            top_profiles = [rows[i] for i, _ in ranked if i < len(rows)]
        except Exception as e:
            logger.warning("Doctor semantic search failed, falling back to lexical order: %s", e)
            stmt_fb = select(DoctorDirectoryProfile)
            if filt is not None:
                stmt_fb = stmt_fb.where(filt)
            stmt_fb = stmt_fb.order_by(DoctorDirectoryProfile.display_name.asc()).limit(limit)
            top_profiles = (await db.execute(stmt_fb)).scalars().all()
    else:
        stmt = select(DoctorDirectoryProfile)
        if filt is not None:
            stmt = stmt.where(filt)
        stmt = stmt.order_by(DoctorDirectoryProfile.display_name.asc()).limit(limit)
        top_profiles = (await db.execute(stmt)).scalars().all()

    return DoctorSearchResponse(
        total=int(total or 0),
        results=[_profile_to_out(p) for p in top_profiles],
        disclaimer=(
            "Datos obtenidos de sitios públicos (p. ej. Top Doctors México, Doctoralia México, DoctorAnytime México) "
            "y almacenados con fecha de ingesta por fuente. "
            "Verifica siempre en la fuente original antes de citar o agendar."
        ),
    )
