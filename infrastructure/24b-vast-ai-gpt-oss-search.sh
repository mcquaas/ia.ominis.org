#!/bin/bash
# Search Vast.ai for GPUs suitable for gpt-oss (Ominis Power) and print template/config hints.
# Uses infrastructure/venv-vast if present (run ./infrastructure/setup-vast-cli.sh once).
# See: docs/VAST_AI_POWER.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VASTAI_CMD=""
[ -x "$SCRIPT_DIR/venv-vast/bin/vastai" ] && VASTAI_CMD="$SCRIPT_DIR/venv-vast/bin/vastai"
[ -z "$VASTAI_CMD" ] && command -v vastai &>/dev/null && VASTAI_CMD="vastai"

echo "=== Vast.ai GPU search for gpt-oss (Ominis Power) ==="
echo ""

if [ -z "$VASTAI_CMD" ]; then
  echo "vastai CLI not found. Run once: ./infrastructure/setup-vast-cli.sh"
  echo "Then: $SCRIPT_DIR/venv-vast/bin/vastai set api-key YOUR_API_KEY"
  echo ""
  echo "Manual: open https://cloud.vast.ai/create/"
  echo "  - Rental: On-demand (best availability)"
  echo "  - GPU: 16+ GB VRAM (A10G, RTX 3090, etc.)"
  echo "  - Prefer 'Secure Cloud' (blue) for production"
  echo "  - Template: image vllm/vllm-openai:gptoss, Entrypoint, args: --model openai/gpt-oss-20b --host 0.0.0.0"
  echo "  - Docker options: -p 8000:8000 --gpus all --ipc=host"
  echo ""
  echo "After rent: get PUBLIC_IP:EXTERNAL_PORT from instance 'IP Port Info' (port 8000)."
  echo "Set in config/power_gpt_server.txt: POWER_API_URL=http://PUBLIC_IP:EXTERNAL_PORT"
  echo "Run: ./infrastructure/20m-update-backend-env-power-gpt.sh"
  exit 0
fi

echo "Searching on-demand offers with GPU and 16+ GB VRAM..."
echo ""

# Search: on-demand, gpu, min 16GB (gpu_ram is in GB in filters)
$VASTAI_CMD search offers --on-demand -g 16 2>/dev/null | head -80 || true

echo ""
echo "--- Template for gpt-oss ---"
echo "Image:    vllm/vllm-openai:gptoss"
echo "Launch:   Entrypoint"
echo "Args:     --model openai/gpt-oss-20b --host 0.0.0.0"
echo "Docker:   -p 8000:8000 --gpus all --ipc=host"
echo ""
echo "After creating the instance, get PUBLIC_IP:PORT from the instance's IP Port Info (mapping for 8000)."
echo "Then: config/power_gpt_server.txt -> POWER_API_URL=http://PUBLIC_IP:PORT"
echo "      ./infrastructure/20m-update-backend-env-power-gpt.sh"
echo ""
echo "Full guide: docs/VAST_AI_POWER.md"
