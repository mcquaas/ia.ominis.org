"""Background scrape: update run row and upsert merged canonical profiles."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.doctor_directory import doctoralia, doctoranytime, topdoctors
from app.doctor_directory.merge import (
    build_appearance,
    compute_dedupe_key,
    merge_appearances,
    merge_scalar_profile_fields,
    primary_profile_url,
    summarize_source_site,
)
from app.doctor_directory.models import (
    DoctorDirectoryProfile,
    DoctorDirectoryScrapeRun,
    DoctorScrapeStatus,
)

logger = logging.getLogger(__name__)

FetchUrlsFn = Callable[[httpx.AsyncClient, int], Awaitable[list[str]]]
ParseProfileFn = Callable[[httpx.AsyncClient, str], Awaitable[dict | None]]

SOURCE_SCRAPERS: dict[str, tuple[FetchUrlsFn, ParseProfileFn]] = {
    "topdoctors_mx": (topdoctors.fetch_doctor_profile_urls, topdoctors.fetch_and_parse_profile),
    "doctoralia_mx": (doctoralia.fetch_doctor_profile_urls, doctoralia.fetch_and_parse_profile),
    "doctoranytime_mx": (doctoranytime.fetch_doctor_profile_urls, doctoranytime.fetch_and_parse_profile),
}

_MERGE_FIELD_NAMES = (
    "display_name",
    "specialty_label",
    "specialties_json",
    "description",
    "image_url",
    "street_address",
    "locality",
    "region",
    "postal_code",
    "country_code",
    "services_json",
    "phones_json",
    "emails_json",
    "external_reviews_json",
    "rating_value",
    "rating_count",
    "rating_best",
    "rating_worst",
    "raw_json_ld",
)


def _row_to_merge_dict(row: DoctorDirectoryProfile) -> dict:
    return {k: getattr(row, k) for k in _MERGE_FIELD_NAMES}


async def _upsert_profile_merged_once(db: AsyncSession, run_id: int, fields: dict, scraped_at: datetime) -> None:
    dk = compute_dedupe_key(
        fields["display_name"],
        fields.get("specialty_label"),
        fields.get("locality"),
        fields.get("region"),
    )
    new_app = build_appearance(
        source_site=fields["source_site"],
        profile_slug=fields["profile_slug"],
        profile_url=fields["profile_url"],
        scraped_at=scraped_at,
        scrape_run_id=run_id,
        rating_value=fields.get("rating_value"),
        rating_count=fields.get("rating_count"),
    )

    res = await db.execute(
        select(DoctorDirectoryProfile).where(DoctorDirectoryProfile.dedupe_key == dk).with_for_update()
    )
    existing = res.scalar_one_or_none()

    if existing is not None:
        apps = merge_appearances(
            existing.source_appearances if isinstance(existing.source_appearances, list) else [],
            new_app,
        )
        merged_cols = merge_scalar_profile_fields(_row_to_merge_dict(existing), fields)
        for k, v in merged_cols.items():
            setattr(existing, k, v)
        existing.source_appearances = apps
        existing.source_site = summarize_source_site(apps)
        existing.profile_slug = dk
        existing.profile_url = primary_profile_url(apps, fields["profile_url"])
        existing.dedupe_key = dk
        existing.last_scraped_at = scraped_at
        existing.scrape_run_id = run_id
        existing.updated_at = scraped_at
        return

    apps = [new_app]
    kwargs = {k: fields[k] for k in _MERGE_FIELD_NAMES if k in fields}
    db.add(
        DoctorDirectoryProfile(
            dedupe_key=dk,
            source_appearances=apps,
            source_site=summarize_source_site(apps),
            profile_slug=dk,
            profile_url=primary_profile_url(apps, fields["profile_url"]),
            last_scraped_at=scraped_at,
            scrape_run_id=run_id,
            created_at=scraped_at,
            updated_at=scraped_at,
            **kwargs,
        )
    )


async def _upsert_profile(db: AsyncSession, run_id: int, fields: dict, scraped_at: datetime) -> None:
    """Merge by canonical dedupe_key; safe under concurrent scrapers (retry on unique races)."""
    for attempt in range(8):
        try:
            await _upsert_profile_merged_once(db, run_id, fields, scraped_at)
            await db.commit()
            return
        except IntegrityError:
            await db.rollback()
            if attempt == 7:
                raise
            await asyncio.sleep(0.04 * (attempt + 1))


async def run_source_scrape(
    run_id: int,
    source_key: str,
    max_profiles: int,
    delay_seconds: float,
) -> None:
    if source_key not in SOURCE_SCRAPERS:
        logger.error("unknown doctor directory source %s", source_key)
        async with async_session() as db:
            await db.execute(
                update(DoctorDirectoryScrapeRun)
                .where(DoctorDirectoryScrapeRun.id == run_id)
                .values(
                    status=DoctorScrapeStatus.failed,
                    finished_at=datetime.now(timezone.utc),
                    error_message=f"Unknown source key: {source_key}",
                )
            )
            await db.commit()
        return

    fetch_urls, parse_one = SOURCE_SCRAPERS[source_key]
    scraped_at = datetime.now(timezone.utc)
    async with async_session() as db:
        await db.execute(
            update(DoctorDirectoryScrapeRun)
            .where(DoctorDirectoryScrapeRun.id == run_id)
            .values(
                status=DoctorScrapeStatus.running,
                started_at=scraped_at,
            )
        )
        await db.commit()

    attempted = upserted = failed = 0
    err_msg: str | None = None
    catastrophic: str | None = None

    try:
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        async with httpx.AsyncClient(
            headers={"User-Agent": topdoctors.USER_AGENT},
            follow_redirects=True,
            timeout=httpx.Timeout(90.0),
            limits=limits,
        ) as client:
            urls = await fetch_urls(client, max_profiles)
            for url in urls:
                attempted += 1
                try:
                    row = await parse_one(client, url)
                    if not row:
                        failed += 1
                    else:
                        async with async_session() as db2:
                            now = datetime.now(timezone.utc)
                            await _upsert_profile(db2, run_id, row, now)
                            upserted += 1
                except Exception as e:
                    logger.exception("profile scrape error %s", url)
                    failed += 1
                    err_msg = str(e)[:2000]

                async with async_session() as db3:
                    await db3.execute(
                        update(DoctorDirectoryScrapeRun)
                        .where(DoctorDirectoryScrapeRun.id == run_id)
                        .values(
                            profiles_attempted=attempted,
                            profiles_upserted=upserted,
                            profiles_failed=failed,
                        )
                    )
                    await db3.commit()

                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
    except Exception as e:
        logger.exception("scrape run %s failed", run_id)
        catastrophic = str(e)[:2000]

    finished = datetime.now(timezone.utc)
    final_status = DoctorScrapeStatus.failed if catastrophic and upserted == 0 else DoctorScrapeStatus.completed
    note = catastrophic or err_msg
    async with async_session() as db:
        await db.execute(
            update(DoctorDirectoryScrapeRun)
            .where(DoctorDirectoryScrapeRun.id == run_id)
            .values(
                status=final_status,
                finished_at=finished,
                profiles_attempted=attempted,
                profiles_upserted=upserted,
                profiles_failed=failed,
                error_message=note,
            )
        )
        await db.commit()


async def run_topdoctors_scrape(run_id: int, max_profiles: int, delay_seconds: float) -> None:
    """Backward-compatible entrypoint."""
    await run_source_scrape(run_id, "topdoctors_mx", max_profiles, delay_seconds)
