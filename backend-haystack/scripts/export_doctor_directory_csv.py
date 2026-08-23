#!/usr/bin/env python3
"""
Export scraped doctor profiles from PostgreSQL to CSV.

Run from backend-haystack (with DATABASE_URL / app config available):
  python -m scripts.export_doctor_directory_csv -o doctors.csv

  python -m scripts.export_doctor_directory_csv -o topdoctors.csv --source-site topdoctors_mx
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _run(output: str, source_site: str | None) -> int:
    from app.database import async_session
    from app.doctor_directory.csv_export import profiles_to_csv_bytes

    async with async_session() as db:
        data = await profiles_to_csv_bytes(db, source_site=source_site)

    with open(output, "wb") as f:
        f.write(data)

    # Row count = lines - header (best-effort)
    line_count = data.count(b"\n")
    rows = max(0, line_count - 1)
    logger.info("Wrote %s bytes (%s data rows) to %s", len(data), rows, output)
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Export doctor_directory_profiles to CSV")
    p.add_argument("-o", "--output", required=True, help="Output CSV path")
    p.add_argument(
        "--source-site",
        default=None,
        help="Optional filter (e.g. topdoctors_mx, doctoralia_mx, doctoranytime_mx)",
    )
    args = p.parse_args()
    asyncio.run(_run(args.output, args.source_site))


if __name__ == "__main__":
    main()
