#!/bin/bash
# Install Med42 on the Ollama GPU server (g4dn by default). Use so "Ominis 2.0 Med" works.
# Uses config/ollama_gpu_server.txt (GPU_ELASTIC_IP) and config/ollama_med_server.txt (OLLAMA_MED_MODEL).
# Usage: ./infrastructure/install-med42-on-ollama.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ -f "$CONFIG_DIR/ollama_gpu_server.txt" ]; then
  source "$CONFIG_DIR/ollama_gpu_server.txt"
  OLLAMA_HOST="${OLLAMA_HOST:-${GPU_ELASTIC_IP}}"
  KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-ollama-gpu-key.pem}"
fi
if [ -f "$CONFIG_DIR/ollama_med_server.txt" ]; then
  source "$CONFIG_DIR/ollama_med_server.txt"
fi

OLLAMA_HOST="${OLLAMA_HOST:?Set OLLAMA_HOST or provide config/ollama_gpu_server.txt}"
MED_MODEL="${OLLAMA_MED_MODEL:-med42}"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: KEY_FILE not found: $KEY_FILE"
  echo "  Default: config/ominis-ollama-gpu-key.pem (g4dn)"
  exit 1
fi

echo "Installing Ominis 2.0 Med (Med42) on Ollama server..."
echo "  Host: $OLLAMA_HOST"
echo "  Model: $MED_MODEL"
echo ""

ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$KEY_FILE" "$SSH_USER@$OLLAMA_HOST" << REMOTECMD
set -e
echo "Pulling $MED_MODEL (this may take several minutes)..."
ollama pull $MED_MODEL
ollama list
echo "Done."
REMOTECMD

echo ""
echo "✓ Model $MED_MODEL installed."
echo "  If OLLAMA_MED_URL is empty, backend uses this server for Med. Run: ./infrastructure/20med-update-backend-env-ollama-med.sh"
echo "  For faster Med, use a Vast Ollama instance (see docs/VAST_AI_POWER.md §10) and set OLLAMA_MED_URL in config/ollama_med_server.txt"
echo ""
