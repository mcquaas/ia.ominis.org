"""Index chunks: write to health_chunks (PG), FAISS (file -> S3), OpenSearch."""

import json
import logging
import os
import tempfile
from typing import Any

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

from pipeline import config as pipeline_config

logger = logging.getLogger(__name__)


def _write_chunks_to_pg(chunks: list[dict[str, Any]]) -> None:
    conn = psycopg2.connect(pipeline_config.DATABASE_URL_SYNC)
    cur = conn.cursor()
    try:
        # Delete existing chunks for doc_ids we're re-indexing to avoid duplicates when re-running
        doc_ids = list({c["doc_id"] for c in chunks})
        for doc_id in doc_ids:
            cur.execute("DELETE FROM health_chunks WHERE doc_id = %s", (doc_id,))
        rows = []
        for c in chunks:
            rows.append((
                c["chunk_id"],
                c["doc_id"],
                (c.get("section") or "")[:256],
                (c.get("chunk_text") or "")[:500000],
                c.get("token_count"),
                (c.get("disease") or "")[:256],
                (c.get("institution") or "")[:256],
                (c.get("state") or "")[:64],
                c.get("year"),
                (c.get("document_type") or "")[:64],
                (c.get("country") or "")[:64],
                (c.get("evidence_level") or "")[:32],
                (c.get("classifier_tag") or "")[:32],
            ))
        execute_values(
            cur,
            """INSERT INTO health_chunks (chunk_id, doc_id, section, chunk_text, token_count, disease, institution, state, year, document_type, country, evidence_level, classifier_tag)
               VALUES %s ON CONFLICT (chunk_id) DO UPDATE SET chunk_text = EXCLUDED.chunk_text, token_count = EXCLUDED.token_count""",
            rows,
            page_size=500,
        )
        conn.commit()
        logger.info("Wrote %d rows to health_chunks", len(rows))
    finally:
        cur.close()
        conn.close()


def _build_faiss_and_upload(chunks: list[dict[str, Any]]) -> None:
    if not chunks or not all(c.get("embedding") for c in chunks):
        logger.warning("No embeddings; skipping FAISS build")
        return
    try:
        import faiss
    except ImportError:
        logger.warning("faiss not installed; skipping FAISS. pip install faiss-cpu")
        return
    vectors = np.array([c["embedding"] for c in chunks], dtype=np.float32)
    n, dim = vectors.shape
    faiss.normalize_L2(vectors)
    id_list_new = [c["chunk_id"] for c in chunks]
    index = faiss.IndexFlatIP(dim)
    existing_ids = []
    try:
        import boto3
        s3 = boto3.client("s3", region_name=pipeline_config.AWS_REGION)
        bucket = pipeline_config.HEALTH_FAISS_S3_BUCKET
        prefix = pipeline_config.HEALTH_FAISS_S3_PREFIX
        with tempfile.TemporaryDirectory() as tmp:
            path_existing_idx = os.path.join(tmp, "existing.faiss")
            path_existing_ids = os.path.join(tmp, "existing_ids.json")
            try:
                s3.download_file(bucket, f"{prefix}/index.faiss", path_existing_idx)
                s3.download_file(bucket, f"{prefix}/chunk_ids.json", path_existing_ids)
                existing_index = faiss.read_index(path_existing_idx)
                with open(path_existing_ids) as f:
                    existing_ids = json.load(f)
                index.add(existing_index.reconstruct_n(0, existing_index.ntotal))
                logger.info("Loaded existing FAISS: %d vectors", existing_index.ntotal)
            except Exception as e:
                logger.info("No existing FAISS or download failed: %s", e)
            index.add(vectors)
            id_list = existing_ids + id_list_new
    except Exception as e:
        logger.warning("S3 download failed, building from current chunks only: %s", e)
        index.add(vectors)
        id_list = id_list_new
    with tempfile.TemporaryDirectory() as tmp:
        path_idx = os.path.join(tmp, "index.faiss")
        path_ids = os.path.join(tmp, "chunk_ids.json")
        faiss.write_index(index, path_idx)
        with open(path_ids, "w") as f:
            json.dump(id_list, f)
        try:
            import boto3
            s3 = boto3.client("s3", region_name=pipeline_config.AWS_REGION)
            bucket = pipeline_config.HEALTH_FAISS_S3_BUCKET
            prefix = pipeline_config.HEALTH_FAISS_S3_PREFIX
            s3.upload_file(path_idx, bucket, f"{prefix}/index.faiss")
            s3.upload_file(path_ids, bucket, f"{prefix}/chunk_ids.json")
            logger.info("Uploaded FAISS index to s3://%s/%s/ (%d vectors)", bucket, prefix, len(id_list))
        except Exception as e:
            logger.warning("S3 upload failed (save locally): %s", e)
            local_dir = pipeline_config.PIPELINE_ROOT / "faiss_out"
            local_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy(path_idx, local_dir / "index.faiss")
            with open(local_dir / "chunk_ids.json", "w") as f:
                json.dump(id_list, f)


def _index_opensearch(chunks: list[dict[str, Any]]) -> None:
    url = (pipeline_config.OPENSEARCH_URL or "").strip()
    if not url:
        logger.warning("OPENSEARCH_URL not set; skipping OpenSearch index")
        return
    index_name = pipeline_config.OPENSEARCH_INDEX
    try:
        from opensearchpy import OpenSearch, RequestsHttpConnection
    except ImportError:
        logger.warning("opensearch-py not installed; pip install opensearch-py")
        return
    # Parse URL: https://xxx.es.amazonaws.com -> host without path
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    auth = None
    if pipeline_config.OPENSEARCH_AUTH:
        user, _, passwd = pipeline_config.OPENSEARCH_AUTH.partition(":")
        auth = (user, passwd)
    client = OpenSearch(
        hosts=[host],
        http_auth=auth,
        use_ssl=pipeline_config.OPENSEARCH_USE_SSL,
        verify_certs=pipeline_config.OPENSEARCH_VERIFY_CERTS,
        connection_class=RequestsHttpConnection,
    )
    # Create index if not exists (simple mapping)
    if not client.indices.exists(index_name):
        client.indices.create(
            index_name,
            body={
                "settings": {"number_of_shards": 1},
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "doc_id": {"type": "keyword"},
                        "chunk_text": {"type": "text"},
                        "title": {"type": "text"},
                        "section": {"type": "keyword"},
                        "institution": {"type": "keyword"},
                        "country": {"type": "keyword"},
                        "year": {"type": "integer"},
                        "document_type": {"type": "keyword"},
                        "disease": {"type": "keyword"},
                    }
                },
            },
        )
    # Bulk index
    from opensearchpy import helpers
    def gen():
        for c in chunks:
            yield {
                "_index": index_name,
                "_id": c["chunk_id"],
                "_source": {
                    "chunk_id": c["chunk_id"],
                    "doc_id": c["doc_id"],
                    "chunk_text": c.get("chunk_text", ""),
                    "title": c.get("title", ""),
                    "section": c.get("section", ""),
                    "institution": c.get("institution", ""),
                    "country": c.get("country", ""),
                    "year": c.get("year"),
                    "document_type": c.get("document_type", ""),
                    "disease": c.get("disease", ""),
                },
                }
    success, failed = helpers.bulk(client, gen(), raise_on_error=False, request_timeout=60)
    logger.info("OpenSearch bulk: %d ok, %d failed", success, len(failed) if failed else 0)


def index_chunks(chunks: list[dict[str, Any]]) -> None:
    """Write chunks to PostgreSQL, build FAISS and upload to S3, bulk index OpenSearch."""
    _write_chunks_to_pg(chunks)
    _build_faiss_and_upload(chunks)
    _index_opensearch(chunks)
