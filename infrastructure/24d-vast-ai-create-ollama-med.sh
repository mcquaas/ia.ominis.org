#!/bin/bash
# Create a Vast.ai instance running Ollama for Ominis 2.0 Med (Med42). Same CLI/SSM as gpt-oss.
# After creation: get IP and port for 11434 from instance, pull med42 (see docs), set OLLAMA_MED_URL and run 20med.
# See: docs/VAST_AI_POWER.md (section "Ominis 2.0 Med on Vast")

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VASTAI_CMD=""
[ -x "$SCRIPT_DIR/venv-vast/bin/vastai" ] && VASTAI_CMD="$SCRIPT_DIR/venv-vast/bin/vastai"
[ -z "$VASTAI_CMD" ] && command -v vastai &>/dev/null && VASTAI_CMD="vastai"

if [ "${VAST_USE_SSM:-}" = "1" ] && command -v aws &>/dev/null; then
  key=$(aws ssm get-parameter --name /ominis/vastai/api-key --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
  [ -n "$key" ] && export VASTAI_API_KEY="$key" || true
fi

if [ -z "$VASTAI_CMD" ]; then
  echo "vastai CLI not found. Run: ./infrastructure/setup-vast-cli.sh"
  exit 1
fi

IMAGE="ollama/ollama"
DISK=50
# Expose Ollama API; GPU required for inference
ENV_OPTS="-p 11434:11434 --gpus all"

echo "=== Vast.ai: create Ollama instance (Ominis 2.0 Med) ==="
echo "Image: $IMAGE"
echo ""

# Query: on-demand, A100 SXM4, num_gpus = 1
OFFER_QUERY='num_gpus=1 gpu_ram>=40 gpu_name in [\"A100_SXM4\", \"A100_PCIE\"]' # Prefer 40GB A100s
OFFER_JSON=$($VASTAI_CMD search offers "$OFFER_QUERY" -d --limit 1 --raw 2>/dev/null || true)
if [ -z "$OFFER_JSON" ]; then
  echo "No on-demand offers found for A100 SXM4 (1 GPU). Try: vastai search offers '$OFFER_QUERY' -d"
  exit 1
fi

OFFER_ID=$(echo "$OFFER_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and len(d) > 0:
        print(d[0].get('id', d[0].get('ask_contract_id', '')))
    elif isinstance(d, dict) and 'offers' in d:
        offers = d['offers']
        print(offers[0].get('id', offers[0].get('ask_contract_id', ''))) if offers else sys.exit(1)
    else:
        print(d.get('id', d.get('ask_contract_id', '')))
except Exception:
    sys.exit(2)
" 2>/dev/null || true)

if [ -z "$OFFER_ID" ] || [ "$OFFER_ID" = "null" ]; then
  echo "Could not parse offer ID. Create manually:"
  echo "  vastai create instance <OFFER_ID> --image $IMAGE --disk $DISK --env '$ENV_OPTS'"
  exit 1
fi

echo "Using offer ID: $OFFER_ID"
echo "Creating instance..."
RESULT=$($VASTAI_CMD create instance "$OFFER_ID" --image "$IMAGE" --disk "$DISK" --env "$ENV_OPTS" --raw 2>&1) || true

if echo "$RESULT" | grep -q '"success": true'; then
  CONTRACT=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('new_contract',''))" 2>/dev/null || true)
  echo "Instance created. Contract ID: $CONTRACT"
  echo ""
  echo "Next steps:"
  echo "  1. vastai show instances   # wait until status is 'running'"
  echo "  2. Instance → IP Port Info: get mapping for 11434 (e.g. 1.2.3.4:45678 -> 11434/tcp)"
  echo "  3. Pull Med42: curl -X POST http://<IP>:<PORT>/api/pull -d '{\"name\":\"med42\"}'"
  echo "  4. config/ollama_med_server.txt: OLLAMA_MED_URL=http://<IP>:<PORT>"
  echo "  5. ./infrastructure/20med-update-backend-env-ollama-med.sh"
else
  echo "Create failed:"
  echo "$RESULT"
  exit 1
fi
