#!/bin/bash
# Runs gpt-oss via official vLLM Docker image (avoids tokenizer compat issues with pip install).
# Use after 24-install-gpt-oss-vllm.sh failed or run on a clean GPU host with Docker + nvidia-container-toolkit.
# VLLM_HOST=18.235.182.22 KEY_FILE=config/ominis-falcon-gpu-key.pem bash infrastructure/24a-run-gpt-oss-docker.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
VLLM_HOST="${VLLM_HOST:-}"
KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-falcon-gpu-key.pem}"
SSH_USER="${SSH_USER:-ubuntu}"

[ -z "$VLLM_HOST" ] && echo "VLLM_HOST required" && exit 1
[ ! -f "$KEY_FILE" ] && echo "KEY_FILE not found: $KEY_FILE" && exit 1

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$VLLM_HOST" << 'REMOTE'
set -e
export DEBIAN_FRONTEND=noninteractive

# Stop existing venv-based service if present
sudo systemctl stop ominis-vllm-gptoss 2>/dev/null || true

# Install Docker if missing
if ! command -v docker &>/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -qq
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker ubuntu
fi

# Install nvidia-container-toolkit if missing
if ! dpkg -l nvidia-container-toolkit &>/dev/null; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update -qq
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
fi

# Remove old container if present
sudo docker rm -f ominis-gptoss 2>/dev/null || true

# Run gpt-oss image (gptoss tag has correct tokenizer/CUDA stack)
sudo docker run -d \
  --name ominis-gptoss \
  --restart unless-stopped \
  --gpus all \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:gptoss \
  --model openai/gpt-oss-20b

echo "Container started. First run will download the model; check: sudo docker logs -f ominis-gptoss"
REMOTE

echo ""
echo "✓ gpt-oss Docker container running on $VLLM_HOST:8000"
echo "  Backend should have POWER_API_URL=http://$VLLM_HOST:8000 (run 20m-update-backend-env-power-gpt.sh if needed)"
echo ""
