"""
Lambda: embed one batch of chunks. Reads chunk JSON from S3, runs sentence-transformers, writes embeddings to S3.
Event: {"s3_bucket": "...", "s3_key": "chunks/batch_001.json"} or {"s3_key": "..."} (bucket from env).
Output: {"s3_bucket": "...", "s3_key": "embeddings/batch_001.json", "count": N}

Deploy as Lambda container image (sentence-transformers + torch are large). Memory 2048–4096 MB, timeout 900 s.
Auto-scaling: invoke one Lambda per chunk batch in parallel (Step Functions Map); more chunks → more Lambdas.
"""

import json
import logging
import os
import uuid

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BUCKET = os.environ.get("PIPELINE_RAW_BUCKET", os.environ.get("HEALTH_FAISS_S3_BUCKET", "ominis-health-embeddings-mx"))
EMBEDDINGS_PREFIX = os.environ.get("PIPELINE_EMBEDDINGS_PREFIX", "pipeline/embeddings")
MODEL_NAME = os.environ.get("HEALTH_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "64"))

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def handler(event: dict, context) -> dict:
    bucket = event.get("s3_bucket") or BUCKET
    key = event.get("s3_key") or event.get("s3_key_ref")
    if not key:
        return {"statusCode": 400, "error": "Missing s3_key (or s3_key_ref)"}

    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        chunks = json.loads(obj["Body"].read().decode("utf-8"))
    except Exception as e:
        logger.exception("Failed to read chunks from s3://%s/%s: %s", bucket, key, e)
        return {"statusCode": 500, "error": str(e)}

    if not chunks or not isinstance(chunks, list):
        return {"bucket": bucket, "s3_key": "", "count": 0}

    texts = [c.get("chunk_text", "") or "" for c in chunks]
    model = get_model()
    embs = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=False)

    for i, c in enumerate(chunks):
        c["embedding"] = embs[i].tolist() if hasattr(embs[i], "tolist") else list(embs[i])

    run_id = event.get("run_id") or (context.aws_request_id[:8] if context else str(uuid.uuid4())[:8])
    base = key.replace("chunks/", "").replace(".json", "")
    out_key = f"{EMBEDDINGS_PREFIX}/{run_id}/{base}.json"

    s3.put_object(
        Bucket=bucket,
        Key=out_key,
        Body=json.dumps(chunks, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Wrote %d embeddings to s3://%s/%s", len(chunks), bucket, out_key)

    return {
        "bucket": bucket,
        "s3_key": out_key,
        "count": len(chunks),
    }
