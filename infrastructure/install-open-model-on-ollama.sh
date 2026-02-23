#!/bin/bash
# Install the model for "Ominis 2.0 Open" on the Ollama GPU server.
# Uses config/ollama_gpu_server.txt by default (g4dn). Override with OLLAMA_HOST and KEY_FILE if you use the g5 (Falcon) server.
# Usage: ./infrastructure/install-open-model-on-ollama.sh
#    or: OLLAMA_HOST=18.235.182.22 KEY_FILE=config/ominis-falcon-gpu-key.pem ./infrastructure/install-open-model-on-ollama.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

# Default: g4dn from ollama_gpu_server.txt
if [ -f "$CONFIG_DIR/ollama_gpu_server.txt" ]; then
  source "$CONFIG_DIR/ollama_gpu_server.txt"
  OLLAMA_HOST="${OLLAMA_HOST:-${GPU_ELASTIC_IP}}"
  KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-ollama-gpu-key.pem}"
fi

# Optional: use Falcon/g5 server
if [ -f "$CONFIG_DIR/falcon_gpu_server.txt" ] && [ -z "$OLLAMA_HOST" ]; then
  source "$CONFIG_DIR/falcon_gpu_server.txt"
  OLLAMA_HOST="${OLLAMA_HOST:-${FALCON_ELASTIC_IP}}"
  KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-falcon-gpu-key.pem}"
fi

OLLAMA_HOST="${OLLAMA_HOST:?Set OLLAMA_HOST or provide config/ollama_gpu_server.txt}"
OPEN_MODEL="${OLLAMA_OPEN_MODEL:-qwen3:14b}"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: KEY_FILE not found: $KEY_FILE"
  echo "  g4dn: config/ominis-ollama-gpu-key.pem"
  echo "  g5:   config/ominis-falcon-gpu-key.pem"
  exit 1
fi

echo "Installing Ominis 2.0 Open model on Ollama server..."
echo "  Host: $OLLAMA_HOST"
echo "  Model: $OPEN_MODEL"
echo ""

ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$KEY_FILE" "$SSH_USER@$OLLAMA_HOST" << REMOTECMD
set -e
echo "Pulling $OPEN_MODEL (this may take a few minutes)..."
ollama pull $OPEN_MODEL
ollama list
echo "Done. Restart backend or run 20k-update-backend-env-open-model.sh so OLLAMA_OPEN_MODEL=$OPEN_MODEL is set."
REMOTECMD

echo ""
echo "✓ Model $OPEN_MODEL installed. Run: OLLAMA_OPEN_MODEL=$OPEN_MODEL ./infrastructure/20k-update-backend-env-open-model.sh"
