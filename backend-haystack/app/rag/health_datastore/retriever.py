"""Hybrid retrieval from health datastore: FAISS + OpenSearch, with score boosting."""

import json
import logging
import os
import tempfile
import time
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_faiss_index = None
_chunk_ids_list: list[str] | None = None
_faiss_loaded_at: float = 0  # when we last loaded from S3
FAISS_CACHE_TTL_SECONDS = 300  # reload from S3 every 5 min so new pipeline runs are visible


def _load_faiss():
    """Load FAISS index from S3 or local path. From S3: reload when TTL expires so new ingest is visible."""
    global _faiss_index, _chunk_ids_list, _faiss_loaded_at
    settings = get_settings()
    path = (settings.health_faiss_path or "").strip()
    if path and os.path.isfile(os.path.join(path, "index.faiss")):
        if _faiss_index is not None:
            return _faiss_index, _chunk_ids_list or []
        import faiss
        _faiss_index = faiss.read_index(os.path.join(path, "index.faiss"))
        ids_path = os.path.join(path, "chunk_ids.json")
        if os.path.isfile(ids_path):
            with open(ids_path) as f:
                _chunk_ids_list = json.load(f)
        else:
            _chunk_ids_list = []
        return _faiss_index, _chunk_ids_list or []
    bucket = (settings.health_faiss_s3_bucket or "").strip()
    if not bucket:
        logger.warning("Health datastore: no health_faiss_path or health_faiss_s3_bucket")
        return None, []
    # From S3: allow cache refresh so backend sees new index after pipeline runs
    now = time.time()
    if _faiss_index is not None and (now - _faiss_loaded_at) < FAISS_CACHE_TTL_SECONDS:
        return _faiss_index, _chunk_ids_list or []
    try:
        import boto3
        import faiss
        s3 = boto3.client("s3", region_name=getattr(settings, "aws_region", "us-east-1"))
        prefix = (settings.health_faiss_s3_prefix or "health-datastore/faiss").strip()
        with tempfile.TemporaryDirectory() as tmp:
            idx_path = os.path.join(tmp, "index.faiss")
            ids_path = os.path.join(tmp, "chunk_ids.json")
            s3.download_file(bucket, f"{prefix}/index.faiss", idx_path)
            s3.download_file(bucket, f"{prefix}/chunk_ids.json", ids_path)
            _faiss_index = faiss.read_index(idx_path)
            with open(ids_path) as f:
                _chunk_ids_list = json.load(f)
        _faiss_loaded_at = now
        return _faiss_index, _chunk_ids_list or []
    except Exception as e:
        logger.warning("Health datastore: could not load FAISS from S3: %s", e)
        return None, []


def _query_opensearch(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    settings = get_settings()
    url = (settings.opensearch_url or "").strip()
    if not url:
        return []
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    auth = None
    if settings.opensearch_auth:
        user, _, passwd = settings.opensearch_auth.partition(":")
        auth = (user, passwd)
    try:
        from opensearchpy import OpenSearch, RequestsHttpConnection
        client = OpenSearch(
            hosts=[host],
            http_auth=auth,
            use_ssl=parsed.scheme == "https",
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        index_name = settings.opensearch_index or "health-chunks"
        resp = client.search(
            index=index_name,
            body={
                "size": top_k,
                "query": {"multi_match": {"query": query, "fields": ["chunk_text", "title", "section"]}},
            },
        )
        hits = resp.get("hits", {}).get("hits", [])
        return [{"_id": h["_id"], **(h.get("_source") or {})} for h in hits]
    except Exception as e:
        logger.warning("OpenSearch query failed: %s", e)
        return []


def _get_metadata_for_chunk_ids(chunk_ids: list[str]) -> dict[str, dict]:
    """Fetch metadata from PostgreSQL health_docs + health_chunks for citation."""
    if not chunk_ids:
        return {}
    settings = get_settings()
    try:
        import psycopg2
        import re
        url = getattr(settings, "database_url_sync", "") or (settings.database_url or "")
        url = re.sub(r"postgresql\+\w+://", "postgresql://", url)
        if not url:
            return {}
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """SELECT c.chunk_id, c.chunk_text, c.institution, c.year, c.document_type, c.country, d.title, d.source_url
               FROM health_chunks c
               JOIN health_docs d ON d.doc_id = c.doc_id
               WHERE c.chunk_id = ANY(%s)""",
            (chunk_ids,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        key_to_cols = ["chunk_id", "chunk_text", "institution", "year", "document_type", "country", "title", "source_url"]
        return {row[0]: dict(zip(key_to_cols, row)) for row in rows}
    except Exception as e:
        logger.warning("Health datastore metadata lookup failed: %s", e)
        return {}


def _embed_query(query: str) -> list[float] | None:
    """Embed query using same model as pipeline (backend embedder)."""
    from app.rag.pipeline import get_pipeline_manager
    try:
        manager = get_pipeline_manager()
        embedder = manager.get_text_embedder()
        out = embedder.run(text=query)
        emb = out.get("embedding")
        if emb is None:
            return None
        return emb if isinstance(emb, list) else emb.tolist()
    except Exception as e:
        logger.warning("Health datastore query embed failed: %s", e)
        return None


def build_evidence_pack(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    """
    Hybrid retrieve from health datastore: FAISS (vector) + OpenSearch (BM25), merge and apply boosting.
    Returns list of {chunk_text, citation, metadata} for OpenScholar.
    """
    settings = get_settings()
    if not settings.health_datastore_enabled:
        return []
    results = []
    seen_ids = set()
    # Vector search
    index, id_list = _load_faiss()
    if index is not None and id_list:
        query_emb = _embed_query(query)
        if query_emb is not None:
            import numpy as np
            import faiss
            dim = len(query_emb)
            if index.d != dim:
                logger.warning("Health datastore: embedding dim %d != index dim %d", dim, index.d)
            else:
                x = np.array([query_emb], dtype=np.float32)
                faiss.normalize_L2(x)
                scores, indices = index.search(x, min(top_k * 2, index.ntotal))
                for j, idx in enumerate(indices[0]):
                    if idx < 0 or idx >= len(id_list):
                        continue
                    cid = id_list[idx]
                    if cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    score = float(scores[0][j]) if scores.size else 0.0
                    results.append({"chunk_id": cid, "score": score, "source": "vector"})
    # BM25 from OpenSearch
    os_hits = _query_opensearch(query, top_k=top_k * 2)
    for h in os_hits:
        cid = h.get("_id") or h.get("chunk_id")
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)
        results.append({"chunk_id": cid, "score": 0.5, "source": "bm25"})
    # Fetch metadata and build citation
    all_ids = [r["chunk_id"] for r in results]
    meta_map = _get_metadata_for_chunk_ids(all_ids)
    # Apply boosting
    current_year = __import__("datetime").datetime.utcnow().year
    def boosted_score(r):
        s = r.get("score", 0) or 0
        meta = meta_map.get(r["chunk_id"]) or {}
        if (meta.get("country") or "").lower() in ("méxico", "mexico", "mx"):
            s += settings.health_boost_country_mexico
        year = meta.get("year")
        if year is not None and (current_year - int(year)) <= 5:
            s += settings.health_boost_year_recent
        if (meta.get("document_type") or "").upper() in ("NOM", "GPC"):
            s += settings.health_boost_nom_gpc
        return s
    results.sort(key=boosted_score, reverse=True)
    # Build evidence pack
    out = []
    for r in results[:top_k]:
        cid = r["chunk_id"]
        meta = meta_map.get(cid) or {}
        chunk_text = meta.get("chunk_text", "")
        if not chunk_text:
            continue
        inst = meta.get("institution", "")
        year = meta.get("year", "")
        doc_type = meta.get("document_type", "")
        title = meta.get("title", "")
        citation = f"{inst} {year} {doc_type}".strip() or title or cid
        out.append({
            "chunk_text": chunk_text,
            "citation": citation,
            "metadata": {k: v for k, v in meta.items() if v is not None and v != ""},
        })
    return out
