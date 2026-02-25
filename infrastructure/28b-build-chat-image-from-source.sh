#!/bin/bash
# Build Ominis LibreChat image FROM SOURCE (frontend-librechat).
# Syncs frontend-librechat + overrides to chat server and runs Docker build there.
# Result: librechat-ominis:latest with your compiled client (not just CSS overrides).
#
# Prereqs: frontend-librechat submodule init'd (git submodule update --init --recursive).
# After this, set CHAT_IMAGE=librechat-ominis:latest in librechat-chat/.env and run 26-sync-chat-librechat.sh.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
[ -f "$SCRIPT_DIR/../config/settings.sh" ] && source "$SCRIPT_DIR/../config/settings.sh"

if [ ! -f "$SCRIPT_DIR/../config/chat_server.txt" ]; then
    echo "Error: Run 25-deploy-chat-ec2.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/chat_server.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-chat-key.pem"
REMOTE_BUILD_DIR="/home/ubuntu/ominis-chat-build"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

if [ ! -d "$REPO_ROOT/frontend-librechat/client" ]; then
    echo "Error: frontend-librechat not found. Run: git submodule update --init --recursive"
    exit 1
fi

echo "Syncing frontend-librechat and build context to $CHAT_ELASTIC_IP (this may take a few minutes)..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$CHAT_ELASTIC_IP" "mkdir -p $REMOTE_BUILD_DIR/frontend-librechat $REMOTE_BUILD_DIR/infrastructure/librechat-ominis-build"

rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
    "$REPO_ROOT/frontend-librechat/" \
    "$SSH_USER@$CHAT_ELASTIC_IP:$REMOTE_BUILD_DIR/frontend-librechat/"

rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
    "$SCRIPT_DIR/librechat-ominis-build/" \
    "$SSH_USER@$CHAT_ELASTIC_IP:$REMOTE_BUILD_DIR/infrastructure/librechat-ominis-build/"

echo "Building image on server (npm run frontend + overlay; may take 10–15 min)..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$CHAT_ELASTIC_IP" "cd $REMOTE_BUILD_DIR && sudo docker build -f infrastructure/librechat-ominis-build/Dockerfile.from-source -t librechat-ominis:latest ."
echo "Image built on server: librechat-ominis:latest"

echo ""
echo "Next steps:"
echo "  1. In infrastructure/librechat-chat/.env set: CHAT_IMAGE=librechat-ominis:latest"
echo "  2. Run: ./infrastructure/26-sync-chat-librechat.sh"
echo ""
