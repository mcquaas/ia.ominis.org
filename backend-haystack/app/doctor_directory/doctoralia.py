"""
Fetch public Doctoralia México profile pages: sitemap URLs + schema.org Physician microdata.

Uses HTTPS GET only (no /api/ per robots). Sitemaps: new_doctor + last_opinion (deduped).
Operators remain responsible for Doctoralia terms and crawl rate.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from app.doctor_directory.contact_info import build_phones_emails_for_row, extract_all_ld_graph_items_from_html
from app.doctor_directory.topdoctors import USER_AGENT

logger = logging.getLogger(__name__)

SOURCE_SITE = "doctoralia.com.mx"
BASE = "https://www.doctoralia.com.mx"
# Public urlsets with doctor profile URLs (path: /{slug}/{specialty}/{city})
DOCTOR_SITEMAPS = [
    f"{BASE}/sitemap.new_doctor.xml",
    f"{BASE}/sitemap.last_opinion.xml",
]

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_PROFILE_PATH = re.compile(r"^/[^/]+/[^/]+/[^/]+/?$")


def profile_slug_from_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        if (p.netloc or "").lower().rstrip(".") not in ("www.doctoralia.com.mx", "doctoralia.com.mx"):
            return None
        path = "/" + p.path.strip("/") + "/"
        if not _PROFILE_PATH.match(path):
            return None
        return p.path.strip("/")
    except Exception:
        return None


def _is_physician_scope(el: BeautifulSoup) -> bool:
    it = (el.get("itemtype") or "").lower()
    return "schema.org/physician" in it


def _meta_or_text(node: BeautifulSoup | None) -> str | None:
    if node is None:
        return None
    if node.name == "meta":
        return (node.get("content") or "").strip() or None
    t = node.get_text(" ", strip=True)
    return t or None


def _itemprop_content(root: BeautifulSoup, prop: str) -> str | None:
    n = root.find(attrs={"itemprop": prop})
    return _meta_or_text(n)


def _absolute_url(url: str | None, base: str) -> str | None:
    if not url:
        return None
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return urljoin(base, u)
    return u


def parse_physician_microdata(soup: BeautifulSoup, profile_url: str, slug: str) -> dict[str, Any] | None:
    phys = None
    for el in soup.find_all(attrs={"itemscope": True}):
        if _is_physician_scope(el):
            phys = el
            break
    if phys is None:
        return None

    name = _itemprop_content(phys, "name")
    if not name:
        h1 = soup.find("h1")
        name = h1.get_text(" ", strip=True) if h1 else None
    if not name:
        return None

    # Prefix like "Dra." from h1 if missing on name
    h1t = soup.find("h1")
    h1_full = h1t.get_text(" ", strip=True) if h1t else ""
    display = name
    if h1_full and name in h1_full and len(h1_full) > len(name):
        display = h1_full

    image_url = None
    img_node = phys.find(attrs={"itemprop": "image"})
    if img_node:
        inner = img_node.find("img")
        if inner and inner.get("src"):
            image_url = _absolute_url(inner.get("src"), BASE)
        elif img_node.name == "a" and img_node.get("href"):
            image_url = _absolute_url(img_node.get("href"), BASE)
        elif img_node.name == "meta":
            image_url = _absolute_url(img_node.get("content"), BASE)

    canonical = soup.find("link", rel=lambda x: x and "canonical" in x)
    canon_url = canonical.get("href") if canonical and canonical.get("href") else profile_url
    if not canon_url.startswith("http"):
        canon_url = urljoin(BASE + "/", canon_url)

    desc_meta = soup.find("meta", attrs={"name": "description"})
    description = (desc_meta.get("content") or "").strip() if desc_meta else None

    street = locality = region = postal = country = None
    addr_el = phys.find(attrs={"itemprop": "address"})
    if addr_el:
        street = _itemprop_content(addr_el, "streetAddress")
        locality = _itemprop_content(addr_el, "addressLocality")
        region = _itemprop_content(addr_el, "addressRegion")
        postal = _itemprop_content(addr_el, "postalCode")
        country = _itemprop_content(addr_el, "addressCountry")

    specialty_label = None
    specs: list[str] = []
    for h2 in soup.find_all("h2"):
        t = h2.get_text(" ", strip=True)
        if "·" in t:
            first = t.split("·")[0].strip()
            if first and len(first) < 100:
                specialty_label = first
                break
    if not specialty_label:
        parts = slug.split("/")
        if len(parts) >= 2:
            specialty_label = parts[1].replace("-", " ").title()

    services: list[str] = []
    for sv in phys.find_all(attrs={"itemprop": "availableService"}):
        tx = sv.get_text(" ", strip=True)
        if tx:
            services.append(tx)

    rv = rc = best = worst = None
    agg = phys.find(attrs={"itemprop": "aggregateRating"})
    if agg:
        try:
            v = _itemprop_content(agg, "ratingValue")
            if v is not None:
                rv = float(v)
        except (TypeError, ValueError):
            pass
        try:
            c = _itemprop_content(agg, "reviewCount")
            if c is not None:
                rc = int(c)
        except (TypeError, ValueError):
            pass
        try:
            b = _itemprop_content(agg, "bestRating")
            if b is not None:
                best = float(b)
        except (TypeError, ValueError):
            pass
        try:
            w = _itemprop_content(agg, "worstRating")
            if w is not None:
                worst = float(w)
        except (TypeError, ValueError):
            pass

    raw_snapshot: dict[str, Any] = {
        "parser": "doctoralia_microdata_v1",
        "display_name": display,
        "canonical_url": canon_url,
        "services_count": len(services),
    }

    return {
        "source_site": SOURCE_SITE,
        "profile_slug": slug[:512],
        "profile_url": canon_url.rstrip("/") + "/",
        "display_name": display[:512],
        "specialty_label": (specialty_label[:255] if specialty_label else None),
        "specialties_json": specs or ([specialty_label] if specialty_label else None),
        "description": description,
        "image_url": image_url,
        "street_address": street,
        "locality": locality,
        "region": region,
        "postal_code": postal,
        "country_code": country,
        "services_json": services or None,
        "rating_value": rv,
        "rating_count": rc,
        "rating_best": best,
        "rating_worst": worst,
        "raw_json_ld": raw_snapshot,
    }


async def fetch_doctor_profile_urls(client: httpx.AsyncClient, max_urls: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for sm_url in DOCTOR_SITEMAPS:
        if len(out) >= max_urls:
            break
        try:
            r = await client.get(sm_url, timeout=120.0)
            r.raise_for_status()
        except Exception as e:
            logger.warning("doctoralia sitemap fetch failed %s: %s", sm_url, e)
            continue
        root = ET.fromstring(r.content)
        for url_el in root.findall("sm:url", _NS):
            if len(out) >= max_urls:
                break
            loc = url_el.find("sm:loc", _NS)
            if loc is None or not loc.text:
                continue
            u = loc.text.strip()
            slug = profile_slug_from_url(u)
            if not slug or u in seen:
                continue
            seen.add(u)
            out.append(u)
    return out


async def fetch_and_parse_profile(client: httpx.AsyncClient, profile_url: str) -> dict[str, Any] | None:
    slug = profile_slug_from_url(profile_url)
    if not slug:
        return None
    r = await client.get(profile_url, timeout=60.0, follow_redirects=True)
    if r.status_code != 200:
        logger.warning("doctoralia profile HTTP %s %s", r.status_code, profile_url)
        return None
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    row = parse_physician_microdata(soup, profile_url, slug)
    if not row:
        logger.warning("no Physician microdata %s", profile_url)
        return None
    graph = extract_all_ld_graph_items_from_html(html)
    phys = row.get("raw_json_ld") if isinstance(row.get("raw_json_ld"), dict) else None
    phones, emails = build_phones_emails_for_row(html=html, physician_ld=phys, graph_items=graph)
    if phones:
        row["phones_json"] = phones
    if emails:
        row["emails_json"] = emails
    return row
