"""
Document store initialization and S3 data loading.
Loads existing chunks from S3 into Haystack's InMemoryDocumentStore.
"""

import json
import logging
from typing import Optional

import boto3
from haystack import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global singleton
_document_store: Optional[InMemoryDocumentStore] = None


def get_document_store() -> InMemoryDocumentStore:
    """Get the global document store (must be initialized first)."""
    global _document_store
    if _document_store is None:
        _document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")
    return _document_store


async def load_chunks_from_s3() -> int:
    """
    Load existing chunks from S3 into the InMemoryDocumentStore.
    Returns the number of documents loaded.

    The S3 bucket stores:
    - {vector_prefix}/chunks.json: Array of chunk objects with content and metadata
    """
    store = get_document_store()

    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)

        logger.info(
            f"Loading chunks from s3://{settings.embeddings_bucket}/{settings.vector_prefix}/chunks.json"
        )

        response = s3.get_object(
            Bucket=settings.embeddings_bucket,
            Key=f"{settings.vector_prefix}/chunks.json",
        )
        chunks = json.loads(response["Body"].read().decode("utf-8"))

        logger.info(f"Loaded {len(chunks)} chunks from S3, converting to Haystack Documents...")

        documents = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc = Document(
                content=chunk.get("content", ""),
                meta={
                    "title": metadata.get("title", "Sin título"),
                    "url": metadata.get("url", ""),
                    "source_type": metadata.get("source_type", "unknown"),
                    "category": metadata.get("category", ""),
                    "language": metadata.get("language", "es"),
                    "tags": metadata.get("tags", []),
                },
            )
            documents.append(doc)

        # Write documents to the store (embeddings will be computed by the indexing pipeline)
        store.write_documents(documents)
        logger.info(f"Wrote {len(documents)} documents to InMemoryDocumentStore")
        return len(documents)

    except Exception as e:
        logger.warning(f"Could not load chunks from S3: {e}")
        logger.info("Starting with empty document store. Use the indexing pipeline to add documents.")
        return 0


async def load_chunks_from_file(filepath: str) -> int:
    """
    Load chunks from a local JSON file (for development/testing).
    Returns the number of documents loaded.
    """
    store = get_document_store()

    with open(filepath, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    documents = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        doc = Document(
            content=chunk.get("content", ""),
            meta={
                "title": metadata.get("title", "Sin título"),
                "url": metadata.get("url", ""),
                "source_type": metadata.get("source_type", "unknown"),
                "category": metadata.get("category", ""),
                "language": metadata.get("language", "es"),
            },
        )
        documents.append(doc)

    store.write_documents(documents)
    logger.info(f"Loaded {len(documents)} documents from {filepath}")
    return len(documents)
