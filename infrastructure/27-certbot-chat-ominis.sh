#!/bin/bash
# Install Let's Encrypt certificate for chat.ominis.org (run after DNS A record points to chat server IP)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ ! -f "$SCRIPT_DIR/../config/chat_server.txt" ] && echo "Error: config/chat_server.txt not found." && exit 1
source "$SCRIPT_DIR/../config/chat_server.txt"

KEY_FILE="$SCRIPT_DIR/../config/ominis-chat-key.pem"
[ ! -f "$KEY_FILE" ] && echo "Error: $KEY_FILE not found." && exit 1

echo "Checking DNS: chat.ominis.org -> $CHAT_ELASTIC_IP"
RESOLVED=$(dig +short chat.ominis.org A 2>/dev/null | head -1)
if [ "$RESOLVED" != "$CHAT_ELASTIC_IP" ]; then
    echo "Warning: DNS resolves to $RESOLVED (expected $CHAT_ELASTIC_IP)."
    echo "Update the A record to $CHAT_ELASTIC_IP and wait for propagation, then run this script again."
    read -p "Continue anyway? [y/N] " -n 1 -r; echo
    [[ ! $REPLY =~ ^[yY]$ ]] && exit 1
fi

echo "Installing certificate on $CHAT_ELASTIC_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" ubuntu@$CHAT_ELASTIC_IP \
    "sudo certbot --nginx -d chat.ominis.org --non-interactive --agree-tos --register-unsafely-without-email"

echo ""
echo "Done. HTTPS: https://chat.ominis.org"
echo "Renewal: certbot renew is in cron.daily on the server."
