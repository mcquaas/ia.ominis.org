#!/bin/bash
# Update Haystack backend .env with OpenScholar 128K API URL (Vast.ai).
# No instance ID — Vast has no EC2 start/stop. Run after 24e-vast-ai-create-openscholar-128k.sh.
# Usage: ./20a-vast-update-backend-env-openscholar-128k.sh [URL]
#   Or create config/openscholar_128k_vast.txt with OPENSCHOLAR_128K_API_URL=http://IP:PORT
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ -n "$1" ]; then
  OPENSCHOLAR_128K_API_URL="$1"
elif [ -f "$CONFIG_DIR/openscholar_128k_vast.txt" ]; then
  source "$CONFIG_DIR/openscholar_128k_vast.txt"
elif [ -f "$CONFIG_DIR/openscholar_128k_server.txt" ]; then
  source "$CONFIG_DIR/openscholar_128k_server.txt"
else
  echo "Usage: $0 <OPENSCHOLAR_128K_API_URL>"
  echo "  Or create config/openscholar_128k_vast.txt with OPENSCHOLAR_128K_API_URL=http://IP:PORT"
  echo "  Get IP:PORT from Vast instance → IP Port Info → 8000/tcp mapping"
  exit 1
fi

if [ -z "$OPENSCHOLAR_128K_API_URL" ]; then
  echo "Error: OPENSCHOLAR_128K_API_URL not set"
  exit 1
fi

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: Backend not deployed. Run 17-deploy-haystack-backend.sh first."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Backend .env: OpenScholar 128K (Vast.ai)                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Backend: $BACKEND_IP"
echo "API URL: $OPENSCHOLAR_128K_API_URL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ -f .env ]; then
  grep -v '^OPENSCHOLAR_128K_' .env | grep -v '^# OpenScholar 128K' > .env.tmp
  mv .env.tmp .env
fi
echo "" >> .env
echo "# OpenScholar 128K (Vast.ai) - 20a-vast" >> .env
echo "OPENSCHOLAR_128K_API_URL=$OPENSCHOLAR_128K_API_URL" >> .env
echo "OPENSCHOLAR_128K_INSTANCE_ID=" >> .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated. OpenScholar 128K will use Vast.ai at $OPENSCHOLAR_128K_API_URL"
echo ""
