#!/bin/bash
# Create a Vast.ai instance running gpt-oss-20b (vLLM). Uses first available on-demand offer with 16+ GB VRAM.
# Uses infrastructure/venv-vast if present (run ./infrastructure/setup-vast-cli.sh once). API key: set via vastai set api-key or VAST_USE_SSM=1.
# See: docs/VAST_AI_POWER.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VASTAI_CMD=""
[ -x "$SCRIPT_DIR/venv-vast/bin/vastai" ] && VASTAI_CMD="$SCRIPT_DIR/venv-vast/bin/vastai"
[ -z "$VASTAI_CMD" ] && command -v vastai &>/dev/null && VASTAI_CMD="vastai"

# Optional: load API key from AWS SSM
if [ "${VAST_USE_SSM:-}" = "1" ] && command -v aws &>/dev/null; then
  key=$(aws ssm get-parameter --name /ominis/vastai/api-key --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
  [ -n "$key" ] && export VASTAI_API_KEY="$key" || true
fi

if [ -z "$VASTAI_CMD" ]; then
  echo "vastai CLI not found. Run once: ./infrastructure/setup-vast-cli.sh"
  echo "Then: $SCRIPT_DIR/venv-vast/bin/vastai set api-key YOUR_KEY"
  echo "Or run with VAST_USE_SSM=1 and AWS CLI configured to use key from SSM."
  exit 1
fi

IMAGE="vllm/vllm-openai:gptoss"
DISK=50
# Entrypoint args: no --ssh/--jupyter => run container as-is with these args
ARGS="--model openai/gpt-oss-20b --host 0.0.0.0"
ENV_OPTS="-p 8000:8000 --gpus all --ipc=host"

echo "=== Vast.ai: create gpt-oss-20b instance ==="
echo "Image: $IMAGE"
echo "Args:  $ARGS"
echo ""

# Get first on-demand offer with 16+ GB GPU (raw JSON to parse offer id)
OFFER_JSON=$($VASTAI_CMD search offers --on-demand -g 16 --limit 1 --raw 2>/dev/null || true)
if [ -z "$OFFER_JSON" ]; then
  echo "No on-demand offers found with 16+ GB VRAM. Try: vastai search offers --on-demand -g 16"
  exit 1
fi

# Extract id (offer/ask id). Format may be list of objects with "id" field
OFFER_ID=$(echo "$OFFER_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and len(d) > 0:
        print(d[0].get('id', d[0].get('ask_id', '')))
    elif isinstance(d, dict) and 'offers' in d:
        offers = d['offers']
        print(offers[0].get('id', offers[0].get('ask_id', ''))) if offers else sys.exit(1)
    else:
        print(d.get('id', d.get('ask_id', '')))
except Exception as e:
    sys.exit(2)
" 2>/dev/null || true)

if [ -z "$OFFER_ID" ] || [ "$OFFER_ID" = "null" ]; then
  echo "Could not parse offer ID from search. Showing raw result:"
  echo "$OFFER_JSON" | head -20
  echo ""
  echo "Create manually with: vastai create instance <OFFER_ID> --image $IMAGE --disk $DISK --env '$ENV_OPTS' --args --model openai/gpt-oss-20b --host 0.0.0.0"
  exit 1
fi

echo "Using offer ID: $OFFER_ID"
echo "Creating instance (this may take a minute)..."
echo ""

# Create: no --ssh / --jupyter => entrypoint/args mode
RESULT=$($VASTAI_CMD create instance "$OFFER_ID" --image "$IMAGE" --disk "$DISK" --env "$ENV_OPTS" --args --model openai/gpt-oss-20b --host 0.0.0.0 --raw 2>&1) || true

if echo "$RESULT" | grep -q '"success": true'; then
  CONTRACT=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('new_contract',''))" 2>/dev/null || true)
  echo "Instance created. Contract ID: $CONTRACT"
  echo ""
  echo "Next steps:"
  echo "  1. $VASTAI_CMD show instances   # wait until status is 'running'"
  echo "  2. Open instance → IP Port Info, find mapping for port 8000 (e.g. 1.2.3.4:34567 -> 8000/tcp)"
  echo "  3. Set config/power_gpt_server.txt: POWER_API_URL=http://<PUBLIC_IP>:<EXTERNAL_PORT>"
  echo "  4. ./infrastructure/20m-update-backend-env-power-gpt.sh"
  echo ""
  echo "Model download on first start can take several minutes. Check: $VASTAI_CMD show instance $CONTRACT"
else
  echo "Create failed:"
  echo "$RESULT"
  exit 1
fi
