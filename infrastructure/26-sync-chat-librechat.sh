#!/bin/bash
# Sync LibreChat config to chat.ominis.org EC2 and (re)start containers
# Requires: config/chat_server.txt, config/ominis-chat-key.pem, .env in librechat-chat/
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

if [ ! -f "$SCRIPT_DIR/../config/chat_server.txt" ]; then
    echo "Error: Run 25-deploy-chat-ec2.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/chat_server.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-chat-key.pem"
LIBRECHAT_DIR="$SCRIPT_DIR/librechat-chat"
REMOTE_DIR="/opt/librechat-ominis"
SSH_USER="ubuntu"

if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

if [ ! -f "$LIBRECHAT_DIR/.env" ]; then
    echo "Error: Create $LIBRECHAT_DIR/.env from .env.example and set CREDS_KEY, CREDS_IV"
    echo "Generate keys at: https://librechat.ai/toolkit/creds_generator"
    exit 1
fi

echo "Syncing LibreChat config to $CHAT_ELASTIC_IP..."
rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
    "$LIBRECHAT_DIR/" \
    "$SSH_USER@$CHAT_ELASTIC_IP:$REMOTE_DIR/"

echo "Starting LibreChat and Nginx on server..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$CHAT_ELASTIC_IP" "bash -s" "$CHAT_DOMAIN" << 'REMOTECMD'
CHAT_DOMAIN=$1
cd /opt/librechat-ominis
# Use custom Ominis image if it exists on server (built by 28-build-chat-image.sh)
if sudo docker image inspect librechat-ominis:latest >/dev/null 2>&1; then
  grep -q 'CHAT_IMAGE=librechat-ominis' .env 2>/dev/null || echo 'CHAT_IMAGE=librechat-ominis:latest' >> .env
fi
sudo docker compose down 2>/dev/null || true
# Skip pull when using custom Ominis image
if ! grep -q 'CHAT_IMAGE=librechat-ominis' .env 2>/dev/null; then
  sudo docker compose pull
fi
sudo docker compose up -d

# Nginx vhost: only overwrite if SSL not already configured (certbot adds 443)
if ! sudo grep -q 'ssl_certificate' /etc/nginx/sites-available/chat-ominis 2>/dev/null; then
  sudo tee /etc/nginx/sites-available/chat-ominis << NGINX
server {
    listen 80;
    server_name CHAT_DOMAIN_PLACEHOLDER;
    location / {
        proxy_pass http://127.0.0.1:3080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
NGINX
  sudo sed -i "s/CHAT_DOMAIN_PLACEHOLDER/$CHAT_DOMAIN/g" /etc/nginx/sites-available/chat-ominis
fi
sudo ln -sf /etc/nginx/sites-available/chat-ominis /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo "Containers:"
sudo docker compose ps
REMOTECMD

echo ""
echo "LibreChat is running at http://$CHAT_ELASTIC_IP:3080"
echo "Configure Nginx and SSL:"
echo "  ssh -i $KEY_FILE $SSH_USER@$CHAT_ELASTIC_IP"
echo "  sudo certbot --nginx -d $CHAT_DOMAIN"
echo ""
echo "Ensure backend (api.ominis.org) ALLOWED_ORIGINS includes https://$CHAT_DOMAIN"
