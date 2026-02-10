#!/bin/bash
# Increase nginx proxy_read_timeout on the Haystack backend so long research streams
# (128K, 8K) don't get cut after 120s. Run once or after 17-deploy-haystack-backend.sh
# overwrites the config.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/haystack_backend.txt" 2>/dev/null || { echo "Missing config/haystack_backend.txt"; exit 1; }
KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
[ ! -f "$KEY_FILE" ] && echo "Missing $KEY_FILE" && exit 1
echo "Setting nginx proxy_read_timeout to 600s on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ubuntu@$BACKEND_IP" \
  "sudo sed -i 's/proxy_read_timeout 120s/proxy_read_timeout 600s/' /etc/nginx/sites-available/ominis-backend && sudo nginx -t && sudo systemctl reload nginx"
echo "Done. Long research streams (e.g. 128K) should no longer disconnect at 2 min."
echo ""
