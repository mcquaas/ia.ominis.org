"""PubMed connector via NCBI E-utilities. Fetches health-related articles."""

import hashlib
import logging
import time
import uuid
from typing import Any

import httpx

from pipeline.ingest.base import BaseConnector

logger = logging.getLogger(__name__)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_QUERY = "health Mexico[affiliation] OR public health[mesh] OR clinical guidelines[tiab]"
MAX_RETRIES = 3
DELAY = 0.4  # respect NCBI rate limits


class PubMedConnector(BaseConnector):
    source_type = "PubMed"

    def __init__(self, query: str = DEFAULT_QUERY, max_results: int = 500, email: str = ""):
        self.query = query
        self.max_results = max_results
        self.email = email or "ominis@example.com"

    def fetch(self) -> list[dict[str, Any]]:
        raw_list: list[dict[str, Any]] = []
        try:
            # Search and get ID list
            with httpx.Client(timeout=30) as client:
                r = client.get(
                    f"{EUTILS}/esearch.fcgi",
                    params={
                        "db": "pubmed",
                        "term": self.query,
                        "retmax": min(self.max_results, 10000),
                        "retmode": "json",
                        "email": self.email,
                    },
                )
                r.raise_for_status()
                data = r.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                logger.info("PubMed: no IDs returned for query %s", self.query[:50])
                return raw_list

            # Fetch summaries in batches of 200
            batch_size = 200
            for i in range(0, len(id_list), batch_size):
                batch_ids = id_list[i : i + batch_size]
                time.sleep(DELAY)
                with httpx.Client(timeout=60) as client:
                    r = client.get(
                        f"{EUTILS}/esummary.fcgi",
                        params={"db": "pubmed", "id": ",".join(batch_ids), "retmode": "json"},
                    )
                    r.raise_for_status()
                    data = r.json()
                result = data.get("result", {})
                for pmid in batch_ids:
                    if pmid == "ERROR":
                        continue
                    item = result.get(pmid)
                    if not item:
                        continue
                    title = item.get("title", "")
                    if not title:
                        continue
                    raw_list.append({
                        "pmid": pmid,
                        "title": title,
                        "year": None,
                        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "abstract": item.get("abstract", ""),
                        "authors": item.get("authors", []),
                        "source_type": self.source_type,
                    })
        except Exception as e:
            logger.exception("PubMed fetch failed: %s", e)
        return raw_list

    def parse(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        content = (raw.get("abstract") or "") or (raw.get("title") or "")
        if not content.strip():
            return None
        doc_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
        year = raw.get("year")
        if not year and raw.get("pubdate"):
            try:
                year = int(str(raw["pubdate"])[:4])
            except (ValueError, TypeError):
                pass
        return {
            "doc_id": doc_id,
            "title": raw.get("title", ""),
            "year": year,
            "country": "",
            "institution": "PubMed",
            "document_type": "estudio",
            "medical_specialty": "",
            "population": "",
            "state": "",
            "source_url": raw.get("source_url", ""),
            "source_type": raw.get("source_type", self.source_type),
            "raw_text": (raw.get("abstract") or "").strip() or raw.get("title", ""),
            "content_hash": content_hash,
        }
