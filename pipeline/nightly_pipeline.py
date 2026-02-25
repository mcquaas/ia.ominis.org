#!/usr/bin/env python3
"""
Nightly Mexican Health Datastore Pipeline.
Run from repo root: PYTHONPATH=. python pipeline/nightly_pipeline.py --full
Or: python -m pipeline.nightly_pipeline --full
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure repo root is on path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline import config as pipeline_config
from pipeline.chunk.semantic_chunker import semantic_chunk_docs
from pipeline.embed.embedder import embed_chunks
from pipeline.index.indexer import index_chunks
from pipeline.ingest.pubmed_connector import PubMedConnector
from pipeline.ingest.url_connector import UrlListConnector
from pipeline.ingest.crawl_connector import UrlCrawlConnector
from pipeline.ingest.zip_connector import ZipConnector
from pipeline.normalize.normalizer import normalize_and_store_docs
from pipeline.reports.reporter import write_report

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
# Reduce noise from HTTP clients (enable DEBUG only with DEBUG=1)
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# Optional: log to file
try:
    pipeline_config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    log_file = pipeline_config.LOGS_DIR / f"nightly_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)
except Exception:
    pass


def _load_unchunked_docs_from_pg() -> list:
    """Load health_docs that have no rows in health_chunks (for backfill). Returns list of doc dicts."""
    import psycopg2
    conn = psycopg2.connect(pipeline_config.DATABASE_URL_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT d.doc_id, d.title, d.year, d.country, d.institution, d.document_type, d.state, d.source_url, d.source_type, d.raw_text
        FROM health_docs d
        LEFT JOIN health_chunks c ON c.doc_id = d.doc_id
        WHERE c.chunk_id IS NULL AND (d.raw_text IS NOT NULL AND length(trim(d.raw_text)) > 0)
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    docs = [
        {
            "doc_id": r[0],
            "title": r[1] or "",
            "year": r[2],
            "country": r[3] or "",
            "institution": r[4] or "",
            "document_type": r[5] or "",
            "state": r[6] or "",
            "source_url": r[7] or "",
            "source_type": r[8] or "",
            "raw_text": r[9] or "",
        }
        for r in rows
    ]
    logger.info("Loaded %d unchunked health_docs from PostgreSQL", len(docs))
    return docs


def _load_raw_docs_from_s3() -> list:
    """Load all raw doc JSONs from S3 (written by ingest Lambdas). Returns list of doc dicts."""
    import json
    import boto3
    bucket = pipeline_config.PIPELINE_RAW_BUCKET
    prefix = pipeline_config.PIPELINE_RAW_PREFIX
    region = pipeline_config.AWS_REGION
    s3 = boto3.client("s3", region_name=region)
    paginator = s3.get_paginator("list_objects_v2")
    all_docs = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            try:
                resp = s3.get_object(Bucket=bucket, Key=key)
                docs = json.loads(resp["Body"].read().decode("utf-8"))
                if isinstance(docs, list):
                    all_docs.extend(docs)
                else:
                    all_docs.append(docs)
            except Exception as e:
                logger.warning("Failed to load s3://%s/%s: %s", bucket, key, e)
    logger.info("Loaded %d raw docs from s3://%s/%s", len(all_docs), bucket, prefix)
    return all_docs


def get_connectors(full: bool, source_filter: str | None, zip_path: str | Path | None = None) -> list:
    connectors = []
    if zip_path:
        from pathlib import Path
        p = Path(zip_path)
        if p.is_file():
            connectors.append(ZipConnector(
                zip_path=p,
                fetch_urls=True,
                max_urls_to_fetch=200,
                institution="SSA",
                document_type="documento",
                country="México",
            ))
        else:
            logger.warning("Zip path not a file: %s", zip_path)
        return connectors

    if full or not source_filter or source_filter == "pubmed":
        queries = getattr(pipeline_config, "PUBMED_QUERIES_MEXICAN_HEALTH", None) or [
            "Mexico[affiliation] OR public health[mesh] OR clinical guidelines[tiab]",
        ]
        max_per_query = min(200, 4000 // len(queries))  # scale with number of queries
        for q in queries:
            connectors.append(PubMedConnector(query=q, max_results=max_per_query))
    if full or source_filter in ("url", "url_list", "mexico"):
        urls = getattr(pipeline_config, "MEXICAN_HEALTH_URLS", None) or [
            "https://www.gob.mx/salud",
            "https://www.imss.gob.mx",
        ]
        connectors.append(UrlListConnector(
            urls=urls,
            institution="SSA",
            document_type="documento",
            country="México",
        ))
    if full or source_filter == "crawl":
        seeds = getattr(pipeline_config, "CRAWL_SEED_URLS", None) or ["https://www.gob.mx/salud"]
        max_pages = getattr(pipeline_config, "CRAWL_MAX_PAGES", None) or 50
        connectors.append(UrlCrawlConnector(
            seed_urls=seeds,
            max_pages=max_pages,
            same_domain_only=True,
            institution="SSA",
            document_type="documento",
            country="México",
        ))
    return connectors


def run_pipeline(full: bool = True, source: str | None = None, from_s3: bool = False, backfill: bool = False, zip_path: str | None = None) -> None:
    if backfill:
        stored = _load_unchunked_docs_from_pg()
        if not stored:
            logger.info("No unchunked health_docs to backfill")
            write_report()
            return
        logger.info("Backfill: chunking %d docs that have no health_chunks", len(stored))
        chunks = semantic_chunk_docs(stored)
        if not chunks:
            logger.warning("No chunks produced")
            write_report()
            return
        logger.info("Embedding %d chunks", len(chunks))
        embed_chunks(chunks)
        logger.info("Indexing (PG, FAISS, OpenSearch)")
        index_chunks(chunks)
        write_report()
        logger.info("Backfill finished.")
        return

    if from_s3:
        all_docs = _load_raw_docs_from_s3()
    else:
        all_docs = []
        for conn in get_connectors(full, source, zip_path=zip_path):
            logger.info("Running connector: %s", conn.source_type)
            for doc in conn.run():
                all_docs.append(doc)

    if not all_docs:
        logger.warning("No documents from connectors or S3")
        if not from_s3:
            write_report()
        return
    # Ensure content_hash for dedup (Lambda output may not have it)
    import hashlib
    for d in all_docs:
        if not d.get("content_hash") and d.get("raw_text"):
            d["content_hash"] = hashlib.sha256((d.get("raw_text") or "").encode("utf-8")).hexdigest()[:32]

    logger.info("Normalizing and storing %d docs", len(all_docs))
    stored = normalize_and_store_docs(all_docs)
    if not stored:
        logger.info("No new docs to chunk (all duplicates)")
        write_report()
        return
    chunks = semantic_chunk_docs(stored)
    if not chunks:
        logger.warning("No chunks produced")
        write_report()
        return
    logger.info("Embedding %d chunks", len(chunks))
    embed_chunks(chunks)
    logger.info("Indexing (PG, FAISS, OpenSearch)")
    index_chunks(chunks)
    write_report()
    logger.info("Nightly pipeline finished.")


def main():
    parser = argparse.ArgumentParser(description="Nightly Mexican Health Datastore Pipeline")
    parser.add_argument("--full", action="store_true", help="Full run (all sources)")
    parser.add_argument("--incremental", action="store_true", help="Incremental (same as full for now; dedup by content_hash)")
    parser.add_argument("--source", type=str, default=None, help="Only run this source: pubmed | url_list | crawl")
    parser.add_argument("--zip", dest="zip_path", type=str, default=None, help="Path to ZIP (e.g. WhatsApp export); ingests .txt and fetches URLs found")
    parser.add_argument("--from-s3", action="store_true", help="Read raw docs from S3 (from ingest Lambdas) instead of running connectors")
    parser.add_argument("--backfill", action="store_true", help="Chunk/embed/index health_docs that have no health_chunks (run on worker)")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    run_pipeline(full=args.full or args.incremental, source=args.source, from_s3=args.from_s3, backfill=args.backfill, zip_path=args.zip_path)


if __name__ == "__main__":
    main()
