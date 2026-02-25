"""Normalize docs and store in PostgreSQL health_docs. Dedupe by content_hash."""

import logging
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

from pipeline import config as pipeline_config

logger = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(pipeline_config.DATABASE_URL_SYNC)


def normalize_and_store_docs(docs: list[dict[str, Any]], source_type: str = "") -> list[dict[str, Any]]:
    """Insert into health_docs, skip duplicates by content_hash. Return list of stored docs (with doc_id)."""
    if not docs:
        return []
    stored = []
    try:
        conn = get_connection()
        cur = conn.cursor()
        existing_hashes = set()
        cur.execute("SELECT content_hash FROM health_docs WHERE content_hash IS NOT NULL")
        for row in cur.fetchall():
            existing_hashes.add(row[0])
        to_insert = []
        for d in docs:
            ch = d.get("content_hash") or ""
            if ch and ch in existing_hashes:
                continue
            doc_id = d.get("doc_id")
            if not doc_id:
                continue
            to_insert.append((
                doc_id,
                (d.get("title") or "")[:4000],
                d.get("year"),
                (d.get("country") or "")[:64],
                (d.get("institution") or "")[:256],
                (d.get("document_type") or "")[:64],
                (d.get("medical_specialty") or "")[:128],
                (d.get("population") or "")[:128],
                (d.get("state") or "")[:64],
                (d.get("source_url") or "")[:4000],
                d.get("source_type", source_type)[:64],
                (d.get("raw_text") or "")[:500_000],
                ch[:64] if ch else None,
            ))
            existing_hashes.add(ch or "")
            stored.append(d)
        if to_insert:
            execute_values(
                cur,
                """INSERT INTO health_docs (doc_id, title, year, country, institution, document_type, medical_specialty, population, state, source_url, source_type, raw_text, content_hash)
                   VALUES %s ON CONFLICT (doc_id) DO NOTHING""",
                to_insert,
                page_size=500,
            )
            conn.commit()
            logger.info("Inserted %d health_docs", len(to_insert))
        cur.close()
        conn.close()
    except Exception as e:
        logger.exception("normalize_and_store_docs failed: %s", e)
        raise
    return stored
