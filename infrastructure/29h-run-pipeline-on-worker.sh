#!/bin/bash
# Run the nightly pipeline once on the worker (SSH). Does not touch the backend.
# Prereq: config/pipeline_worker.txt with PIPELINE_WORKER_IP and 29e-setup-pipeline-worker.sh already run.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
if [ ! -f "$CONFIG_DIR/pipeline_worker.txt" ]; then
  echo "Error: config/pipeline_worker.txt not found. See docs/RUNBOOK_INGESTA_WORKER.md"
  exit 1
fi
source "$CONFIG_DIR/pipeline_worker.txt"
KEY_FILE="${PIPELINE_WORKER_KEY_FILE:-$CONFIG_DIR/ominis-ollama-key.pem}"
SSH_USER="${PIPELINE_WORKER_USER:-ubuntu}"
REMOTE_DIR="/opt/ominis-pipeline"

if [ -z "$PIPELINE_WORKER_IP" ]; then
  echo "Error: PIPELINE_WORKER_IP not set in config/pipeline_worker.txt"
  exit 1
fi
if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "Running pipeline on worker $PIPELINE_WORKER_IP (this may take a while)..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$PIPELINE_WORKER_IP" \
  "cd $REMOTE_DIR && source venv/bin/activate && set -a && [ -f .env ] && . .env && set +a && export PYTHONPATH=$REMOTE_DIR && python -m pipeline.nightly_pipeline --full"

echo ""
echo "Done. Check: curl -s https://api.ominis.org/v1/health-datastore/status | python3 -m json.tool"
