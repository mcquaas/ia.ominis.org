#!/bin/bash
# Remove the nightly pipeline cron from the API server so ingestion runs only on the worker.
# Run from repo root after you have set up the pipeline worker (29e-setup-pipeline-worker.sh).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"
KEY_FILE="${PIPELINE_WORKER_KEY_FILE:-$CONFIG_DIR/ominis-ollama-key.pem}"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "Removing pipeline cron from API server $BACKEND_IP ..."
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" '
  if crontab -l 2>/dev/null | grep -q "nightly_pipeline\|pipeline.nightly_pipeline"; then
    crontab -l 2>/dev/null | grep -v "nightly_pipeline" | grep -v "pipeline.nightly_pipeline" | crontab -
    echo "Pipeline cron removed."
  else
    echo "No pipeline cron found on this server."
  fi
  echo "Current crontab:"
  crontab -l 2>/dev/null || echo "(empty)"
'
echo "Done. API server will no longer run the pipeline."
