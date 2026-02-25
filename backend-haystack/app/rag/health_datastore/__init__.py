"""Health datastore: hybrid retrieval (FAISS + OpenSearch) for Mexican health evidence. Used by OpenScholar 128K."""

from app.rag.health_datastore.retriever import build_evidence_pack

__all__ = ["build_evidence_pack"]
