#!/bin/bash
# Inyecta POWER_* en el .env del backend para que "GPT" (gpt-oss) aparezca en chat y dashboard.
# Edita config/power_gpt_server.txt con tu POWER_API_URL (URL del vLLM que sirve gpt-oss) y ejecuta este script.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

# Cargar valores: primero config/power_gpt_server.txt, luego env
if [ -f "$CONFIG_DIR/power_gpt_server.txt" ]; then
  source "$CONFIG_DIR/power_gpt_server.txt"
fi

POWER_API_URL="${POWER_API_URL:-}"
POWER_MODEL="${POWER_MODEL:-openai/gpt-oss-20b}"
POWER_API_KEY="${POWER_API_KEY:-EMPTY}"
POWER_TIMEOUT="${POWER_TIMEOUT:-120}"
POWER_INSTANCE_ID="${POWER_INSTANCE_ID:-}"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

echo "Actualizando POWER_* en backend $BACKEND_IP..."
echo "  POWER_API_URL=$POWER_API_URL"
echo "  POWER_MODEL=$POWER_MODEL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ ! -f .env ]; then
  echo "No .env found. Despliega el backend primero (17-deploy-haystack-backend.sh o 20-sync-backend.sh)."
  exit 1
fi
# Quitar líneas existentes de POWER_ y el comentario de bloque
grep -v '^POWER_API_URL=' .env | \
grep -v '^POWER_MODEL=' .env | \
grep -v '^POWER_API_KEY=' .env | \
grep -v '^POWER_TIMEOUT=' .env | \
grep -v '^POWER_INSTANCE_ID=' .env | \
grep -v '^# GPT (gpt-oss)' .env | \
grep -v '^# Si POWER_API_URL' .env > .env.tmp || true
mv .env.tmp .env
# Añadir bloque POWER
echo "# GPT (gpt-oss) - 20m" >> .env
echo "POWER_API_URL=$POWER_API_URL" >> .env
echo "POWER_MODEL=$POWER_MODEL" >> .env
echo "POWER_API_KEY=$POWER_API_KEY" >> .env
echo "POWER_TIMEOUT=$POWER_TIMEOUT" >> .env
echo "POWER_INSTANCE_ID=$POWER_INSTANCE_ID" >> .env
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env actualizado con POWER_*."
if [ -n "$POWER_API_URL" ]; then
  echo "  GPT aparecerá en el chat y en el dashboard."
else
  echo "  POWER_API_URL está vacía: GPT no se mostrará hasta que definas la URL del vLLM en config/power_gpt_server.txt y vuelvas a ejecutar este script."
fi
echo ""
