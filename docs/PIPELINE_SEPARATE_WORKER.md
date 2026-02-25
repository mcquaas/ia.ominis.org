# Running the pipeline on a separate worker (recommended)

The ingestion pipeline (ingest → normalize → chunk → **embed** → index) is CPU- and memory-heavy. Running it on the **same EC2 as the API** can saturate the server and make the API (and SSH) unresponsive. **Running the pipeline on a dedicated worker** keeps the API server stable.

**GPU:** Not required. The pipeline uses `sentence-transformers/all-MiniLM-L6-v2`, which runs fine on CPU. A **t3.medium** or **t3.large** is enough. You can rent a cheap **CPU-only** instance on Vast.ai or use a small EC2 in the same AWS region/VPC as RDS (simpler for DB access).

## Quick setup (AWS EC2 worker)

1. **Launch worker** (same region/VPC as backend so it can reach RDS):
   ```bash
   ./infrastructure/29e0-launch-pipeline-worker-ec2.sh
   ```
2. Set `PIPELINE_WORKER_IP` in `config/pipeline_worker.txt` (copy from `config/pipeline_worker.txt.example`).
3. **Install pipeline and cron on worker:**
   ```bash
   ./infrastructure/29e-setup-pipeline-worker.sh
   ```
4. **Remove pipeline cron from API server** so only the worker runs it:
   ```bash
   ./infrastructure/29d-remove-pipeline-cron-from-backend.sh
   ```

## Architecture

- **API server** (existing `ominis-haystack-backend`): Serves the API only. Loads FAISS from S3 and queries OpenSearch/PostgreSQL for retrieval. **Does not run the pipeline.**
- **Pipeline worker** (new EC2 or scheduled job): Runs the nightly pipeline only. Needs access to the same **RDS** (writes `health_docs`, `health_chunks`), **S3** (uploads FAISS + chunk_ids), and optionally **OpenSearch**. No uvicorn, no public traffic.

## Option A: Dedicated pipeline worker EC2

### 1. Launch a worker instance

- **Region**: Same as RDS (e.g. `mx-central-1` or `us-east-1`) so it can reach the database.
- **Type**: e.g. `t3.medium` or `t3.large` (embedding benefits from more CPU/RAM). Can be burstable; pipeline runs once per night.
- **VPC**: Same VPC as RDS (or ensure RDS security group allows inbound from this instance’s security group on port 5432).
- **IAM role**: Attach a role with policies for **S3** (read/write the FAISS bucket) and, if you use it, **OpenSearch** (or use access keys in `.env`).
- **Storage**: 20–30 GB is enough for code + venv + logs.
- **Security group**: Outbound to RDS (5432), S3, OpenSearch, and the internet (for PubMed, gob.mx, etc.). Inbound: SSH (22) from your IP for setup only; no need for 8000.

### 2. Install pipeline on the worker

On the worker (Ubuntu), as `ubuntu`:

```bash
sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv python3-pip git
cd /opt
sudo git clone https://github.com/YOUR_ORG/ia.ominis.org.git ominis-pipeline
# Or rsync pipeline + backend-haystack from your machine:
# rsync -avz --exclude venv --exclude .env backend-haystack/ ubuntu@WORKER_IP:/opt/ominis-pipeline/backend-haystack/
# rsync -avz pipeline/ ubuntu@WORKER_IP:/opt/ominis-pipeline/pipeline/

cd /opt/ominis-pipeline
python3.12 -m venv venv
source venv/bin/activate
pip install -r backend-haystack/requirements.txt -q
pip install -r pipeline/requirements.txt
```

Create `/opt/ominis-pipeline/.env` with at least:

```env
# Same RDS as the API (get from backend .env). Worker must be able to reach RDS.
DATABASE_URL_SYNC=postgresql://USER:PASSWORD@RDS_HOST:5432/ominis_haystack
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@RDS_HOST:5432/ominis_haystack

# S3 for FAISS (worker uploads; API server reads)
AWS_REGION=us-east-1
HEALTH_FAISS_S3_BUCKET=ominis-health-embeddings-mx
HEALTH_FAISS_S3_PREFIX=health-datastore/faiss

# Optional: OpenSearch (same as backend)
OPENSEARCH_URL=https://search-....
OPENSEARCH_INDEX=health-chunks
```

If the worker uses an IAM role, you don’t need AWS keys in `.env`. Otherwise add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

### 3. Run the pipeline on the worker

```bash
cd /opt/ominis-pipeline
source venv/bin/activate
set -a && [ -f .env ] && . .env && set +a
export PYTHONPATH=/opt/ominis-pipeline
python -m pipeline.nightly_pipeline --full
```

Set up cron (e.g. 2:00 AM) on the **worker** only:

```cron
0 2 * * * cd /opt/ominis-pipeline && . venv/bin/activate && set -a && [ -f .env ] && . .env && set +a && export PYTHONPATH=/opt/ominis-pipeline && python -m pipeline.nightly_pipeline --incremental >> /opt/ominis-pipeline/pipeline/logs/cron.log 2>&1
```

### 4. API server: do not run the pipeline

On the **API server** (`ominis-haystack-backend`), remove or comment out the pipeline cron if it was there. The API only needs to read from RDS, S3 (FAISS), and OpenSearch; it does not need to run `nightly_pipeline`.

## Option B: Same account, run pipeline from your machine (or CI)

You can also run the pipeline from a dev machine or a CI runner that has:

- Network access to **RDS** (e.g. RDS publicly accessible with security group allowing your IP, or VPN/bastion).
- **AWS credentials** (env or profile) for S3 and OpenSearch.

Then:

```bash
cd /path/to/ia.ominis.org
# .env with DATABASE_URL_SYNC, AWS_*, OPENSEARCH_* (RDS must be reachable)
source .venv/bin/activate  # or backend venv
export PYTHONPATH=.
python -m pipeline.nightly_pipeline --full
```

No second server, but your machine or CI must have access to RDS and AWS.

## Summary

| Component        | API server              | Pipeline worker        |
|-----------------|------------------------|------------------------|
| Runs            | uvicorn (API only)     | `nightly_pipeline` only |
| Reads           | RDS, S3 (FAISS), OS   | RDS (same DB)          |
| Writes          | —                      | RDS, S3, OpenSearch    |
| Public traffic  | Yes (443/8000)         | No                     |
| When to run     | Always                 | Cron (e.g. 2 AM)       |

Using a **separate worker** for ingestion avoids saturating the API server and keeps SSH and the API responsive.

## Vast.ai (optional)

You can run the pipeline on a **CPU-only** Vast.ai instance (no GPU needed). An EC2 in the same AWS VPC as RDS (via `29e0-launch-pipeline-worker-ec2.sh`) is usually simpler.

For **auto-scaling by number of sources**, see **[docs/PIPELINE_LAMBDA.md](PIPELINE_LAMBDA.md)**: run ingest (and optionally embed) with AWS Lambda + Step Functions so more sources trigger more parallel invocations.
