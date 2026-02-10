#!/bin/bash
# =============================================================================
# Update Haystack backend .env with OpenScholar 128K instance ID and API URL.
# Run after 15-deploy-openscholar-128k.sh so the dashboard switch can start/stop
# the 128K EC2 instance.
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/openscholar_128k_server.txt" ]; then
    echo "Error: Run 15-deploy-openscholar-128k.sh first to create config/openscholar_128k_server.txt"
    exit 1
fi
source "$CONFIG_DIR/openscholar_128k_server.txt"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
    echo "Error: Backend not deployed. Run 17-deploy-haystack-backend.sh first."
    exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Update Backend .env with OpenScholar 128K config          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Backend:  $BACKEND_IP"
echo "Instance: $OPENSCHOLAR_128K_INSTANCE_ID"
echo "API URL:  $OPENSCHOLAR_128K_API_URL"
echo ""

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
# Strip existing 128K / AWS_REGION_GPU lines (avoid duplicate on re-runs)
if [ -f .env ]; then
  grep -v '^OPENSCHOLAR_128K_' .env | grep -v '^AWS_REGION_GPU=' | grep -v '^# OpenScholar 128K' > .env.tmp
  sudo mv .env.tmp .env
  sudo chown ubuntu:ubuntu .env
fi
# Append with sudo so it works even if .env is root-owned
echo "" | sudo tee -a .env > /dev/null
echo "# OpenScholar 128K (dashboard start/stop) - 20a" | sudo tee -a .env > /dev/null
echo "OPENSCHOLAR_128K_INSTANCE_ID=$OPENSCHOLAR_128K_INSTANCE_ID" | sudo tee -a .env > /dev/null
echo "OPENSCHOLAR_128K_API_URL=$OPENSCHOLAR_128K_API_URL" | sudo tee -a .env > /dev/null
echo "AWS_REGION_GPU=us-east-1" | sudo tee -a .env > /dev/null
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo ""
echo "✓ Backend .env updated and service restarted."
echo "  Dashboard switch for 128K will work (start/stop instance $OPENSCHOLAR_128K_INSTANCE_ID)."
echo ""
echo "If the dashboard still shows 'no configurado' or 'error AWS': the backend needs"
echo "EC2 permissions in us-east-1. Add to backend .env (or use an IAM role with EC2 access):"
echo "  AWS_ACCESS_KEY_ID=..."
echo "  AWS_SECRET_ACCESS_KEY=..."
echo ""
