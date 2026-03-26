"""
Fetch public Top Doctors México pages: sitemap URLs + JSON-LD Physician blocks.

Uses only normal HTTPS GET of pages linked from https://www.topdoctors.mx/sitemap.xml (doctors-all).
Does not call disallowed /api/ routes. Operators remain responsible for site terms and crawl rate.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE_SITE = "topdoctors.mx"
BASE = "https://www.topdoctors.mx"
SITEMAP_INDEX = f"{BASE}/sitemap.xml"
DOCTORS_ALL = f"{BASE}/sitemap/mx/doctors-all.xml"
USER_AGENT = "OminisDoctorDirectoryBot/1.0 (+https://ominis.org; ingest for internal directory)"

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

_PHONE_PATTERNS = [
    re.compile(r"\+52\s*\(?\d{2,3}\)?\s*[\d\s]{8,25}(?:\s*Ext\.?\s*\d+)?", re.I),
    re.compile(r"\(\+52\)\s*[\d\s\(\)]{10,30}", re.I),
]


def profile_slug_from_url(url: str) -> str | None:
    try:
        path = urlparse(url).path.strip("/").split("/")
        if len(path) >= 2 and path[0] == "doctor" and path[1]:
            return path[1].rstrip("/")
    except Exception:
        pass
    return None


async def fetch_doctor_profile_urls(client: httpx.AsyncClient, max_urls: int) -> list[str]:
    r = await client.get(DOCTORS_ALL, timeout=120.0)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out: list[str] = []
    for url_el in root.findall("sm:url", _NS):
        if len(out) >= max_urls:
            break
        loc = url_el.find("sm:loc", _NS)
        if loc is None or not loc.text:
            continue
        u = loc.text.strip()
        if "/doctor/" in u and profile_slug_from_url(u):
            out.append(u)
    return out


def _extract_phones_from_html(html: str) -> list[str]:
    seen: set[str] = set()
    phones: list[str] = []
    for pat in _PHONE_PATTERNS:
        for m in pat.finditer(html):
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            if len(raw) < 12 or raw in seen:
                continue
            if "5593315610" in raw.replace(" ", ""):  # site-wide support line noise
                continue
            seen.add(raw)
            phones.append(raw)
    return phones[:6]


def parse_physician_json_ld(html: str, profile_url: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph") if isinstance(data, dict) else None
        if not isinstance(graph, list):
            continue
        for item in graph:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Physician":
                return item
    return None


def physician_to_row_fields(physician: dict[str, Any], profile_url: str, slug: str) -> dict[str, Any]:
    name = (physician.get("name") or "").strip() or slug.replace("-", " ").title()
    addr = physician.get("address") if isinstance(physician.get("address"), dict) else {}
    specs: list[str] = []
    ms = physician.get("medicalSpecialty")
    if isinstance(ms, list):
        for s in ms:
            if isinstance(s, dict) and s.get("name"):
                specs.append(str(s["name"]).strip())
            elif isinstance(s, str):
                specs.append(s.strip())
    elif isinstance(ms, dict) and ms.get("name"):
        specs.append(str(ms["name"]).strip())

    services: list[str] = []
    av = physician.get("availableService")
    if isinstance(av, list):
        for s in av:
            if isinstance(s, dict) and s.get("name"):
                services.append(str(s["name"]).strip())

    ar = physician.get("aggregateRating") if isinstance(physician.get("aggregateRating"), dict) else {}
    rv = ar.get("ratingValue")
    rc = ar.get("reviewCount")
    try:
        rating_value = float(rv) if rv is not None and str(rv).strip() != "" else None
    except (TypeError, ValueError):
        rating_value = None
    try:
        rating_count = int(rc) if rc is not None else None
    except (TypeError, ValueError):
        rating_count = None
    try:
        best = float(ar.get("bestRating")) if ar.get("bestRating") is not None else None
    except (TypeError, ValueError):
        best = None
    try:
        worst = float(ar.get("worstRating")) if ar.get("worstRating") is not None else None
    except (TypeError, ValueError):
        worst = None

    return {
        "source_site": SOURCE_SITE,
        "profile_slug": slug,
        "profile_url": profile_url.rstrip("/") + "/",
        "display_name": name[:512],
        "specialty_label": (specs[0][:255] if specs else None),
        "specialties_json": specs or None,
        "description": (physician.get("description") or None),
        "image_url": (physician.get("image") or None),
        "street_address": (addr.get("streetAddress") or None),
        "locality": (addr.get("addressLocality") or None),
        "region": (addr.get("addressRegion") or None),
        "postal_code": (addr.get("postalCode") or None),
        "country_code": (addr.get("addressCountry") or None),
        "services_json": services or None,
        "rating_value": rating_value,
        "rating_count": rating_count,
        "rating_best": best,
        "rating_worst": worst,
        "raw_json_ld": physician,
    }


async def fetch_and_parse_profile(client: httpx.AsyncClient, profile_url: str) -> dict[str, Any] | None:
    slug = profile_slug_from_url(profile_url)
    if not slug:
        return None
    r = await client.get(profile_url, timeout=60.0, follow_redirects=True)
    if r.status_code != 200:
        logger.warning("doctor profile HTTP %s %s", r.status_code, profile_url)
        return None
    html = r.text
    physician = parse_physician_json_ld(html, profile_url)
    if not physician:
        logger.warning("no Physician JSON-LD %s", profile_url)
        return None
    row = physician_to_row_fields(physician, profile_url, slug)
    phones = _extract_phones_from_html(html)
    if phones:
        row["phones_json"] = phones
    return row
