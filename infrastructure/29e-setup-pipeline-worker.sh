#!/bin/bash
# Set up the pipeline on a dedicated worker EC2: sync code, venv, .env (from backend), and cron.
# Prereqs: Worker EC2 launched (same region/VPC as RDS recommended), SSH key access.
# 1. Copy config/pipeline_worker.txt.example to config/pipeline_worker.txt
# 2. Set PIPELINE_WORKER_IP to the worker's public IP
# 3. Run: ./infrastructure/29e-setup-pipeline-worker.sh
#
# Optionally run 29d-remove-pipeline-cron-from-backend.sh after this so the API server no longer runs the pipeline.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_DIR="$REPO_DIR/config"

if [ ! -f "$CONFIG_DIR/pipeline_worker.txt" ]; then
  echo "Error: config/pipeline_worker.txt not found."
  echo "Copy config/pipeline_worker.txt.example to config/pipeline_worker.txt and set PIPELINE_WORKER_IP."
  exit 1
fi
source "$CONFIG_DIR/pipeline_worker.txt"
if [ -z "$PIPELINE_WORKER_IP" ]; then
  echo "Error: PIPELINE_WORKER_IP not set in config/pipeline_worker.txt"
  exit 1
fi

source "$CONFIG_DIR/haystack_backend.txt" 2>/dev/null || true
KEY_FILE="${PIPELINE_WORKER_KEY_FILE:-$CONFIG_DIR/ominis-ollama-key.pem}"
SSH_USER="${PIPELINE_WORKER_USER:-ubuntu}"
REMOTE_DIR="/opt/ominis-pipeline"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Setting up pipeline worker at $PIPELINE_WORKER_IP"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "=== 1. Syncing backend-haystack and pipeline to worker ==="
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" "sudo mkdir -p $REMOTE_DIR && sudo chown $SSH_USER:$SSH_USER $REMOTE_DIR"

rsync -avz --progress \
  -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
  --exclude 'venv' --exclude '.env' --exclude '__pycache__' --exclude '*.pyc' \
  "$REPO_DIR/backend-haystack/" \
  "$SSH_USER@$PIPELINE_WORKER_IP:$REMOTE_DIR/backend-haystack/"

rsync -avz --progress \
  -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
  --exclude '__pycache__' --exclude '*.pyc' --exclude 'faiss_out' --exclude 'logs' \
  "$REPO_DIR/pipeline/" \
  "$SSH_USER@$PIPELINE_WORKER_IP:$REMOTE_DIR/pipeline/"

echo ""
echo "=== 2. Installing Python venv and dependencies on worker ==="
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" << 'REMOTE'
set -e
REMOTE_DIR=/opt/ominis-pipeline
cd "$REMOTE_DIR"
# Ensure python3.12-venv is available (Ubuntu minimal may not have it)
sudo apt-get update -qq
sudo apt-get install -y python3.12-venv 2>/dev/null || sudo apt-get install -y python3-venv
rm -rf venv
if [ ! -d venv ]; then
  python3 -m venv venv || python3.12 -m venv venv
fi
source venv/bin/activate
pip install -q -r pipeline/requirements.txt
echo "Venv and deps installed."
REMOTE

echo ""
echo "=== 3. Copying .env from API server to worker ==="
# Get .env from backend server (same DB, S3, OpenSearch)
if [ -n "$BACKEND_IP" ] && [ -f "$KEY_FILE" ]; then
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" \
    "grep -E '^(DATABASE_URL|AWS_|HEALTH_|OPENSEARCH)' /opt/ominis-backend/.env 2>/dev/null || true" \
    | ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" "cat > $REMOTE_DIR/.env"
  echo " .env copied from API server."
else
  echo " Could not copy .env from API server (BACKEND_IP or key missing). Create $REMOTE_DIR/.env on worker manually with DATABASE_URL_SYNC, AWS_REGION, HEALTH_FAISS_S3_BUCKET, etc."
fi

echo ""
echo "=== 4. Adding cron (2:00 AM) on worker ==="
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" "
  CRON_LINE='0 2 * * * cd $REMOTE_DIR && . venv/bin/activate && set -a && [ -f .env ] && . .env && set +a && export PYTHONPATH=$REMOTE_DIR && python -m pipeline.nightly_pipeline --incremental >> $REMOTE_DIR/pipeline/logs/cron.log 2>&1'
  (crontab -l 2>/dev/null | grep -v 'nightly_pipeline' | grep -v 'pipeline.nightly_pipeline'; echo \"\$CRON_LINE\") | crontab -
  echo 'Cron added (2:00 AM).'
  echo 'Current crontab:'
  crontab -l 2>/dev/null || echo '(empty)'
"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Pipeline worker setup complete.                           ║"
echo "║   Run pipeline once by hand:                                ║"
echo "║     ssh -i $KEY_FILE $SSH_USER@$PIPELINE_WORKER_IP" 
echo "║     'cd $REMOTE_DIR && source venv/bin/activate && set -a && . .env && set +a && export PYTHONPATH=$REMOTE_DIR && python -m pipeline.nightly_pipeline --full'"
echo "║   Then remove pipeline cron from API server:                ║"
echo "║     ./infrastructure/29d-remove-pipeline-cron-from-backend.sh"
echo "╚══════════════════════════════════════════════════════════════╝"
