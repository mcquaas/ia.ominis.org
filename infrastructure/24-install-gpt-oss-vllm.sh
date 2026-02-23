#!/bin/bash
# Instala vLLM + gpt-oss en un servidor con GPU (g5.2xlarge o similar) y deja el servicio escuchando en :8000.
# Uso: VLLM_HOST=44.217.115.195 KEY_FILE=config/ominis-falcon-gpu-key.pem ./infrastructure/24-install-gpt-oss-vllm.sh
# Requiere: EC2 con GPU (≥16 GB VRAM para 20B), Ubuntu, y la key SSH del host.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

# Host donde instalar vLLM (IP o hostname). Debe ser accesible por SSH y por el backend (78.12.33.205).
VLLM_HOST="${VLLM_HOST:-}"
# Key SSH para ese host (p. ej. la del g5 si es tu instancia Power)
KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-falcon-gpu-key.pem}"
SSH_USER="${SSH_USER:-ubuntu}"

if [ -z "$VLLM_HOST" ]; then
  echo "Uso: VLLM_HOST=<ip-o-hostname> [KEY_FILE=path/to/key.pem] $0"
  echo "Ejemplo: VLLM_HOST=44.217.115.195 KEY_FILE=$CONFIG_DIR/ominis-falcon-gpu-key.pem $0"
  echo ""
  echo "Opcional: crea config/power_vllm_install.txt con:"
  echo "  VLLM_HOST=44.217.115.195"
  echo "  KEY_FILE=$CONFIG_DIR/ominis-falcon-gpu-key.pem"
  exit 1
fi

[ ! -f "$KEY_FILE" ] && echo "Error: KEY_FILE no encontrado: $KEY_FILE" && exit 1

echo "Instalando vLLM + gpt-oss-20b en $VLLM_HOST (usuario $SSH_USER)..."
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$VLLM_HOST" << 'REMOTE'
set -e
export DEBIAN_FRONTEND=noninteractive

# Python 3.12 y venv
if ! command -v python3.12 &>/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update -qq
  sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
fi

sudo mkdir -p /opt/ominis-vllm
sudo chown ubuntu:ubuntu /opt/ominis-vllm
cd /opt/ominis-vllm

# Install uv (recommended by vLLM/OpenAI for gpt-oss)
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
export PATH="$HOME/.local/bin:$PATH"

if [ ! -d "venv" ]; then
  uv venv --python 3.12 --seed
fi
source venv/bin/activate

# vLLM 0.10.2 supports gpt-oss on Ampere (A10G); see https://docs.vllm.ai/projects/recipes/en/latest/OpenAI/GPT-OSS.html
uv pip install "vllm==0.10.2" --torch-backend=auto

# Servicio systemd para que quede corriendo
sudo tee /etc/systemd/system/ominis-vllm-gptoss.service > /dev/null << 'SVC'
[Unit]
Description=Ominis vLLM gpt-oss (OpenAI compatible)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ominis-vllm
Environment="PATH=/opt/ominis-vllm/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/ominis-vllm/venv/bin/vllm serve openai/gpt-oss-20b --host 0.0.0.0 --async-scheduling
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
SVC

sudo systemctl daemon-reload
sudo systemctl enable ominis-vllm-gptoss
sudo systemctl restart ominis-vllm-gptoss
sleep 5
sudo systemctl status ominis-vllm-gptoss --no-pager || true
REMOTE

echo ""
echo "✓ vLLM + gpt-oss-20b instalado y servicio activo en $VLLM_HOST:8000"
echo "  Asegúrate de que el backend tenga POWER_API_URL=http://$VLLM_HOST:8000"
echo "  (Puedes usar: ./infrastructure/20m-update-backend-env-power-gpt.sh con POWER_API_URL en config/power_gpt_server.txt)"
echo ""
