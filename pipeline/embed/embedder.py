"""Generate embeddings for chunks. Uses HEALTH_EMBEDDING_MODEL (e.g. all-MiniLM or bge-m3)."""

import logging
from typing import Any

from pipeline import config as pipeline_config

logger = logging.getLogger(__name__)


def embed_chunks(chunks: list[dict[str, Any]], batch_size: int = 64) -> list[dict[str, Any]]:
    """Add 'embedding' (list of float) to each chunk. Modifies in place and returns chunks."""
    if not chunks:
        return chunks
    model_name = pipeline_config.HEALTH_EMBEDDING_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        dim = pipeline_config.HEALTH_EMBEDDING_DIM
        texts = [c.get("chunk_text", "") or "" for c in chunks]
        embs = model.encode(texts, batch_size=batch_size, show_progress_bar=True)
        for i, c in enumerate(chunks):
            c["embedding"] = embs[i].tolist()
        logger.info("Embedded %d chunks with %s (dim=%s)", len(chunks), model_name, embs.shape[1])
        return chunks
    except Exception as e:
        logger.exception("Embedding failed: %s", e)
        raise
