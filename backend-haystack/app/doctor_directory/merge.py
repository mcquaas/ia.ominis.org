"""Canonical doctor key (name + specialty + location) for cross-source deduplication."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def _normalize_part(s: str | None) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"^(dr\.?|dra\.?|doctora?\.?)\s+", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t


def compute_dedupe_key(
    display_name: str,
    specialty_label: str | None,
    locality: str | None,
    region: str | None,
) -> str:
    raw = "|".join(
        [
            _normalize_part(display_name),
            _normalize_part(specialty_label),
            _normalize_part(locality),
            _normalize_part(region),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pick_longer(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if len(a) >= len(b) else b


def _merge_phones(a: list | None, b: list | None) -> list | None:
    if not a and not b:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for src in (a or []), (b or []):
        for p in src:
            p = str(p).strip()
            if p and p not in seen:
                seen.add(p)
                out.append(p)
    return out or None


def _merge_services(a: list | None, b: list | None) -> list | None:
    if not a and not b:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for src in (a or []), (b or []):
        for s in src:
            s = str(s).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out[:40] or None


def merge_scalar_profile_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming parser row into existing column dict (for SQLAlchemy update)."""
    out = dict(existing)
    out["display_name"] = (
        _pick_longer(existing.get("display_name"), incoming.get("display_name"))
        or existing.get("display_name")
        or incoming.get("display_name")
    )
    out["specialty_label"] = incoming.get("specialty_label") or existing.get("specialty_label")
    out["description"] = _pick_longer(existing.get("description"), incoming.get("description"))
    out["image_url"] = incoming.get("image_url") or existing.get("image_url")
    out["street_address"] = _pick_longer(existing.get("street_address"), incoming.get("street_address"))
    out["locality"] = incoming.get("locality") or existing.get("locality")
    out["region"] = incoming.get("region") or existing.get("region")
    out["postal_code"] = incoming.get("postal_code") or existing.get("postal_code")
    out["country_code"] = incoming.get("country_code") or existing.get("country_code")
    out["specialties_json"] = _merge_services(existing.get("specialties_json"), incoming.get("specialties_json"))
    out["services_json"] = _merge_services(existing.get("services_json"), incoming.get("services_json"))
    out["phones_json"] = _merge_phones(existing.get("phones_json"), incoming.get("phones_json"))
    out["external_reviews_json"] = existing.get("external_reviews_json") or incoming.get("external_reviews_json")
    # Prefer rating with more reviews; else higher value
    er, ec = existing.get("rating_value"), existing.get("rating_count") or 0
    ir, ic = incoming.get("rating_value"), incoming.get("rating_count") or 0
    if ic > ec or (ic == ec and (ir or 0) > (er or 0)):
        out["rating_value"] = ir
        out["rating_count"] = ic if ic else None
        out["rating_best"] = incoming.get("rating_best")
        out["rating_worst"] = incoming.get("rating_worst")
    else:
        out["rating_value"] = er
        out["rating_count"] = ec if ec else None
        out["rating_best"] = existing.get("rating_best")
        out["rating_worst"] = existing.get("rating_worst")
    out["raw_json_ld"] = incoming.get("raw_json_ld") or existing.get("raw_json_ld")
    return out


def build_appearance(
    *,
    source_site: str,
    profile_slug: str,
    profile_url: str,
    scraped_at: datetime,
    scrape_run_id: int | None,
    rating_value: float | None = None,
    rating_count: int | None = None,
) -> dict[str, Any]:
    return {
        "source_site": source_site,
        "profile_slug": profile_slug,
        "profile_url": profile_url.rstrip("/") + "/",
        "last_scraped_at": scraped_at.replace(tzinfo=scraped_at.tzinfo or timezone.utc).isoformat(),
        "scrape_run_id": scrape_run_id,
        "rating_value": rating_value,
        "rating_count": rating_count,
    }


def merge_appearances(existing: list[dict[str, Any]] | None, new_app: dict[str, Any]) -> list[dict[str, Any]]:
    key = (new_app["source_site"], new_app["profile_slug"])
    kept = [a for a in (existing or []) if (a.get("source_site"), a.get("profile_slug")) != key]
    kept.append(new_app)
    kept.sort(key=lambda a: (a.get("source_site") or "", a.get("profile_slug") or ""))
    return kept


def summarize_source_site(appearances: list[dict[str, Any]] | None) -> str:
    if not appearances:
        return "unknown"
    sites = sorted({a.get("source_site") or "" for a in appearances if a.get("source_site")})
    if len(sites) <= 1:
        return sites[0] if sites else "unknown"
    return "merged"


def primary_profile_url(appearances: list[dict[str, Any]] | None, fallback: str) -> str:
    if not appearances:
        return fallback
    return appearances[0].get("profile_url") or fallback
