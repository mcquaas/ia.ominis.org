"""Connector that fetches documents from a list of URLs (Mexican health sources: DOF, CENETEC, etc.)."""

import hashlib
import logging
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from pipeline.ingest.base import BaseConnector

logger = logging.getLogger(__name__)


def _text_from_html(html: str) -> str:
    """Strip tags and normalize whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500_000]  # cap size


class UrlListConnector(BaseConnector):
    """Fetch and normalize documents from a list of URLs. Use for DOF, CENETEC, SSA, etc."""

    source_type = "url_list"

    def __init__(
        self,
        urls: list[str],
        institution: str = "SSA",
        document_type: str = "documento",
        country: str = "México",
    ):
        self.urls = urls
        self.institution = institution
        self.document_type = document_type
        self.country = country

    def fetch(self) -> list[dict[str, Any]]:
        raw_list: list[dict[str, Any]] = []
        for url in self.urls:
            try:
                with httpx.Client(timeout=30, follow_redirects=True) as client:
                    r = client.get(url)
                    r.raise_for_status()
                    body = r.text
            except Exception as e:
                logger.warning("UrlListConnector fetch %s: %s", url, e)
                continue
            text = _text_from_html(body) if "text/html" in r.headers.get("content-type", "") else body
            if len(text) < 100:
                continue
            raw_list.append({
                "url": url,
                "title": urlparse(url).path.rstrip("/").split("/")[-1] or url[:80],
                "raw_text": text[:300_000],
                "institution": self.institution,
                "document_type": self.document_type,
                "country": self.country,
            })
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
