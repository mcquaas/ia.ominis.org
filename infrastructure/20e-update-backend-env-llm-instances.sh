#!/bin/bash
# Inject OLLAMA_INSTANCE_ID and OLLAMA_CLINIC_INSTANCE_ID into backend .env so the
# dashboard switches can start/stop the LLM GPU instance (g4dn runs both Qwen and BioMistral).
# Uses config/ollama_gpu_server.txt. Falcon removed; both models use g4dn.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/ollama_gpu_server.txt" ]; then
    echo "Error: config/ollama_gpu_server.txt not found (run 13-deploy-gpu-ollama-us.sh first)."
    exit 1
fi
source "$CONFIG_DIR/ollama_gpu_server.txt"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
    echo "Error: config/haystack_backend.txt not found."
    exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

# Both ominis-2.0 (Qwen) and ominis-2.0-clinic (BioMistral) on same g4dn
OLLAMA_INSTANCE_ID="${GPU_INSTANCE_ID:-}"
OLLAMA_CLINIC_INSTANCE_ID="${GPU_INSTANCE_ID:-}"

echo "Injecting LLM instance IDs into backend .env (backend: $BACKEND_IP)..."
echo "  OLLAMA_INSTANCE_ID=$OLLAMA_INSTANCE_ID (ominis-2.0 / Ominis 2.0 Clinic - g4dn)"
echo "  OLLAMA_CLINIC_INSTANCE_ID=$OLLAMA_CLINIC_INSTANCE_ID (same g4dn)"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ -f .env ]; then
  grep -v '^OLLAMA_INSTANCE_ID=' .env | grep -v '^OLLAMA_CLINIC_INSTANCE_ID=' | grep -v '^# LLM instance IDs' > .env.tmp
  sudo mv .env.tmp .env
  sudo chown ubuntu:ubuntu .env
fi
echo "# LLM instance IDs (dashboard start/stop) - 20e" | sudo tee -a .env > /dev/null
echo "OLLAMA_INSTANCE_ID=$OLLAMA_INSTANCE_ID" | sudo tee -a .env > /dev/null
echo "OLLAMA_CLINIC_INSTANCE_ID=$OLLAMA_CLINIC_INSTANCE_ID" | sudo tee -a .env > /dev/null
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated with LLM instance IDs."
echo "  Dashboard switches for ominis-2.0 and ominis-2.0-clinic will show g4dn status."
echo ""
