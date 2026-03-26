#!/bin/bash
# Sync Haystack backend code to EC2 and restart the service
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# Load backend config
if [ ! -f "$SCRIPT_DIR/../config/haystack_backend.txt" ]; then
    echo "Error: Backend not deployed. Run 17-deploy-haystack-backend.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/haystack_backend.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"
BACKEND_DIR="$SCRIPT_DIR/../backend-haystack"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Syncing Haystack Backend to EC2                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Server:  $BACKEND_IP"
echo ""

if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

echo "Syncing backend code..."
rsync -avz --progress \
    --exclude 'venv' \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    -e "ssh -o StrictHostKeyChecking=no -i \"$KEY_FILE\"" \
    "$BACKEND_DIR/" \
    "$SSH_USER@$BACKEND_IP:$REMOTE_DIR/"

echo "Syncing nightly health datastore pipeline..."
PIPELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/pipeline"
if [ -d "$PIPELINE_DIR" ]; then
  rsync -avz --progress \
      --exclude '__pycache__' \
      --exclude '*.pyc' \
      --exclude 'faiss_out' \
      --exclude 'logs' \
      -e "ssh -o StrictHostKeyChecking=no -i \"$KEY_FILE\"" \
      "$PIPELINE_DIR/" \
      "$SSH_USER@$BACKEND_IP:$REMOTE_DIR/pipeline/"
  echo "  ✓ Pipeline synced"
fi

echo "  ✓ Code synced"

echo ""
echo "Restarting backend service..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << 'REMOTECMD'
# Align nginx with 15m SSE / Vast cold start (was 600s or default 60s)
for f in /etc/nginx/sites-available/ominis-backend /etc/nginx/sites-enabled/ominis-backend; do
  if [ -f "$f" ]; then
    sudo sed -i 's/proxy_read_timeout 600s/proxy_read_timeout 900s/g' "$f" 2>/dev/null || true
    sudo sed -i 's/proxy_read_timeout 120s/proxy_read_timeout 900s/g' "$f" 2>/dev/null || true
    sudo sed -i 's/proxy_send_timeout 600s/proxy_send_timeout 900s/g' "$f" 2>/dev/null || true
  fi
done
sudo nginx -t 2>/dev/null && sudo systemctl reload nginx 2>/dev/null || true

cd /opt/ominis-backend
source venv/bin/activate
pip install -r requirements.txt -q 2>/dev/null || true
alembic upgrade head
if [ -f pipeline/requirements.txt ]; then pip install -r pipeline/requirements.txt; fi
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Backend Deployed Successfully!                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
