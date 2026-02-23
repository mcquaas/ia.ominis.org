#!/bin/bash
# Set OLLAMA_CLINIC_MODEL on backend .env when the Ollama server has a different name (e.g. cniongolo/biomistral).
# Usage: OLLAMA_CLINIC_MODEL=cniongolo/biomistral ./infrastructure/20l-update-backend-env-clinic-model.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

CLINIC_MODEL="${OLLAMA_CLINIC_MODEL:-cniongolo/biomistral}"

echo "Updating OLLAMA_CLINIC_MODEL on backend $BACKEND_IP to $CLINIC_MODEL..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd /opt/ominis-backend
if [ ! -f .env ]; then
  echo "No .env found. Run 20-sync-backend.sh first."
  exit 1
fi
grep -v '^OLLAMA_CLINIC_MODEL=' .env > .env.tmp || true
echo "OLLAMA_CLINIC_MODEL=$CLINIC_MODEL" >> .env.tmp
mv .env.tmp .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
echo "Done. Ominis 2.0 Clinic will use model: $CLINIC_MODEL"
REMOTECMD
