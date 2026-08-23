"""Helpers for admin dashboard overview (external counts, ingestion jobs)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def fetch_pubmed_record_count() -> int | None:
    """NCBI einfo for pubmed — total records (approximate corpus size)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
                params={"db": "pubmed", "retmode": "json"},
            )
            r.raise_for_status()
            payload = r.json()
            rows = (payload.get("einforesult") or {}).get("dbinfo") or []
            if not rows:
                return None
            c = rows[0].get("count")
            if c is None:
                return None
            return int(str(c).replace(",", ""))
    except Exception as e:
        logger.debug("fetch_pubmed_record_count: %s", e)
        return None


async def fetch_clinicaltrials_study_count() -> int | None:
    """ClinicalTrials.gov API v2 — total studies."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("https://clinicaltrials.gov/api/v2/stats/size")
            r.raise_for_status()
            payload = r.json()
            t = payload.get("totalStudies")
            if t is None:
                return None
            return int(t)
    except Exception as e:
        logger.debug("fetch_clinicaltrials_study_count: %s", e)
        return None


def server_row_level(up: bool, state: str, detail: str | None) -> str:
    """ok | warning | error for EC2 / research / Vast serverless."""
    st = (state or "").lower()
    if up and st == "running":
        return "ok"
    if st == "idle":
        return "warning"
    if st == "not_configured" or (detail and "not_configured" in (detail or "")):
        return "warning"
    return "error"


def source_level_ok_count(count: int, *, allow_zero_warning: bool = True) -> str:
    if count > 0:
        return "ok"
    return "warning" if allow_zero_warning else "error"
