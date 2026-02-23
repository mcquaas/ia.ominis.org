#!/bin/bash
# Add la.ominis.org and ai.ominis.org to ALLOWED_ORIGINS so the dashboard (RAG, scrape-index) works from those origins.
# Run once after deploy if the dashboard is at la.ominis.org or ai.ominis.org.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

echo "Updating ALLOWED_ORIGINS on backend $BACKEND_IP (ia.ominis.org, la.ominis.org, ai.ominis.org)..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << 'REMOTECMD'
set -e
cd /opt/ominis-backend
if [ -f .env ]; then
  # Remove old ALLOWED_ORIGINS line and add new one with all origins
  grep -v '^ALLOWED_ORIGINS=' .env > .env.tmp || true
  echo 'ALLOWED_ORIGINS=https://ominis.org,https://ia.ominis.org,https://la.ominis.org,https://ai.ominis.org,https://chat.ominis.org,http://localhost:3000' >> .env.tmp
  mv .env.tmp .env
  sudo systemctl restart ominis-backend
  sleep 2
  sudo systemctl status ominis-backend --no-pager
  echo "Done. CORS now allows ia.ominis.org, la.ominis.org, ai.ominis.org, chat.ominis.org."
else
  echo "No .env found. Run 17-deploy-haystack-backend.sh or 20-sync-backend.sh first."
  exit 1
fi
REMOTECMD
