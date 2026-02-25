#!/usr/bin/env bash
# Check that the Haystack backend service is running and /v1/health responds.
# Uses config/haystack_backend.txt (BACKEND_IP) and the same SSH key as 20-sync-backend.sh.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found. Run 17-deploy-haystack-backend.sh first."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "Backend host: $BACKEND_IP"
echo ""

echo "=== Load and pipeline processes ==="
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" \
  'echo "Load: $(cat /proc/loadavg)"; echo "Memory: $(free -h | grep Mem)"; pgrep -af "pipeline.nightly_pipeline" || echo "No pipeline process running"' 2>/dev/null || true
echo ""

echo "=== systemctl status ominis-backend ==="
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" \
  'sudo systemctl status ominis-backend --no-pager' 2>/dev/null || true
echo ""

echo "=== Local health check (curl http://127.0.0.1:8000/v1/health) ==="
RESULT=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" \
  'curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://127.0.0.1:8000/v1/health' 2>/dev/null || echo "000")
if [ "$RESULT" = "200" ]; then
  echo "  HTTP $RESULT — backend is up and responding."
else
  echo "  HTTP ${RESULT:-000} — backend not responding on port 8000."
  echo ""
  echo "To restart the backend on the server:"
  echo "  ssh -i $KEY_FILE $SSH_USER@$BACKEND_IP 'sudo systemctl restart ominis-backend && sleep 2 && sudo systemctl status ominis-backend --no-pager'"
  echo ""
  echo "Or from this repo run: ./infrastructure/20-sync-backend.sh"
  exit 1
fi

echo ""
echo "=== Public URL (if DNS points to this IP) ==="
echo "  https://api.ominis.org/v1/health"
echo "  curl -s -o /dev/null -w '%{http_code}' https://api.ominis.org/v1/health"
