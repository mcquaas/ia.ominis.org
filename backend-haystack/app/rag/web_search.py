"""
Web search Haystack component using DuckDuckGo (ddgs package).
Returns search results as Haystack Document objects.
"""

import logging
from typing import Optional

from haystack import Document, component

logger = logging.getLogger(__name__)


@component
class WebSearchComponent:
    """
    Haystack component that searches the web using DuckDuckGo.
    Returns a list of Documents with source_type="web".
    """

    def __init__(self, region: str = "mx-es", safesearch: str = "moderate"):
        self.region = region
        self.safesearch = safesearch

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int = 5) -> dict:
        """Search the web and return Documents."""
        try:
            from ddgs import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(
                    query,
                    region=self.region,
                    safesearch=self.safesearch,
                    max_results=top_k,
                ):
                    title = r.get("title", "Sin título")
                    url = r.get("href", "")
                    body = r.get("body", "")

                    if not url or not body:
                        continue

                    doc = Document(
                        content=body,
                        meta={
                            "title": title,
                            "url": url,
                            "source_type": "web",
                        },
                    )
                    results.append(doc)

            logger.info(f"WebSearch for '{query[:50]}' returned {len(results)} results")
            return {"documents": results}

        except ImportError:
            logger.error("ddgs is not installed. Run: pip install ddgs")
            return {"documents": []}
        except Exception as e:
            logger.error(f"Web search error: {e}", exc_info=True)
            return {"documents": []}


# Convenience async wrapper for use in the router
async def search_web(query: str, max_results: int = 5) -> list[Document]:
    """Async wrapper that runs WebSearchComponent in a thread executor."""
    import asyncio

    ws = WebSearchComponent()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: ws.run(query=query, top_k=max_results))
    return result.get("documents", [])
