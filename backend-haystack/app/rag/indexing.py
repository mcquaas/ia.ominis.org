"""
Haystack Indexing Pipeline.
Handles chunking, embedding, and storing new documents.
"""

import logging
from typing import Optional

from haystack import Document, Pipeline
from haystack.components.embedders import SentenceTransformersDocumentEmbedder
from haystack.components.preprocessors import DocumentCleaner, DocumentSplitter
from haystack.components.writers import DocumentWriter

from app.config import get_settings
from app.rag.document_store import get_document_store

logger = logging.getLogger(__name__)
settings = get_settings()

_indexing_pipeline: Optional[Pipeline] = None


def build_indexing_pipeline() -> Pipeline:
    """
    Build the Haystack indexing pipeline:
    1. Clean documents (remove empty lines, etc.)
    2. Split into chunks (512 chars with overlap, matching existing chunker)
    3. Embed chunks with SentenceTransformers
    4. Write to the document store
    """
    document_store = get_document_store()

    pipeline = Pipeline()

    # Document cleaner
    cleaner = DocumentCleaner(
        remove_empty_lines=True,
        remove_extra_whitespaces=True,
    )

    # Splitter (matching existing chunker: 512 chars, 50 overlap)
    splitter = DocumentSplitter(
        split_by="sentence",
        split_length=3,  # 3 sentences per chunk
        split_overlap=1,
    )

    # Document embedder
    embedder = SentenceTransformersDocumentEmbedder(
        model=settings.embedding_model,
    )

    # Writer
    writer = DocumentWriter(
        document_store=document_store,
        policy="overwrite",
    )

    pipeline.add_component("cleaner", cleaner)
    pipeline.add_component("splitter", splitter)
    pipeline.add_component("embedder", embedder)
    pipeline.add_component("writer", writer)

    pipeline.connect("cleaner", "splitter")
    pipeline.connect("splitter", "embedder")
    pipeline.connect("embedder", "writer")

    return pipeline


def get_indexing_pipeline() -> Pipeline:
    """Get or create the indexing pipeline."""
    global _indexing_pipeline
    if _indexing_pipeline is None:
        _indexing_pipeline = build_indexing_pipeline()
        _indexing_pipeline.warm_up()
    return _indexing_pipeline


def index_documents(documents: list[Document]) -> int:
    """
    Index a list of Haystack Documents through the pipeline.
    Returns the number of documents written.
    """
    pipeline = get_indexing_pipeline()
    result = pipeline.run({"cleaner": {"documents": documents}})
    written = result.get("writer", {}).get("documents_written", 0)
    logger.info(f"Indexed {written} document chunks")
    return written


def index_raw_text(
    content: str,
    title: str = "",
    url: str = "",
    source_type: str = "manual",
    category: str = "",
    language: str = "es",
) -> int:
    """
    Index raw text content by creating a Document and running it through the pipeline.
    """
    doc = Document(
        content=content,
        meta={
            "title": title,
            "url": url,
            "source_type": source_type,
            "category": category,
            "language": language,
        },
    )
    return index_documents([doc])
