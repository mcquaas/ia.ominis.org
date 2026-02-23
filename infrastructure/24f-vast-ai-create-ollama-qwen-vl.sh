#!/bin/bash
# Create a Vast.ai instance running Ollama with Qwen3 (chat) + Qwen2.5-VL (vision).
# A100 40GB so both models can be loaded. After creation: pull models, set OLLAMA_URL and VISION_MODEL, run 20c.
# See: docs/VAST_OLLAMA_QWEN_VL.md

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
DISK=60
# Expose Ollama API and bind to all interfaces so the backend can reach it (default is localhost-only).
ENV_OPTS="-p 11434:11434 -e OLLAMA_HOST=0.0.0.0 --gpus all"
# Start ollama serve on boot (SSH launch type does not run it by default).
ONSTART_CMD='export OLLAMA_HOST=0.0.0.0; nohup ollama serve >> /var/log/ollama.log 2>&1 &'

echo "=== Vast.ai: create Ollama (Qwen3 + Qwen2.5-VL) ==="
echo "Image: $IMAGE"
echo "Models to pull after start: qwen3:14b (chat), qwen2.5vl:7b (vision)"
echo ""

# Query: A100 40GB so both models fit in VRAM
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
  echo "  vastai create instance <OFFER_ID> --image $IMAGE --disk $DISK --env '$ENV_OPTS'"
  exit 1
fi

echo "Using offer ID: $OFFER_ID"
echo "Creating instance..."
RESULT=$($VASTAI_CMD create instance "$OFFER_ID" --image "$IMAGE" --disk "$DISK" --env "$ENV_OPTS" --onstart-cmd "$ONSTART_CMD" --raw 2>&1) || true

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
  echo "  2. Instance → IP & Port Info: get mapping for 11434 (e.g. 1.2.3.4:45678 -> 11434/tcp)"
  echo "  3. Pull models (from any machine that can reach the instance):"
  echo "     curl -X POST http://<IP>:<PORT>/api/pull -d '{\"name\":\"qwen3:14b\"}'"
  echo "     curl -X POST http://<IP>:<PORT>/api/pull -d '{\"name\":\"qwen2.5vl:7b\"}'"
  echo "  4. config/ollama_qwen_vast.txt: OLLAMA_QWEN_VAST_URL=http://<IP>:<PORT>"
  echo "  5. ./infrastructure/20c-vast-update-backend-env-ollama-qwen-vl.sh"
else
  echo "Create failed:"
  echo "$RESULT"
  exit 1
fi
