"""
Document store using Haystack's PgvectorDocumentStore.

Persistent storage in PostgreSQL with pgvector extension.
Reuses the same PostgreSQL instance used for users/logs/rag_sources.
"""

import json
import logging
import re
from typing import Optional

from haystack import Document
from haystack.utils import Secret
from haystack_integrations.document_stores.pgvector import PgvectorDocumentStore

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global singleton
_document_store: Optional[PgvectorDocumentStore] = None


def _build_pgvector_conn_str() -> str:
    """
    Convert the async database URL to a sync connection string for pgvector.
    e.g. postgresql+asyncpg://user:pass@host:5432/db
      -> postgresql://user:pass@host:5432/db
    """
    url = settings.database_url
    # Strip any SQLAlchemy driver prefix
    url = re.sub(r"postgresql\+\w+://", "postgresql://", url)
    return url


def get_document_store() -> PgvectorDocumentStore:
    """Get the global PgvectorDocumentStore (creates if needed)."""
    global _document_store
    if _document_store is None:
        conn_str = _build_pgvector_conn_str()
        logger.info(f"Initializing PgvectorDocumentStore (dim={settings.embedding_dimension})")
        _document_store = PgvectorDocumentStore(
            connection_string=Secret.from_token(conn_str),
            table_name="haystack_documents",
            embedding_dimension=settings.embedding_dimension,
            vector_function="cosine_similarity",
            recreate_table=False,  # Preserve data across restarts
            search_strategy="hnsw",
            hnsw_recreate_index_if_exists=False,
        )
    return _document_store


async def migrate_chunks_from_s3() -> int:
    """
    One-time migration: load existing chunks from S3 into PgvectorDocumentStore.
    Only imports chunks that don't already exist.
    Returns the number of documents imported.
    """
    import boto3

    store = get_document_store()
    existing_count = store.count_documents()

    if existing_count > 0:
        logger.info(
            f"PgvectorDocumentStore already has {existing_count} documents. "
            "Skipping S3 migration."
        )
        return existing_count

    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        key = f"{settings.vector_prefix}/chunks.json"

        logger.info(f"Migrating chunks from s3://{settings.embeddings_bucket}/{key}")

        response = s3.get_object(
            Bucket=settings.embeddings_bucket,
            Key=key,
        )
        chunks = json.loads(response["Body"].read().decode("utf-8"))

        logger.info(f"Loaded {len(chunks)} chunks from S3, importing to pgvector...")

        documents = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc = Document(
                content=chunk.get("content", ""),
                meta={
                    "title": metadata.get("title", "Sin título"),
                    "url": metadata.get("url", ""),
                    "source_type": metadata.get("source_type", "rag"),
                    "category": metadata.get("category", ""),
                    "language": metadata.get("language", "es"),
                },
            )
            documents.append(doc)

        if documents:
            # Documents need to be embedded before writing to pgvector
            if (getattr(settings, "embedding_service_url", None) or "").strip():
                from app.rag.embedder import ExternalDocumentEmbedder
                embedder = ExternalDocumentEmbedder()
                embedder.warm_up()
            else:
                from haystack.components.embedders import SentenceTransformersDocumentEmbedder
                embedder = SentenceTransformersDocumentEmbedder(model=settings.embedding_model)
                embedder.warm_up()
            result = embedder.run(documents=documents)
            embedded_docs = result["documents"]

            store.write_documents(embedded_docs)
            logger.info(f"Migrated {len(embedded_docs)} documents to PgvectorDocumentStore")
            return len(embedded_docs)

        return 0

    except Exception as e:
        logger.warning(f"S3 migration skipped: {e}")
        logger.info("Starting with current pgvector contents.")
        return store.count_documents()
