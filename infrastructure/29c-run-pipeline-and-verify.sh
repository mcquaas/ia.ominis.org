#!/bin/bash
# Run nightly health datastore pipeline on backend server and verify ingestion.
# Run from repo root on a machine that can SSH to the backend.
# Usage: ./infrastructure/29c-run-pipeline-and-verify.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/../config/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found. Run 17-deploy-haystack-backend.sh first."
  exit 1
fi
source "$SCRIPT_DIR/../config/haystack_backend.txt"
KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: $KEY_FILE not found."
  exit 1
fi

echo "=== 1. Running nightly pipeline on backend ($BACKEND_IP) ==="
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << 'REMOTE'
cd /opt/ominis-backend
source venv/bin/activate
set -a
[ -f .env ] && . .env
set +a
export PYTHONPATH=/opt/ominis-backend
python -m pipeline.nightly_pipeline --full 2>&1
REMOTE

echo ""
echo "=== 2. Verifying health datastore (backend status endpoint) ==="
# Prefer direct API URL (port 8000); fallback to public URL (nginx)
BASE="${BACKEND_URL:-http://$BACKEND_IP:8000}"
STATUS_URL="${BASE%/}/v1/health-datastore/status"
echo "GET $STATUS_URL"
curl -s -S "$STATUS_URL" | python3 -m json.tool 2>/dev/null || curl -s -S "$STATUS_URL"

echo ""
echo "Done. If health_docs and health_chunks are > 0 and evidence_pack_test_count > 0, ingestion is working."
