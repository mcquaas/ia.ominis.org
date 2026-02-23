#!/bin/bash
# Inject Pipecat Cloud config into backend .env for /live page (ominis-2.0-clinic mode).
# Usage: PIPECAT_AGENT_NAME=ominis-live-avatar PIPECAT_API_TOKEN=xxx ./infrastructure/20j-update-backend-env-pipecat.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

if [ -z "$PIPECAT_AGENT_NAME" ] || [ -z "$PIPECAT_API_TOKEN" ]; then
    echo "Usage: PIPECAT_AGENT_NAME=xxx PIPECAT_API_TOKEN=xxx $0"
    echo "Get Pipecat token at https://pipecat.ai after deploying the agent."
    exit 1
fi

echo "Updating Pipecat config on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd /opt/ominis-backend
if [ -f .env ]; then
  grep -v '^PIPECAT_AGENT_NAME=' .env > .env.tmp || true
  grep -v '^PIPECAT_API_TOKEN=' .env.tmp > .env.tmp2 || true
  mv .env.tmp2 .env.tmp
  echo "PIPECAT_AGENT_NAME=$PIPECAT_AGENT_NAME" >> .env.tmp
  echo "PIPECAT_API_TOKEN=$PIPECAT_API_TOKEN" >> .env.tmp
  mv .env.tmp .env
  sudo systemctl restart ominis-backend
  sleep 2
  sudo systemctl status ominis-backend --no-pager
  echo "Done. /live now uses Pipecat (ominis-2.0-clinic)."
else
  echo "No .env found. Run 20-sync-backend.sh first."
  exit 1
fi
REMOTECMD
