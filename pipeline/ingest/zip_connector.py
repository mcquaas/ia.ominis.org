"""Ingest from a ZIP file: e.g. WhatsApp chat export (.txt with URLs) and optional attached files."""

import hashlib
import logging
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

import httpx

from pipeline.ingest.base import BaseConnector

logger = logging.getLogger(__name__)

# URLs: http(s) only, avoid trailing punctuation
URL_RE = re.compile(
    r"https?://[^\s<>\"{}|\\^`\[\]\)]+",
    re.IGNORECASE,
)


def _text_from_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300_000]


def _extract_urls(text: str) -> list[str]:
    """Return unique URLs found in text (strip trailing punctuation)."""
    seen = set()
    out = []
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:)")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _read_zip_text(zip_path: str | Path) -> list[tuple[str, str]]:
    """Read .txt files from zip. Returns list of (filename, content)."""
    path = Path(zip_path)
    if not path.is_file():
        return []
    out = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/") or not name.lower().endswith(".txt"):
                    continue
                try:
                    raw = zf.read(name)
                    text = raw.decode("utf-8", errors="replace").strip()
                    if len(text) > 50:
                        out.append((name, text))
                except Exception as e:
                    logger.warning("Zip read %s: %s", name, e)
    except Exception as e:
        logger.warning("Zip open %s: %s", path, e)
    return out


class ZipConnector(BaseConnector):
    """
    Ingest from a ZIP (e.g. WhatsApp export): extract .txt files, collect URLs from content,
    optionally fetch those URLs. Produces one doc per .txt and one per fetched URL.
    """

    source_type = "zip"

    def __init__(
        self,
        zip_path: str | Path,
        fetch_urls: bool = True,
        max_urls_to_fetch: int = 200,
        institution: str = "SSA",
        document_type: str = "documento",
        country: str = "México",
    ):
        self.zip_path = Path(zip_path)
        self.fetch_urls = fetch_urls
        self.max_urls_to_fetch = max_urls_to_fetch
        self.institution = institution
        self.document_type = document_type
        self.country = country

    def fetch(self) -> list[dict[str, Any]]:
        raw_list: list[dict[str, Any]] = []
        txt_files = _read_zip_text(self.zip_path)
        all_urls: set[str] = set()

        for name, content in txt_files:
            raw_list.append({
                "url": "",
                "title": Path(name).name,
                "raw_text": content[:500_000],
                "institution": self.institution,
                "document_type": self.document_type,
                "country": self.country,
                "source_file": name,
            })
            for u in _extract_urls(content):
                all_urls.add(u)

        if self.fetch_urls and all_urls:
            urls_to_fetch = list(all_urls)[: self.max_urls_to_fetch]
            fetched = 0
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                for url in urls_to_fetch:
                    if fetched >= self.max_urls_to_fetch:
                        break
                    try:
                        r = client.get(url)
                        r.raise_for_status()
                        body = r.text
                    except Exception as e:
                        logger.debug("Zip URL fetch %s: %s", url[:60], e)
                        continue
                    ct = r.headers.get("content-type", "")
                    if "text/html" in ct:
                        text = _text_from_html(body)
                    else:
                        text = body[:300_000] if isinstance(body, str) else body.decode("utf-8", errors="replace")[:300_000]
                    if len(text) < 100:
                        continue
                    raw_list.append({
                        "url": url,
                        "title": url.split("/")[-1].split("?")[0] or url[:80],
                        "raw_text": text[:300_000],
                        "institution": self.institution,
                        "document_type": self.document_type,
                        "country": self.country,
                        "source_file": "",
                    })
                    fetched += 1
            logger.info("Zip: %d txt files, %d URLs fetched from chat", len(txt_files), fetched)

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
