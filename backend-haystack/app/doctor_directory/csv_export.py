"""CSV serialization for doctor_directory_profiles (shared by API and CLI script)."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctor_directory.contact_info import (
    enriched_contact_lists_for_export,
    enriched_contacts_for_export,
)
from app.doctor_directory.models import DoctorDirectoryProfile

_JSON_COLUMNS = frozenset(
    {
        "specialties_json",
        "services_json",
        "phones_json",
        "emails_json",
        "external_reviews_json",
        "raw_json_ld",
        "source_appearances",
    }
)

_DT_COLUMNS = frozenset({"last_scraped_at", "created_at", "updated_at"})
_PHONE_COLUMN_COUNT = 12
_EMAIL_COLUMN_COUNT = 12

PHONE_COLUMNS = [f"phone_{i}" for i in range(1, _PHONE_COLUMN_COUNT + 1)]
EMAIL_COLUMNS = [f"email_{i}" for i in range(1, _EMAIL_COLUMN_COUNT + 1)]

CSV_COLUMNS = [
    "id",
    "dedupe_key",
    "source_site",
    "profile_slug",
    "profile_url",
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
    "source_appearances",
    "last_scraped_at",
    "scrape_run_id",
    "created_at",
    "updated_at",
    "phones_all",
    "emails_all",
    *PHONE_COLUMNS,
    *EMAIL_COLUMNS,
]


def csv_cell(column: str, value):
    if value is None:
        return ""
    if column in _JSON_COLUMNS:
        return json.dumps(value, ensure_ascii=False, default=str)
    if column in _DT_COLUMNS and isinstance(value, datetime):
        return value.isoformat()
    return value


async def profiles_to_csv_bytes(db: AsyncSession, *, source_site: str | None = None) -> bytes:
    """Load all profiles (optionally filtered by source_site) and return UTF-8 CSV bytes."""
    query = select(DoctorDirectoryProfile).order_by(DoctorDirectoryProfile.id)
    if source_site:
        query = query.where(DoctorDirectoryProfile.source_site == source_site)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for row in rows:
        cells = {
            c: csv_cell(c, getattr(row, c, None))
            for c in CSV_COLUMNS
            if c not in {"phones_all", "emails_all", *PHONE_COLUMNS, *EMAIL_COLUMNS}
        }
        phones, emails = enriched_contact_lists_for_export(
            row.phones_json if isinstance(row.phones_json, list) else None,
            row.emails_json if isinstance(row.emails_json, list) else None,
            row.raw_json_ld,
        )
        pa, ea = enriched_contacts_for_export(
            row.phones_json if isinstance(row.phones_json, list) else None,
            row.emails_json if isinstance(row.emails_json, list) else None,
            row.raw_json_ld,
        )
        cells["phones_all"] = pa
        cells["emails_all"] = ea
        for idx, column in enumerate(PHONE_COLUMNS):
            cells[column] = phones[idx] if idx < len(phones) else ""
        for idx, column in enumerate(EMAIL_COLUMNS):
            cells[column] = emails[idx] if idx < len(emails) else ""
        w.writerow(cells)
    return buf.getvalue().encode("utf-8")
