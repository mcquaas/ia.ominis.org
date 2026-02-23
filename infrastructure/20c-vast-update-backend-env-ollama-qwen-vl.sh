#!/bin/bash
# Update Haystack backend .env to use Vast Ollama (Qwen3 + Qwen2.5-VL) for chat and vision.
# Run after 24f and after pulling qwen3:14b and qwen2.5vl:7b on the instance.
# Usage: ./20c-vast-update-backend-env-ollama-qwen-vl.sh [URL]
#   Or create config/ollama_qwen_vast.txt with OLLAMA_QWEN_VAST_URL=http://IP:PORT
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ -n "$1" ]; then
  OLLAMA_QWEN_VAST_URL="$1"
elif [ -f "$CONFIG_DIR/ollama_qwen_vast.txt" ]; then
  source "$CONFIG_DIR/ollama_qwen_vast.txt"
else
  echo "Usage: $0 <OLLAMA_QWEN_VAST_URL>"
  echo "  Or create config/ollama_qwen_vast.txt with OLLAMA_QWEN_VAST_URL=http://IP:PORT"
  echo "  From Vast: Instance → IP & Port Info → mapping for 11434"
  exit 1
fi

if [ -z "$OLLAMA_QWEN_VAST_URL" ]; then
  echo "Error: OLLAMA_QWEN_VAST_URL not set"
  exit 1
fi

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:14b}"
VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"

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
echo "║     Backend .env: Ollama (Vast) Qwen3 + Qwen2.5-VL           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Backend: $BACKEND_IP"
echo "OLLAMA_URL: $OLLAMA_QWEN_VAST_URL"
echo "OLLAMA_MODEL: $OLLAMA_MODEL"
echo "VISION_MODEL: $VISION_MODEL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ -f .env ]; then
  grep -v '^OLLAMA_URL=' .env | grep -v '^OLLAMA_MODEL=' | grep -v '^VISION_MODEL=' | grep -v '^# Ollama (Vast)' > .env.tmp 2>/dev/null || true
  [ -s .env.tmp ] && mv .env.tmp .env || true
fi
echo "" >> .env
echo "# Ollama (Vast.ai) - Qwen3 chat + Qwen2.5-VL vision - 20c-vast" >> .env
echo "OLLAMA_URL=$OLLAMA_QWEN_VAST_URL" >> .env
echo "OLLAMA_MODEL=$OLLAMA_MODEL" >> .env
echo "VISION_MODEL=$VISION_MODEL" >> .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated. Chat uses $OLLAMA_MODEL, vision uses $VISION_MODEL at $OLLAMA_QWEN_VAST_URL"
echo ""
