"""Quality metrics for the health datastore."""

import logging
from datetime import datetime
from typing import Any

import psycopg2

from pipeline import config as pipeline_config

logger = logging.getLogger(__name__)


def compute_quality_metrics() -> dict[str, Any]:
    """Query health_docs and health_chunks for metrics."""
    conn = psycopg2.connect(pipeline_config.DATABASE_URL_SYNC)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM health_docs")
        num_docs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM health_chunks")
        num_chunks = cur.fetchone()[0]
        cur.execute(
            """SELECT COUNT(*) FROM health_chunks c
               JOIN health_docs d ON d.doc_id = c.doc_id
               WHERE LOWER(TRIM(d.country)) IN ('méxico', 'mexico', 'mx')"""
        )
        mexican_chunks = cur.fetchone()[0]
        pct_mexican = (mexican_chunks / num_chunks * 100) if num_chunks else 0
        cur.execute("SELECT AVG(EXTRACT(YEAR FROM CURRENT_DATE) - year) FROM health_docs WHERE year IS NOT NULL")
        row = cur.fetchone()
        avg_age = float(row[0]) if row and row[0] is not None else None
        cur.execute(
            """SELECT d.document_type, COUNT(*) FROM health_docs d GROUP BY d.document_type ORDER BY COUNT(*) DESC LIMIT 10"""
        )
        by_type = dict(cur.fetchall())
        cur.execute(
            """SELECT d.institution, COUNT(*) FROM health_docs d GROUP BY d.institution ORDER BY COUNT(*) DESC LIMIT 15"""
        )
        by_institution = dict(cur.fetchall())
        return {
            "date": datetime.utcnow().isoformat() + "Z",
            "num_documents": num_docs,
            "num_chunks": num_chunks,
            "pct_chunks_mexican": round(pct_mexican, 2),
            "avg_evidence_age_years": round(avg_age, 2) if avg_age is not None else None,
            "by_document_type": by_type,
            "by_institution": by_institution,
        }
    finally:
        cur.close()
        conn.close()
