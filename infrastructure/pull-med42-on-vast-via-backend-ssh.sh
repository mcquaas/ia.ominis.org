#!/bin/bash
# Pull Med42 on the Vast Ollama instance using SSH from the backend EC2.
# This works around the "connection refused" issue when trying to connect directly to the public port.
# Usage: ./infrastructure/pull-med42-on-vast-via-backend-ssh.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

# Load backend EC2 details
source "$CONFIG_DIR/haystack_backend.txt"
BACKEND_KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
BACKEND_SSH_USER="ubuntu"

# Vast SSH details (key generated on backend, used from backend)
VAST_SSH_KEY_FILE="~/.ssh/vast_ec2" # This key is on the backend EC2
VAST_SSH_PORT="13782"
VAST_SSH_HOST="root@ssh8.vast.ai"

# Load Med model name from config, default to med42
MED_MODEL="med42"
if [ -f "$CONFIG_DIR/ollama_med_server.txt" ]; then
  source "$CONFIG_DIR/ollama_med_server.txt"
  MED_MODEL="${OLLAMA_MED_MODEL:-med42}"
fi

echo "=== Pulling Med42 on Vast Ollama via backend EC2 SSH ==="
echo "  Backend EC2: $BACKEND_IP"
echo "  Vast Instance: ssh8.vast.ai:$VAST_SSH_PORT"
echo "  Model: $MED_MODEL"
echo ""

# Nested SSH:
# 1. Connect to backend EC2
# 2. From backend EC2, connect to Vast, find Ollama container, and run 'ollama pull med42'
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i "$BACKEND_KEY_FILE" "$BACKEND_SSH_USER@$BACKEND_IP" << EOF
  set -e
  echo "  (On Backend EC2) Connecting to Vast instance..."
  # Use the key on the EC2, not the local machine's key
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i $VAST_SSH_KEY_FILE -p $VAST_SSH_PORT $VAST_SSH_HOST ' \
    echo "  (On Vast) Finding Ollama container..."
    CONTAINER_ID=$(docker ps --filter ancestor=ollama/ollama --format "{{.ID}}")
    if [ -z "$CONTAINER_ID" ]; then
      echo "  (On Vast) Error: Ollama container not found." >&2
      exit 1
    fi
    echo "  (On Vast) Found container: $CONTAINER_ID. Pulling $MED_MODEL..."
    docker exec -it "$CONTAINER_ID" ollama pull "$MED_MODEL"
    echo "  (On Vast) Listing models..."
    docker exec -it "$CONTAINER_ID" ollama list
    echo "  (On Vast) Pull command finished."
  '
  echo "  (On Backend EC2) SSH to Vast finished."
EOF

echo ""
echo "✓ Med42 pull command sent to Vast instance via backend EC2."
echo "  Ahora, el modelo debería estar disponible en la instancia Vast de Ollama."
echo "  Para que el backend lo use en el chat, el puerto público de Vast (69.63.236.190:26137) debe ser accesible desde el EC2."
echo "  Si aún tienes 'connection refused', el backend no podrá conectar. Reinicia la instancia Vast o revisa su firewall."
echo ""
