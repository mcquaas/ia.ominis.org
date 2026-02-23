#!/bin/bash
# Run the Med42 pull from the backend EC2 (so the request goes from the same IP that will call Vast in production).
# If this fails with "Connection refused", run the pull from your laptop instead:
#   ./infrastructure/pull-med42-via-api.sh http://69.63.236.190:26137
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"
[ -f "$CONFIG_DIR/ollama_med_server.txt" ] && source "$CONFIG_DIR/ollama_med_server.txt"

OLLAMA_MED_URL="${OLLAMA_MED_URL:-}"
MED_MODEL="${OLLAMA_MED_MODEL:-med42}"
KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"

if [ -z "$OLLAMA_MED_URL" ]; then
  echo "Error: OLLAMA_MED_URL not set in config/ollama_med_server.txt"
  exit 1
fi

BASE="${OLLAMA_MED_URL%/}"
echo "Pulling $MED_MODEL from backend EC2 ($BACKEND_IP) to $BASE ..."
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" "curl -s -X POST '$BASE/api/pull' -d '{\"name\":\"$MED_MODEL\"}' --max-time 600"

echo ""
echo "Done. If you saw JSON with 'status', the pull was requested. If you saw 'Connection refused', run from your laptop: ./infrastructure/pull-med42-via-api.sh $BASE"
echo ""
