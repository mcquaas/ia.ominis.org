#!/bin/bash
# Pull Qwen3 and Qwen2.5-VL on the Vast Ollama instance by calling the API from the backend EC2.
# The backend can often reach Vast when your local machine cannot.
# Usage: ./infrastructure/pull-ollama-qwen-vl-via-backend.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/ollama_qwen_vast.txt" ]; then
  echo "Error: config/ollama_qwen_vast.txt not found. Run 20c setup first."
  exit 1
fi
source "$CONFIG_DIR/ollama_qwen_vast.txt"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"

if [ -z "$OLLAMA_QWEN_VAST_URL" ]; then
  echo "Error: OLLAMA_QWEN_VAST_URL not set in config/ollama_qwen_vast.txt"
  exit 1
fi

echo "=== Pulling Ollama models on Vast via backend EC2 ==="
echo "  Backend: $BACKEND_IP"
echo "  Ollama:  $OLLAMA_QWEN_VAST_URL"
echo "  Models:  qwen3:14b, qwen2.5vl:7b"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << EOF
set -e
echo "  Pulling qwen3:14b (may take several minutes)..."
curl -s -X POST "$OLLAMA_QWEN_VAST_URL/api/pull" -d '{"name":"qwen3:14b"}' || true
echo ""
echo "  Pulling qwen2.5vl:7b (may take several minutes)..."
curl -s -X POST "$OLLAMA_QWEN_VAST_URL/api/pull" -d '{"name":"qwen2.5vl:7b"}' || true
echo ""
echo "  Listing models..."
curl -s "$OLLAMA_QWEN_VAST_URL/api/tags" | head -50
EOF

echo ""
echo "✓ Pull commands sent. If the backend can reach Vast, models will appear in Ollama."
echo "  Check Vast instance logs or run: curl -s $OLLAMA_QWEN_VAST_URL/api/tags"
echo ""
