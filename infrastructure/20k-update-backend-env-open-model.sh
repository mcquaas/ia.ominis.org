#!/bin/bash
# Add OLLAMA_OPEN_MODEL to backend .env so "Ominis 2.0 Open" appears in the chat.
# Usage: OLLAMA_OPEN_MODEL=qwen3:14b ./infrastructure/20k-update-backend-env-open-model.sh
# Optional: OLLAMA_OPEN_URL=http://host:11434 (leave empty to use same server as OLLAMA_URL)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

OPEN_MODEL="${OLLAMA_OPEN_MODEL:-qwen3:14b}"
OPEN_URL="${OLLAMA_OPEN_URL:-}"

echo "Updating backend .env on $BACKEND_IP..."
echo "  OLLAMA_OPEN_MODEL=$OPEN_MODEL"
[ -n "$OPEN_URL" ] && echo "  OLLAMA_OPEN_URL=$OPEN_URL" || echo "  OLLAMA_OPEN_URL=(empty, use OLLAMA_URL)"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ ! -f .env ]; then
  echo "No .env found. Run 20-sync-backend.sh first."
  exit 1
fi
grep -v '^OLLAMA_OPEN_MODEL=' .env | grep -v '^OLLAMA_OPEN_URL=' | grep -v '^# Ominis 2.0 Open' > .env.tmp || true
echo "# Ominis 2.0 Open (optional chat model) - 20k" >> .env.tmp
echo "OLLAMA_OPEN_MODEL=$OPEN_MODEL" >> .env.tmp
[ -n "$OPEN_URL" ] && echo "OLLAMA_OPEN_URL=$OPEN_URL" >> .env.tmp || true
mv .env.tmp .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
echo "Done. Ominis 2.0 Open will appear when the model is available on the Ollama server."
REMOTECMD

echo ""
echo "✓ Backend .env updated. Ensure the Ollama server has the model: ollama pull $OPEN_MODEL"
