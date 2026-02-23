#!/bin/bash
# Build Ominis-themed LibreChat image on chat.ominis.org EC2 and tag as librechat-ominis:latest.
# After this, set CHAT_IMAGE=librechat-ominis:latest in librechat-chat/.env and run 26-sync-chat-librechat.sh.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/../config/settings.sh" ] && source "$SCRIPT_DIR/../config/settings.sh"

if [ ! -f "$SCRIPT_DIR/../config/chat_server.txt" ]; then
    echo "Error: Run 25-deploy-chat-ec2.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/chat_server.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-chat-key.pem"
BUILD_DIR="$SCRIPT_DIR/librechat-ominis-build"
REMOTE_BUILD_DIR="/home/ubuntu/librechat-ominis-build"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

echo "Syncing build context to $CHAT_ELASTIC_IP..."
rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
    "$BUILD_DIR/" \
    "$SSH_USER@$CHAT_ELASTIC_IP:$REMOTE_BUILD_DIR/"

echo "Building image on server (this may take a few minutes)..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$CHAT_ELASTIC_IP" "bash -s" << 'REMOTECMD'
set -e
cd /home/ubuntu/librechat-ominis-build
sudo docker build -t librechat-ominis:latest .
echo "Image built: librechat-ominis:latest"
REMOTECMD

echo ""
echo "Next steps:"
echo "  1. In infrastructure/librechat-chat/.env add: CHAT_IMAGE=librechat-ominis:latest"
echo "  2. Run: ./infrastructure/26-sync-chat-librechat.sh"
echo ""
