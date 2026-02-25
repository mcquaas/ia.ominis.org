"""Crawl seed URLs: fetch page, discover same-domain links, fetch them up to max_pages. Use for gob.mx/salud and similar."""

import hashlib
import logging
import re
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from pipeline.ingest.base import BaseConnector

logger = logging.getLogger(__name__)

# Match href="..." or href='...' (single or double quote)
HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _text_from_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500_000]


def _normalize_url(base_url: str, href: str) -> str | None:
    """Resolve relative href against base_url; return None if not http(s)."""
    href = href.strip().split("#")[0].split("?")[0]
    if not href or href.startswith("mailto:") or href.startswith("tel:"):
        return None
    try:
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            return None
        return full
    except Exception:
        return None


def _same_domain(url: str, seed_netloc: str) -> bool:
    if not url or not seed_netloc:
        return False
    return urlparse(url).netloc.lower() == seed_netloc.lower()


def _discover_links(html: str, base_url: str, seed_netloc: str) -> set[str]:
    """Extract same-domain links from HTML."""
    out = set()
    for m in HREF_RE.finditer(html):
        href = m.group(1).strip()
        full = _normalize_url(base_url, href)
        if full and _same_domain(full, seed_netloc):
            out.add(full)
    return out


class UrlCrawlConnector(BaseConnector):
    """Fetch seed URLs and follow same-domain links up to max_pages. Good for gob.mx/salud, etc."""

    source_type = "url_crawl"

    def __init__(
        self,
        seed_urls: list[str],
        max_pages: int = 50,
        same_domain_only: bool = True,
        institution: str = "SSA",
        document_type: str = "documento",
        country: str = "México",
    ):
        self.seed_urls = seed_urls
        self.max_pages = max_pages
        self.same_domain_only = same_domain_only
        self.institution = institution
        self.document_type = document_type
        self.country = country

    def fetch(self) -> list[dict[str, Any]]:
        raw_list: list[dict[str, Any]] = []
        to_fetch: set[str] = set()
        for u in self.seed_urls:
            parsed = urlparse(u)
            if parsed.scheme in ("http", "https"):
                to_fetch.add(u)

        fetched: set[str] = set()
        pages_done = 0

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            while to_fetch and pages_done < self.max_pages:
                url = to_fetch.pop()
                if url in fetched:
                    continue
                fetched.add(url)
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    body = r.text
                except Exception as e:
                    logger.warning("Crawl fetch %s: %s", url, e)
                    continue
                ct = r.headers.get("content-type", "")
                if "text/html" not in ct:
                    continue
                text = _text_from_html(body)
                if len(text) < 50:
                    continue
                raw_list.append({
                    "url": url,
                    "title": urlparse(url).path.rstrip("/").split("/")[-1] or url[:80],
                    "raw_text": text[:300_000],
                    "institution": self.institution,
                    "document_type": self.document_type,
                    "country": self.country,
                })
                pages_done += 1
                if pages_done >= self.max_pages:
                    break
                if self.same_domain_only:
                    seed_netloc = urlparse(url).netloc
                    new_links = _discover_links(body, url, seed_netloc)
                    for link in new_links:
                        if link not in fetched:
                            to_fetch.add(link)
        logger.info("Crawl: fetched %d pages from %d seeds", len(raw_list), len(self.seed_urls))
        return raw_list

    def parse(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        text = (raw.get("raw_text") or "").strip()
        if not text:
            return None
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        doc_id = str(uuid.uuid4())
        return {
            "doc_id": doc_id,
            "title": raw.get("title", ""),
            "year": None,
            "country": raw.get("country", "México"),
            "institution": raw.get("institution", "SSA"),
            "document_type": raw.get("document_type", "documento"),
            "medical_specialty": "",
            "population": "",
            "state": "",
            "source_url": raw.get("url", ""),
            "source_type": self.source_type,
            "raw_text": text,
            "content_hash": content_hash,
        }
