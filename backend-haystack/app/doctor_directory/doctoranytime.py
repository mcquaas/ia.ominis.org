"""
DoctorAnytime México: public sitemap /sitemaps/doctors + Physician JSON-LD in page (application/ld+json).

HTTPS GET only (robots disallow /api/). Crawl-delay: 4 — use a respectful default delay in jobs.
"""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from app.doctor_directory.contact_info import build_phones_emails_for_row, extract_all_ld_graph_items_from_html

logger = logging.getLogger(__name__)

SOURCE_SITE = "doctoranytime.mx"
BASE = "https://www.doctoranytime.mx"
DOCTORS_SITEMAP = f"{BASE}/sitemaps/doctors"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

_PROFILE_RE = re.compile(r"^/d/[^/]+/[^/]+/?$")


def profile_slug_from_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if "doctoranytime.mx" not in host:
            return None
        path = "/" + (p.path or "").strip("/") + "/"
        if not _PROFILE_RE.match(path.lower()):
            return None
        return (p.path or "").strip("/")
    except Exception:
        return None


def _strip_html(s: str | None) -> str | None:
    if not s:
        return None
    t = unescape(re.sub(r"<[^>]+>", " ", s))
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _first_address(addr: Any) -> dict[str, Any]:
    if isinstance(addr, list) and addr:
        a = addr[0]
        return a if isinstance(a, dict) else {}
    if isinstance(addr, dict):
        return addr
    return {}


def _country_name(ac: Any) -> str | None:
    if isinstance(ac, dict):
        n = ac.get("name")
        return str(n).strip()[:8] if n else None
    if isinstance(ac, str):
        return ac.strip()[:8]
    return None


def parse_physician_from_page(soup: BeautifulSoup, profile_url: str, slug: str) -> dict[str, Any] | None:
    phys = None
    for sc in soup.find_all("script"):
        raw = sc.string or sc.get_text() or ""
        if "@graph" not in raw or "Physician" not in raw:
            continue
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        g = data.get("@graph")
        if not isinstance(g, list):
            continue
        for item in g:
            if isinstance(item, dict) and item.get("@type") == "Physician":
                phys = item
                break
        if phys:
            break
    if not phys:
        return None

    name = (phys.get("name") or "").strip()
    if not name:
        return None

    spec = phys.get("medicalSpecialty")
    if isinstance(spec, list):
        spec = spec[0] if spec else None
    specialty_label = str(spec).strip() if spec else None

    addr = _first_address(phys.get("address"))
    street = addr.get("streetAddress")
    locality = addr.get("addressLocality")
    region = addr.get("addressRegion")
    postal = addr.get("postalCode")
    country = _country_name(addr.get("addressCountry"))

    img = phys.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    image_url = str(img).strip() if img else None

    ar = phys.get("aggregateRating") if isinstance(phys.get("aggregateRating"), dict) else {}
    rv = ar.get("ratingValue")
    rc = ar.get("reviewCount") or ar.get("ratingCount")
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

    u = phys.get("url")
    canon = str(u).strip() if u else profile_url
    if not canon.startswith("http"):
        canon = profile_url

    desc = _strip_html(phys.get("description"))

    return {
        "source_site": SOURCE_SITE,
        "profile_slug": slug[:512],
        "profile_url": canon.rstrip("/") + "/",
        "display_name": name[:512],
        "specialty_label": specialty_label[:255] if specialty_label else None,
        "specialties_json": [specialty_label] if specialty_label else None,
        "description": desc,
        "image_url": image_url,
        "street_address": street,
        "locality": locality,
        "region": region,
        "postal_code": str(postal).strip() if postal else None,
        "country_code": str(country).strip()[:8] if country else None,
        "services_json": None,
        "rating_value": rating_value,
        "rating_count": rating_count,
        "rating_best": best,
        "rating_worst": worst,
        "raw_json_ld": {"parser": "doctoranytime_ld_json_v1", "name": name, "medicalSpecialty": specialty_label},
    }


async def fetch_doctor_profile_urls(client: httpx.AsyncClient, max_urls: int) -> list[str]:
    r = await client.get(DOCTORS_SITEMAP, timeout=120.0)
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
        if profile_slug_from_url(u):
            out.append(u)
    return out


async def fetch_and_parse_profile(client: httpx.AsyncClient, profile_url: str) -> dict[str, Any] | None:
    slug = profile_slug_from_url(profile_url)
    if not slug:
        return None
    r = await client.get(profile_url, timeout=60.0, follow_redirects=True)
    if r.status_code != 200:
        logger.warning("doctoranytime profile HTTP %s %s", r.status_code, profile_url)
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    row = parse_physician_from_page(soup, profile_url, slug)
    if not row:
        logger.warning("no Physician JSON-LD %s", profile_url)
        return None
    html = r.text
    graph = extract_all_ld_graph_items_from_html(html)
    phys = row.get("raw_json_ld") if isinstance(row.get("raw_json_ld"), dict) else None
    phones, emails = build_phones_emails_for_row(html=html, physician_ld=phys, graph_items=graph)
    if phones:
        row["phones_json"] = phones
    if emails:
        row["emails_json"] = emails
    return row
