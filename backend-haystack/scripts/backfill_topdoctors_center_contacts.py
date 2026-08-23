#!/usr/bin/env python3
"""
Backfill Top Doctors clinic contact info into existing doctor_directory_profiles rows.

Run from backend-haystack:
  python -m scripts.backfill_topdoctors_center_contacts --limit 100
  python -m scripts.backfill_topdoctors_center_contacts
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Top Doctors clinic contacts")
    parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0=all)")
    parser.add_argument("--delay", type=float, default=0.15, help="Pause between clinic page fetches")
    args = parser.parse_args()

    import httpx
    from sqlalchemy import select

    from app.database import async_session
    from app.doctor_directory.contact_info import merge_unique_strings
    from app.doctor_directory.models import DoctorDirectoryProfile
    from app.doctor_directory.topdoctors import USER_AGENT, fetch_linked_center_contacts

    async with async_session() as db:
        stmt = (
            select(DoctorDirectoryProfile)
            .where(DoctorDirectoryProfile.source_site == "topdoctors.mx")
            .order_by(DoctorDirectoryProfile.id.asc())
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        rows = list((await db.execute(stmt)).scalars().all())

    logger.info("Loaded %s Top Doctors profiles", len(rows))
    updated = 0
    checked = 0
    center_cache: dict[str, tuple[list[str], list[str]]] = {}

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-MX,es;q=0.9,en;q=0.8"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for row in rows:
            checked += 1
            raw = row.raw_json_ld if isinstance(row.raw_json_ld, dict) else None
            if not raw or not raw.get("hasPOS"):
                continue
            phones, emails = await fetch_linked_center_contacts(client, raw, cache=center_cache)
            merged_phones = merge_unique_strings(row.phones_json if isinstance(row.phones_json, list) else None, phones)
            merged_emails = merge_unique_strings(row.emails_json if isinstance(row.emails_json, list) else None, emails)
            changed = merged_phones != (row.phones_json if isinstance(row.phones_json, list) else []) or merged_emails != (
                row.emails_json if isinstance(row.emails_json, list) else []
            )
            if not changed:
                if args.delay:
                    await asyncio.sleep(args.delay)
                continue

            async with async_session() as db:
                current = await db.get(DoctorDirectoryProfile, row.id)
                if current is None:
                    continue
                current.phones_json = merged_phones or None
                current.emails_json = merged_emails or None
                current.updated_at = datetime.now(timezone.utc)
                await db.commit()
            updated += 1
            logger.info(
                "Updated row %s (%s): %s phones, %s emails",
                row.id,
                row.display_name,
                len(merged_phones),
                len(merged_emails),
            )
            if args.delay:
                await asyncio.sleep(args.delay)

    logger.info("Done. Checked=%s Updated=%s CachedCenters=%s", checked, updated, len(center_cache))


if __name__ == "__main__":
    asyncio.run(main())
