#!/bin/bash
# Inject OpenScholar 8K (ominis-2.0-research) instance ID into backend .env so the
# dashboard switch can start/stop that EC2. Uses config/openscholar_server.txt.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/openscholar_server.txt" ]; then
    echo "Error: config/openscholar_server.txt not found (run 14-deploy-openscholar.sh first)."
    exit 1
fi
source "$CONFIG_DIR/openscholar_server.txt"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
    echo "Error: config/haystack_backend.txt not found."
    exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

echo "Injecting OpenScholar 8K instance ID into backend .env (backend: $BACKEND_IP)..."
echo "  OPENSCHOLAR_INSTANCE_ID=$OPENSCHOLAR_INSTANCE_ID"
echo "  OPENSCHOLAR_API_URL=$OPENSCHOLAR_API_URL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
# Remove existing OPENSCHOLAR_ (8K only, not 128K) lines so we can append
if [ -f .env ]; then
  grep -v '^OPENSCHOLAR_INSTANCE_ID=' .env | grep -v '^OPENSCHOLAR_API_URL=' | grep -v '^# OpenScholar 8K' > .env.tmp
  sudo mv .env.tmp .env
  sudo chown ubuntu:ubuntu .env
fi
echo "# OpenScholar 8K (dashboard start/stop) - 20c" | sudo tee -a .env > /dev/null
echo "OPENSCHOLAR_INSTANCE_ID=$OPENSCHOLAR_INSTANCE_ID" | sudo tee -a .env > /dev/null
echo "OPENSCHOLAR_API_URL=$OPENSCHOLAR_API_URL" | sudo tee -a .env > /dev/null
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated with OpenScholar 8K (ominis-2.0-research)."
echo "  Dashboard switch for 8K will now show status (stopped/running)."
echo ""