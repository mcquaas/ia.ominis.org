#!/bin/bash
# Update Haystack backend .env with Med42 API URL (Vast.ai, OpenAI-compatible).
# Run after Med42 is running on Vast. Get IP and external port from instance → IP & Port Info (e.g. 8080 -> 41474).
# Usage: ./20b-vast-update-backend-env-med42.sh [URL]
#   Or create config/med42_vast.txt with MED42_API_URL=http://IP:PORT
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ -n "$1" ]; then
  MED42_API_URL="$1"
elif [ -f "$CONFIG_DIR/med42_vast.txt" ]; then
  source "$CONFIG_DIR/med42_vast.txt"
else
  echo "Usage: $0 <MED42_API_URL>"
  echo "  Or create config/med42_vast.txt with MED42_API_URL=http://IP:PORT"
  echo "  From Vast: Instance → IP & Port Info → mapping for internal 8080 (e.g. 50.217.254.161:41474)"
  exit 1
fi

if [ -z "$MED42_API_URL" ]; then
  echo "Error: MED42_API_URL not set"
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
echo "║     Backend .env: Med42 (Vast.ai)                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Backend: $BACKEND_IP"
echo "MED42_API_URL: $MED42_API_URL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ -f .env ]; then
  grep -v '^MED42_' .env | grep -v '^# Med42' > .env.tmp
  mv .env.tmp .env
fi
echo "" >> .env
echo "# Med42 (Vast.ai) - Clinical Translator in research - 20b-vast" >> .env
echo "MED42_API_URL=$MED42_API_URL" >> .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated. Med42 (Clinical Translator) will use Vast at $MED42_API_URL"
echo ""
