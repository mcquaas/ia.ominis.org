"""
Open Scholar (Semantic Scholar) search as a Haystack-compatible source.

Uses the Semantic Scholar Academic Graph API (paper relevance search).
Returns results as Haystack Document objects with source_type="openscholar".
API key via SEMANTIC_SCHOLAR_API_KEY (optional; improves rate limits).
See: https://api.semanticscholar.org/api-docs/
"""

import asyncio
import logging
from typing import Optional

import httpx
from haystack import Document, component

from app.config import get_settings

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "paperId,title,url,abstract,authors,year,venue,externalIds"


@component
class OpenScholarSearchComponent:
    """
    Haystack component that searches Semantic Scholar (Open Scholar) for academic papers.
    Returns a list of Documents with source_type="openscholar".
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        self._api_key = (api_key or "").strip() or (get_settings().semantic_scholar_api_key or "").strip()
        self._timeout = timeout

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int = 5) -> dict:
        """Search Semantic Scholar and return Documents."""
        if top_k <= 0:
            return {"documents": []}
        limit = min(top_k, 100)
        headers = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        try:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.get(
                    SEARCH_URL,
                    params={"query": query[:500], "limit": limit, "fields": FIELDS},
                    headers=headers,
                )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"Semantic Scholar API error: {e.response.status_code} {e.response.text[:200]}")
            return {"documents": []}
        except Exception as e:
            logger.error(f"Open Scholar search error: {e}", exc_info=True)
            return {"documents": []}

        papers = data.get("data") or []
        documents = []
        for p in papers:
            title = p.get("title") or "Sin título"
            abstract = p.get("abstract") or ""
            url = p.get("url") or ""
            year = p.get("year")
            authors_list = p.get("authors") or []
            authors_str = ", ".join(a.get("name", "") for a in authors_list if isinstance(a, dict))
            venue = p.get("venue") or ""
            external_ids = p.get("externalIds") or {}
            doi = (external_ids.get("DOI") or external_ids.get("doi") or "").strip() if isinstance(external_ids, dict) else ""
            content = abstract or title
            if not content.strip():
                continue
            meta = {
                "title": title,
                "url": url or f"https://www.semanticscholar.org/paper/{p.get('paperId', '')}",
                "source_type": "openscholar",
                "authors": authors_str,
                "year": str(year) if year is not None else "",
                "venue": venue,
                "doi": doi,
            }
            doc = Document(content=content, meta=meta)
            documents.append(doc)

        logger.info(f"OpenScholar search for '{query[:50]}' returned {len(documents)} results")
        return {"documents": documents}


async def search_openscholar(query: str, max_results: int = 5) -> list[Document]:
    """Async wrapper: run OpenScholarSearchComponent in a thread executor."""
    comp = OpenScholarSearchComponent()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: comp.run(query=query, top_k=max_results))
    return result.get("documents", [])
