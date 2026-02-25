"""
Lambda: ingest one source (pubmed or url_list). Writes raw docs to S3 for downstream normalize/chunk/embed.
Event: {"source": "pubmed", "max_results": 300} or {"source": "url_list", "urls": ["https://..."], "institution": "SSA", ...}
Output: {"bucket": "...", "key": "raw_docs/YYYY-MM-DD/source_id.json", "doc_count": N}
Auto-scaling: invoke one Lambda per source in parallel (Step Functions Map or SQS).
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
import httpx

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BUCKET = os.environ.get("PIPELINE_RAW_BUCKET", os.environ.get("HEALTH_FAISS_S3_BUCKET", "ominis-health-embeddings-mx"))
PREFIX = os.environ.get("PIPELINE_RAW_PREFIX", "pipeline/raw_docs")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_DELAY = 0.4


def _text_from_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300_000]


def fetch_pubmed(max_results: int = 300, query: str | None = None) -> list[dict]:
    q = query or "health Mexico[affiliation] OR public health[mesh] OR clinical guidelines[tiab]"
    raw_list: list[dict] = []
    with httpx.Client(timeout=30) as client:
        r = client.get(
            f"{EUTILS}/esearch.fcgi",
            params={"db": "pubmed", "term": q, "retmax": min(max_results, 10000), "retmode": "json", "email": "ominis@example.com"},
        )
        r.raise_for_status()
        data = r.json()
    id_list = data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return raw_list
    batch_size = 200
    for i in range(0, len(id_list), batch_size):
        batch_ids = id_list[i : i + batch_size]
        time.sleep(NCBI_DELAY)
        with httpx.Client(timeout=60) as client:
            r = client.get(
                f"{EUTILS}/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(batch_ids), "retmode": "json"},
            )
            r.raise_for_status()
            data = r.json()
        for pmid in batch_ids:
            if pmid == "ERROR":
                continue
            item = data.get("result", {}).get(pmid)
            if not item or not item.get("title"):
                continue
            raw_list.append({
                "doc_id": str(uuid.uuid4()),
                "title": item.get("title", ""),
                "year": int(str(item.get("pubdate", ""))[:4]) if item.get("pubdate") else None,
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source_type": "PubMed",
                "raw_text": (item.get("abstract") or "") or item.get("title", ""),
                "institution": "PubMed",
                "document_type": "estudio",
                "country": "",
            })
    for d in raw_list:
        raw = (d.get("raw_text") or "") or (d.get("title") or "")
        if raw:
            d["content_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return raw_list


def fetch_url_list(urls: list[str], institution: str = "SSA", document_type: str = "documento", country: str = "México") -> list[dict]:
    raw_list: list[dict] = []
    for url in urls:
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                r = client.get(url)
                r.raise_for_status()
                body = r.text
        except Exception as e:
            logger.warning("Fetch %s: %s", url, e)
            continue
        text = _text_from_html(body) if "text/html" in r.headers.get("content-type", "") else body
        if len(text) < 100:
            continue
        raw_list.append({
            "doc_id": str(uuid.uuid4()),
            "title": urlparse(url).path.rstrip("/").split("/")[-1] or url[:80],
            "raw_text": text[:300_000],
            "source_url": url,
            "source_type": "url_list",
            "institution": institution,
            "document_type": document_type,
            "country": country,
        })
    for d in raw_list:
        if d.get("raw_text"):
            d["content_hash"] = hashlib.sha256(d["raw_text"].encode("utf-8")).hexdigest()[:32]
    return raw_list


def handler(event: dict, context) -> dict:
    source = (event.get("source") or "").strip().lower()
    if not source:
        return {"statusCode": 400, "error": "Missing 'source' (pubmed | url_list)"}

    if source == "pubmed":
        docs = fetch_pubmed(max_results=int(event.get("max_results") or 300), query=event.get("query"))
        source_id = "pubmed"
    elif source == "url_list":
        urls = event.get("urls") or []
        if not urls:
            return {"statusCode": 400, "error": "url_list requires 'urls' array"}
        docs = fetch_url_list(
            urls=urls,
            institution=event.get("institution", "SSA"),
            document_type=event.get("document_type", "documento"),
            country=event.get("country", "México"),
        )
        source_id = "url_list"
    else:
        return {"statusCode": 400, "error": f"Unknown source: {source}"}

    if not docs:
        return {"bucket": BUCKET, "key": "", "doc_count": 0, "source": source_id}

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = event.get("run_id") or context.aws_request_id if context else str(uuid.uuid4())[:8]
    key = f"{PREFIX}/{date_str}/{source_id}_{run_id}.json"

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(docs, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Wrote %d docs to s3://%s/%s", len(docs), BUCKET, key)

    return {
        "bucket": BUCKET,
        "key": key,
        "doc_count": len(docs),
        "source": source_id,
    }
