#!/bin/bash
# Set nginx client_max_body_size to 50M on the Haystack backend so RAG file uploads
# (e.g. CSV up to ~50MB) are accepted. Default is 1M. Run once on existing backend.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/haystack_backend.txt" 2>/dev/null || { echo "Missing config/haystack_backend.txt"; exit 1; }
KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
[ ! -f "$KEY_FILE" ] && echo "Missing $KEY_FILE" && exit 1
echo "Setting nginx client_max_body_size to 50M on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ubuntu@$BACKEND_IP" \
  'CONF=/etc/nginx/sites-available/ominis-backend
   if grep -q "client_max_body_size" "$CONF"; then
     sudo sed -i "s/client_max_body_size .*/client_max_body_size 50M;/" "$CONF"
   else
     sudo sed -i "/server_name _;/a\    client_max_body_size 50M;" "$CONF"
   fi
   sudo nginx -t && sudo systemctl reload nginx'
echo "Done. RAG file uploads up to 50MB are now allowed."
