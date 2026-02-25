#!/bin/bash
# 1) Invoke ingest Lambdas (pubmed + url_list) so they write raw docs to S3.
# 2) Run the nightly pipeline --from-s3 on the worker (or print instructions).
# Prereq: 29i-deploy-pipeline-ingest-lambda.sh deployed the Lambda; worker has pipeline code + .env (RDS, S3, OpenSearch).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

FUNCTION_NAME="${LAMBDA_FUNCTION_INGESTION:-ominis-pipeline-ingest}"
AWS_REGION="${AWS_REGION:-mx-central-1}"

# PubMed queries: política pública, Ley General de Salud, salud digital, IA en salud, FUNSALUD, IMSS, ISSSTE, CCINSHAE, CONBIOETICA, SINAVE, protocolos, diabetes, cáncer, cardiovasculares, etc.
PUBMED_QUERIES=(
  "Mexico[affiliation] OR public health[mesh] OR clinical guidelines[tiab]"
  "health policy Mexico[tiab] OR public health policy[tiab] Mexico OR Ley General de Salud"
  "(IMSS OR ISSSTE OR Mexican health system)[tiab] OR healthcare Mexico[tiab]"
  "universal health coverage[tiab] Mexico OR seguro popular Mexico"
  "digital health[tiab] Mexico OR e-health[tiab] Mexico OR telemedicine Mexico"
  "artificial intelligence[tiab] health OR AI healthcare[tiab] OR machine learning clinical"
  "FUNSALUD Mexico OR health foundation Mexico"
  "CONBIOETICA Mexico OR bioethics[tiab] Mexico OR Comisión Nacional Bioética"
  "SINAVE Mexico OR epidemiological surveillance[tiab] Mexico OR vigilancia epidemiológica"
  "CCINSHAE Mexico OR scientific health information Mexico"
  "clinical practice guidelines[tiab] Mexico OR guías práctica clínica México"
  "health protocols[tiab] Mexico OR clinical protocols[tiab] Mexico OR protocolos salud"
  "(diabetes mellitus OR hypertension)[mesh] AND Mexico[affiliation]"
  "diabetes[tiab] Mexico OR diabetes mellitus type 2[mesh] Mexico"
  "cancer[tiab] Mexico OR neoplasms[mesh] Mexico[affiliation] OR cáncer México"
  "cardiovascular[tiab] Mexico OR cardiovascular diseases[mesh] Mexico[affiliation]"
  "(maternal health OR perinatal)[tiab] AND Mexico"
  "mental health[tiab] Mexico OR psychiatric Mexico[affiliation]"
  "infectious diseases[mesh] Mexico OR enfermedades transmisibles México"
)
# Mexican health URLs: SSA, CENAPRECE, IMSS, ISSSTE, CENETEC, FUNSALUD, CONBIOETICA, SINAVE
MEXICAN_URLS='["https://www.gob.mx/salud","https://www.gob.mx/salud/cenaprece","https://www.imss.gob.mx","https://www.gob.mx/issste","https://cenetec-difusion.com/gpc-sns/","https://www.gob.mx/salud/documentos","https://funsalud.org.mx","https://www.conbioetica-mexico.salud.gob.mx","https://www.gob.mx/salud/conbioetica","https://www.sinave.gob.mx"]'

echo "=== 1) Invoking ingest Lambdas ==="
echo ""

# Invoke PubMed for each query (more relevant results for Mexican health)
MAX_PER_QUERY=150
for i in "${!PUBMED_QUERIES[@]}"; do
  Q="${PUBMED_QUERIES[$i]}"
  echo "Invoking Lambda: source=pubmed query=${Q:0:50}..."
  aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --payload "{\"source\":\"pubmed\",\"max_results\":$MAX_PER_QUERY,\"query\":$(echo "$Q" | jq -Rs .)}" \
    --cli-binary-format raw-in-base64-out \
    "$SCRIPT_DIR/../.lambda_pubmed_$i.json" --output text --query 'StatusCode'
  echo "  Response: $(cat "$SCRIPT_DIR/../.lambda_pubmed_$i.json" 2>/dev/null | head -c 200)"
  echo ""
done

# Invoke url_list (Mexican health URLs)
echo "Invoking Lambda: source=url_list (Mexican health URLs)"
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --payload "{\"source\":\"url_list\",\"urls\":$MEXICAN_URLS,\"institution\":\"SSA\",\"document_type\":\"documento\",\"country\":\"México\"}" \
  --cli-binary-format raw-in-base64-out \
  "$SCRIPT_DIR/../.lambda_url_list_out.json" --output text --query 'StatusCode'
echo "  Response: $(cat "$SCRIPT_DIR/../.lambda_url_list_out.json" 2>/dev/null || echo '{}')"

echo ""
echo "Lambdas finished. Raw docs are in S3 (pipeline/raw_docs/YYYY-MM-DD/)."
echo ""

# 2) Run pipeline --from-s3 ONLY on the worker (never on the backend — saturates the API).
CONFIG_DIR="$SCRIPT_DIR/../config"
if [ -f "$CONFIG_DIR/pipeline_worker.txt" ]; then
  source "$CONFIG_DIR/pipeline_worker.txt"
  KEY_FILE="${PIPELINE_WORKER_KEY_FILE:-$CONFIG_DIR/ominis-ollama-key.pem}"
  SSH_USER="${PIPELINE_WORKER_USER:-ubuntu}"
  REMOTE_DIR="${PIPELINE_WORKER_REMOTE_DIR:-/opt/ominis-pipeline}"
  if [ -n "$PIPELINE_WORKER_IP" ] && [ -f "$KEY_FILE" ]; then
    echo "=== 2) Running pipeline --from-s3 on worker $PIPELINE_WORKER_IP ==="
    ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" \
      "cd $REMOTE_DIR && source venv/bin/activate && set -a && [ -f .env ] && . .env && set +a && export PYTHONPATH=$REMOTE_DIR && python -m pipeline.nightly_pipeline --from-s3"
    echo ""
    echo "Done. Check: curl -s https://api.ominis.org/v1/health-datastore/status | python3 -m json.tool"
    exit 0
  fi
fi

# No worker configured: do NOT run on backend (would saturate the API).
echo "=== 2) Pipeline must run on the WORKER only (not on the backend) ==="
echo ""
echo "The pipeline (embedding + index) is CPU/RAM heavy and will saturate the API server."
echo "Configure a separate worker, then run pipeline --from-s3 there:"
echo ""
echo "  1) Launch worker EC2:  ./infrastructure/29e0-launch-pipeline-worker-ec2.sh"
echo "  2) Setup pipeline:     ./infrastructure/29e-setup-pipeline-worker.sh"
echo "  3) Create config:      config/pipeline_worker.txt (PIPELINE_WORKER_IP=..., PIPELINE_WORKER_KEY_FILE=...)"
echo "  4) Run this script again; or on the worker: python -m pipeline.nightly_pipeline --from-s3"
echo ""
echo "Remove pipeline cron from backend (if any): ./infrastructure/29d-remove-pipeline-cron-from-backend.sh"
echo ""
echo "To run --from-s3 manually ON THE WORKER (not backend):"
echo "  ssh -i <key> ubuntu@<WORKER_IP>"
echo "  cd /opt/ominis-pipeline && source venv/bin/activate && set -a && . .env && set +a && export PYTHONPATH=\$(pwd)"
echo "  python -m pipeline.nightly_pipeline --from-s3"
echo ""
echo "To backfill unchunked health_docs (chunk+embed+index) ON THE WORKER:"
echo "  python -m pipeline.nightly_pipeline --backfill"
echo ""
echo "Then: curl -s https://api.ominis.org/v1/health-datastore/status | python3 -m json.tool"
