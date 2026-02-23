#!/bin/bash
# Inyecta OLLAMA_MED_* en el .env del backend para que "Ominis 2.0 Med" (Med42-v2) aparezca en chat y dashboard.
# config/ollama_med_server.txt: OLLAMA_MED_MODEL=med42; OLLAMA_MED_URL vacío = mismo Ollama que Ominis 2.0, o URL Vast (docs/VAST_AI_POWER.md §10).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

OLLAMA_MED_MODEL=""
OLLAMA_MED_URL=""
OLLAMA_MED_INSTANCE_ID=""
if [ -f "$CONFIG_DIR/ollama_med_server.txt" ]; then
  source "$CONFIG_DIR/ollama_med_server.txt"
fi

OLLAMA_MED_MODEL="${OLLAMA_MED_MODEL:-}"
OLLAMA_MED_URL="${OLLAMA_MED_URL:-}"
OLLAMA_MED_INSTANCE_ID="${OLLAMA_MED_INSTANCE_ID:-}"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

echo "Actualizando OLLAMA_MED_* en backend $BACKEND_IP..."
echo "  OLLAMA_MED_MODEL=$OLLAMA_MED_MODEL"
echo "  OLLAMA_MED_URL=$OLLAMA_MED_URL"
echo "  OLLAMA_MED_INSTANCE_ID=$OLLAMA_MED_INSTANCE_ID"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ ! -f .env ]; then
  echo "No .env found. Despliega el backend primero."
  exit 1
fi
grep -v '^OLLAMA_MED_MODEL=' .env | grep -v '^OLLAMA_MED_URL=' .env | grep -v '^OLLAMA_MED_INSTANCE_ID=' .env | grep -v '^# Ominis 2.0 Med' .env > .env.tmp || true
mv .env.tmp .env
echo "# Ominis 2.0 Med (Med42-v2) - 20med" >> .env
echo "OLLAMA_MED_MODEL=$OLLAMA_MED_MODEL" >> .env
echo "OLLAMA_MED_URL=$OLLAMA_MED_URL" >> .env
echo "OLLAMA_MED_INSTANCE_ID=$OLLAMA_MED_INSTANCE_ID" >> .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env actualizado con OLLAMA_MED_*."
if [ -n "$OLLAMA_MED_MODEL" ]; then
  echo "  Ominis 2.0 Med aparecerá en el chat. Asegúrate de tener el modelo en Ollama: ollama pull $OLLAMA_MED_MODEL"
else
  echo "  OLLAMA_MED_MODEL vacío: define OLLAMA_MED_MODEL en config/ollama_med_server.txt y vuelve a ejecutar."
fi
echo ""
