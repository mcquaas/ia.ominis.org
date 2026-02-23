"""
Optional external embedding service (e.g. bge on RTX 4090).
When EMBEDDING_SERVICE_URL is set, query and document embedding use this instead of SentenceTransformers.
API contract: POST {url}/embed with {"texts": ["a", "b"]} -> {"embeddings": [[...], [...]]}.
EMBEDDING_DIMENSION must match the service output.
"""

import logging
from typing import Any

import httpx
from haystack.dataclasses import Document

from app.config import get_settings

logger = logging.getLogger(__name__)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call external embedding API. Returns list of embedding vectors."""
    settings = get_settings()
    url = (settings.embedding_service_url or "").rstrip("/")
    if not url:
        raise RuntimeError("embedding_service_url not set")
    endpoint = f"{url}/embed"
    payload = {"texts": texts}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
    # Support {"embeddings": [[...], ...]} or OpenAI-style {"data": [{"embedding": [...]}, ...]}
    if "embeddings" in data:
        return data["embeddings"]
    if "data" in data and isinstance(data["data"], list):
        return [item["embedding"] for item in data["data"] if "embedding" in item]
    raise ValueError(f"Unexpected embedding response shape: {list(data.keys())}")


class ExternalTextEmbedder:
    """
    Drop-in replacement for SentenceTransformersTextEmbedder when using an external embedding API.
    run(text: str) -> {"embedding": list[float]}
    """

    def warm_up(self) -> None:
        """Optional: verify service is reachable."""
        try:
            _embed_batch(["ping"])
        except Exception as e:
            logger.warning("External embedder warm-up failed: %s", e)

    def run(self, text: str | list[str]) -> dict[str, Any]:
        """Embed one or more texts. Returns embedding (single) or embeddings (list) to match Haystack."""
        if isinstance(text, str):
            text = [text]
        if not text:
            return {"embedding": [], "embeddings": []}
        vectors = _embed_batch(text)
        if len(vectors) == 1:
            return {"embedding": vectors[0]}
        return {"embeddings": vectors}


class ExternalDocumentEmbedder:
    """
    Drop-in replacement for SentenceTransformersDocumentEmbedder when using an external embedding API.
    run(documents: list[Document]) -> {"documents": list[Document]} with each doc.embedding set.
    """

    def warm_up(self) -> None:
        ExternalTextEmbedder().warm_up()

    def run(self, documents: list[Document]) -> dict[str, list[Document]]:
        if not documents:
            return {"documents": []}
        texts = [d.content or "" for d in documents]
        vectors = _embed_batch(texts)
        for doc, vec in zip(documents, vectors, strict=True):
            doc.embedding = vec
        return {"documents": documents}
