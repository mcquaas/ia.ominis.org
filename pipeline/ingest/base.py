"""Base connector for health data sources. All connectors implement fetch, parse, normalize."""

from abc import ABC, abstractmethod
from typing import Any, Iterator


class BaseConnector(ABC):
    """Abstract connector: fetch raw data, parse, normalize to unified doc schema."""

    source_type: str = "generic"

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw items from the source (e.g. API, scrape). Return list of raw items."""
        pass

    def parse(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Parse one raw item into a structured dict. Override if needed."""
        return raw

    def normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize to unified schema: doc_id, title, year, country, institution, document_type, source_url, raw_text, etc."""
        out = {
            "doc_id": item.get("doc_id", ""),
            "title": item.get("title", ""),
            "year": item.get("year"),
            "country": item.get("country", ""),
            "institution": item.get("institution", ""),
            "document_type": item.get("document_type", ""),
            "medical_specialty": item.get("medical_specialty", ""),
            "population": item.get("population", ""),
            "state": item.get("state", ""),
            "source_url": item.get("source_url", ""),
            "source_type": getattr(self, "source_type", item.get("source_type", "generic")),
            "raw_text": item.get("raw_text", item.get("content", item.get("abstract", ""))),
            "content_hash": item.get("content_hash", ""),
        }
        return {k: (v or "") if isinstance(v, str) else v for k, v in out.items()}

    def run(self) -> Iterator[dict[str, Any]]:
        """Fetch, parse, normalize and yield normalized docs."""
        for raw in self.fetch():
            parsed = self.parse(raw)
            if parsed is None:
                continue
            yield self.normalize(parsed)
