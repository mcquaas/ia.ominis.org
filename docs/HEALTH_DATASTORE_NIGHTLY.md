# Nightly Health Datastore Pipeline

The **Mexican Health Datastore** is built by a nightly pipeline that ingests from PubMed and Mexican health URLs, chunks, embeds, and indexes into FAISS (S3), OpenSearch, and PostgreSQL. The backend uses it for hybrid retrieval when `health_datastore_enabled` is true.

## Do the Ominis models already use it?

**Yes.** Whenever the backend has the health datastore enabled and configured, **all chat models** (Ominis 2.0, Ominis Med, etc.) that answer through `/v1/rag/query-stream` automatically use it. The backend runs health-datastore retrieval in parallel with RAG (admin sources), web, PubMed, and OpenScholar. There is no per-model switch: if `HEALTH_DATASTORE_ENABLED=true` and `HEALTH_FAISS_S3_BUCKET` is set, every query can get chunks from the health datastore. The “Ominis / bases de datos” toggle controls the **admin RAG**; the health datastore is always queried when enabled.

## What do I need to do so models use it?

On the **API server** (`/opt/ominis-backend`), ensure `.env` has:

- `HEALTH_DATASTORE_ENABLED=true`
- `HEALTH_FAISS_S3_BUCKET=ominis-health-embeddings-mx`
- `HEALTH_FAISS_S3_PREFIX=health-datastore/faiss`

The backend must be able to read that S3 bucket (same as the pipeline worker). It also needs the **same PostgreSQL (RDS)** as the worker for chunk metadata/citations. Optional: `OPENSEARCH_URL` and `OPENSEARCH_INDEX=health-chunks` for BM25. The embedding model must match the pipeline (default `all-MiniLM-L6-v2`, 384 dim). After changing `.env`, restart: `sudo systemctl restart ominis-backend`.

## Will Ominis know about a recently ingested document?

**Yes, after the pipeline finishes and the backend reloads the index.** The worker uploads the new FAISS index to S3 at the end of each run. The backend **refreshes the index from S3 every 5 minutes** (see `FAISS_CACHE_TTL_SECONDS` in `app/rag/health_datastore/retriever.py`). So within about 5 minutes after the worker uploads a new index, the next query will use it. Restarting the backend picks it up immediately.

---

## One-time setup

### 1. OpenSearch (AWS)

Create an OpenSearch domain (once) via AWS CLI:

```bash
./infrastructure/29-create-opensearch-domain.sh
```

Set in backend `.env` and pipeline (or backend `.env` only if pipeline loads it):

- `OPENSEARCH_URL=https://<endpoint>` (from script output)
- `OPENSEARCH_INDEX=health-chunks`

### 2. Backend .env

Add (or ensure) in `backend-haystack/.env`:

```env
HEALTH_DATASTORE_ENABLED=true
HEALTH_FAISS_S3_BUCKET=ominis-health-embeddings-mx
HEALTH_FAISS_S3_PREFIX=health-datastore/faiss
OPENSEARCH_URL=https://...
OPENSEARCH_INDEX=health-chunks
```

### 3. Migration

Migration `015_add_health_datastore_tables` adds `health_docs` and `health_chunks`. It runs automatically on deploy when you run `./infrastructure/20-sync-backend.sh` (alembic upgrade head).

## Running the pipeline

**Recommended:** Run the pipeline on a **separate worker** (another EC2 or a machine with access to RDS + S3) so the API server is never saturated. See **[docs/PIPELINE_SEPARATE_WORKER.md](PIPELINE_SEPARATE_WORKER.md)** for setup.

**Warning:** The pipeline (especially embedding) is CPU- and memory-heavy. Running it on the **same machine** as the API can make the server unresponsive for several minutes. Prefer running it via **cron at night** (e.g. 2:00 AM) or in a time window with low traffic. If you run it by hand, expect the API to be slow or to return 502 until the pipeline finishes.

On the **backend server** after sync you must use the project **venv** (so numpy, faiss, etc. are available):

```bash
cd /opt/ominis-backend
source venv/bin/activate
# If pipeline deps are missing (e.g. ModuleNotFoundError: numpy), install once:
pip install -r pipeline/requirements.txt

set -a && [ -f .env ] && . .env && set +a   # load .env
export PYTHONPATH=/opt/ominis-backend
python -m pipeline.nightly_pipeline --full
```

From **repo root** (or on the server from `/opt/ominis-backend` with venv activated and `.env` loaded):

```bash
# Full run (all sources)
PYTHONPATH=. python pipeline/nightly_pipeline.py --full

# Incremental (same as full; dedup by content_hash)
PYTHONPATH=. python pipeline/nightly_pipeline.py --incremental

# Single source
PYTHONPATH=. python pipeline/nightly_pipeline.py --source pubmed

# Read raw docs from S3 (written by ingest Lambdas)
PYTHONPATH=. python pipeline/nightly_pipeline.py --from-s3

# Crawl seed URLs (follow same-domain links, e.g. gob.mx/salud and subpages)
PYTHONPATH=. python pipeline/nightly_pipeline.py --source crawl

# Ingest from a ZIP (e.g. WhatsApp chat export): .txt files + fetch URLs found in chat
PYTHONPATH=. python pipeline/nightly_pipeline.py --zip /path/to/chat.zip
```

**Crawl:** With `--source crawl` the pipeline uses `CRAWL_SEED_URLS` from `pipeline/config.py` (e.g. https://www.gob.mx/salud), fetches each seed, discovers same-domain links from the HTML, and fetches those pages up to `CRAWL_MAX_PAGES` (default 80). So one run can ingest the main page and many linked pages (e.g. [gob.mx/salud](https://www.gob.mx/salud/) and its “Documentos”, “Acciones y programas”, etc.).

**ZIP / WhatsApp:** With `--zip /path/to/file.zip` the pipeline opens the zip, reads every `.txt` file (e.g. WhatsApp export), extracts all URLs from the text, and optionally fetches those URLs (up to 200 by default). It produces one doc per `.txt` file (full chat content) and one doc per successfully fetched URL. Attached files inside the zip (e.g. PDFs) are not yet extracted; only `.txt` and fetched links are used.

To run **ingestion with Lambdas**: deploy with `./infrastructure/29i-deploy-pipeline-ingest-lambda.sh`, then `./infrastructure/29j-trigger-lambda-ingest-and-pipeline.sh`. See [PIPELINE_LAMBDA.md](PIPELINE_LAMBDA.md).

Pipeline reads `DATABASE_URL_SYNC`, `AWS_REGION`, `HEALTH_FAISS_S3_BUCKET`, `OPENSEARCH_URL`, etc. from `.env` (backend-haystack/.env or repo root .env).

## Cron (nightly)

On the backend server, add a cron job (e.g. 2:00 AM). Use the venv and set PYTHONPATH:

```cron
0 2 * * * cd /opt/ominis-backend && . venv/bin/activate && set -a && [ -f .env ] && . .env && set +a && export PYTHONPATH=/opt/ominis-backend && python -m pipeline.nightly_pipeline --incremental >> /opt/ominis-backend/pipeline/logs/cron.log 2>&1
```

Or use a systemd timer if you prefer.

## Output

- **PostgreSQL**: `health_docs`, `health_chunks` (metadata and chunk text).
- **S3**: `s3://<HEALTH_FAISS_S3_BUCKET>/<HEALTH_FAISS_S3_PREFIX>/index.faiss` and `chunk_ids.json`.
- **OpenSearch**: index `health-chunks` (BM25).
- **Reports**: `pipeline/reports/YYYY-MM-DD_report.json` and `reports/YYYY-MM-DD_summary.md`.

## Backend retrieval

When a user runs a query with RAG/search enabled, the backend calls `build_evidence_pack(query)` which:

1. Loads FAISS index from S3 (or `HEALTH_FAISS_PATH`).
2. Queries OpenSearch for BM25.
3. Merges and applies boosting (México +0.15, recent year +0.10, NOM/GPC +0.12).
4. Returns evidence as Haystack Documents with `source_type="health_datastore"` for OpenScholar.

No extra API or service is required; the backend does the retrieval in-process.

## Verification

**Status endpoint** (no auth):

```bash
curl -s http://<BACKEND_IP>:8000/v1/health-datastore/status
```

Returns: `enabled`, `health_docs`, `health_chunks`, `evidence_pack_test_count` (retrieval test with query "salud México diabetes"), and `opensearch_url_set`. If `evidence_pack_test_count` > 0, FAISS + OpenSearch + PG are working.

**Run pipeline and verify in one go** (from a machine that can SSH to the backend):

```bash
./infrastructure/29c-run-pipeline-and-verify.sh
```

This runs the nightly pipeline on the server, then curls the status endpoint and prints the JSON.
