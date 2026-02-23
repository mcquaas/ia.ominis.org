#!/bin/bash
# Inject HEYGEN_LIVE_AVATAR_API_KEY into backend .env for /live page.
# Usage: HEYGEN_LIVE_AVATAR_API_KEY=your_key ./infrastructure/20i-update-backend-env-liveavatar.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

if [ -z "$HEYGEN_LIVE_AVATAR_API_KEY" ]; then
    echo "Usage: HEYGEN_LIVE_AVATAR_API_KEY=your_key $0"
    echo "Get your key at https://app.liveavatar.com"
    exit 1
fi

echo "Updating HEYGEN_LIVE_AVATAR_API_KEY on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd /opt/ominis-backend
if [ -f .env ]; then
  grep -v '^HEYGEN_LIVE_AVATAR_API_KEY=' .env > .env.tmp || true
  echo "HEYGEN_LIVE_AVATAR_API_KEY=$HEYGEN_LIVE_AVATAR_API_KEY" >> .env.tmp
  mv .env.tmp .env
  sudo systemctl restart ominis-backend
  sleep 2
  sudo systemctl status ominis-backend --no-pager
  echo "Done. LiveAvatar API key configured."
else
  echo "No .env found. Run 20-sync-backend.sh first."
  exit 1
fi
REMOTECMD
