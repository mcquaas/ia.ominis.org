#!/bin/bash
# Create a Vast.ai instance running vLLM with OpenScholar 128K (32K context).
# Uses public image vllm/vllm-openai and passes model args. No EC2; no start/stop from dashboard.
# After creation: get IP and port for 8000 from instance, set OPENSCHOLAR_128K_API_URL and run 20a-vast-update-backend-env-openscholar-128k.sh
# See: docs/OPENSCHOLAR_128K_VAST.md

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

IMAGE="vllm/vllm-openai:latest"
DISK=80
# Expose vLLM OpenAI-compatible API on 8000
ENV_OPTS="-p 8000:8000 --gpus all"
# Arguments passed to vLLM entrypoint. Model as positional (vLLM v0.13+); no --model, no --raw.
VLLM_ARGS="OpenSciLM/Llama-3.1_OpenScholar-8B --served-model-name openscholar --host 0.0.0.0 --port 8000 --max-model-len 32768 --gpu-memory-utilization 0.9 --trust-remote-code"

echo "=== Vast.ai: create OpenScholar 128K (vLLM) ==="
echo "Image: $IMAGE"
echo "Model: OpenSciLM/Llama-3.1_OpenScholar-8B (max-model-len 32768)"
echo ""

# Query: 1 GPU, A100 40GB (recommended for OpenScholar 128K / 32K context)
OFFER_QUERY="num_gpus=1 gpu_ram>=40 gpu_name in [\"A100_SXM4\", \"A100_PCIE\"]"
OFFER_JSON=$($VASTAI_CMD search offers "$OFFER_QUERY" -d --limit 1 --raw 2>/dev/null || true)
if [ -z "$OFFER_JSON" ] || [ "$OFFER_JSON" = "[]" ]; then
  echo "No A100 offers found. Try: vastai search offers \"$OFFER_QUERY\" -d"
  exit 1
fi

OFFER_ID=$(echo "$OFFER_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if isinstance(d, list) and len(d) > 0:
        print(d[0].get('id', d[0].get('ask_contract_id', '')))
    elif isinstance(d, dict):
        print(d.get('id', d.get('ask_contract_id', '')))
    else:
        sys.exit(1)
except Exception:
    sys.exit(2)
" 2>/dev/null || true)

if [ -z "$OFFER_ID" ] || [ "$OFFER_ID" = "null" ]; then
  echo "Could not parse offer ID. Create manually:"
  echo "  vastai create instance <OFFER_ID> --image $IMAGE --disk $DISK --env '$ENV_OPTS' --args $VLLM_ARGS"
  exit 1
fi

echo "Using offer ID: $OFFER_ID"
echo "Creating instance (entrypoint mode; model will load on first request)..."
# --args must be last so --raw is not forwarded to the container (would cause vllm: error: unrecognized arguments: --raw)
RESULT=$($VASTAI_CMD create instance "$OFFER_ID" --image "$IMAGE" --disk "$DISK" --env "$ENV_OPTS" --raw --args $VLLM_ARGS 2>&1) || true

if echo "$RESULT" | grep -qE '"success":\s*true|'"'"'success'"'"':\s*True'; then
  CONTRACT=$(echo "$RESULT" | python3 -c "
import re, sys
s = sys.stdin.read()
m = re.search(r\"'new_contract':\s*(\d+)\", s) or re.search(r'\"new_contract\":\s*(\d+)', s)
print(m.group(1) if m else '')
" 2>/dev/null || true)
  echo "Instance created. Contract ID: $CONTRACT"
  echo ""
  echo "Next steps:"
  echo "  1. vastai show instances   # wait until status is 'running'"
  echo "  2. Instance → IP Port Info: get mapping for 8000 (e.g. 1.2.3.4:45678 -> 8000/tcp)"
  echo "  3. Backend .env: OPENSCHOLAR_128K_API_URL=http://<IP>:<PORT>  (no instance ID; Vast has no start/stop)"
  echo "  4. ./infrastructure/20a-vast-update-backend-env-openscholar-128k.sh  # pass URL or set in config"
else
  echo "Create failed:"
  echo "$RESULT"
  exit 1
fi
