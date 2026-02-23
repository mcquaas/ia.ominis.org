#!/bin/bash
# Add CORS headers in Nginx for the Haystack backend so uploads from ia.ominis.org
# (and la, ai, ominis.org, localhost) are not blocked by the browser.
# Run once on existing backend. Uses same config as 17-deploy-haystack-backend.sh.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/haystack_backend.txt" 2>/dev/null || { echo "Missing config/haystack_backend.txt"; exit 1; }
KEY_FILE="$SCRIPT_DIR/../config/ominis-ollama-key.pem"
[ ! -f "$KEY_FILE" ] && echo "Missing $KEY_FILE" && exit 1

echo "Applying CORS headers in Nginx on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ubuntu@$BACKEND_IP" 'sudo tee /etc/nginx/sites-available/ominis-backend > /dev/null << "NGINXEOF"
map $http_origin $cors_origin {
    default "";
    "~^https://(ia|la|ai)\.ominis\.org$" $http_origin;
    "https://ominis.org" $http_origin;
    "http://localhost:3000" $http_origin;
}
server {
    listen 80;
    server_name _;
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_hide_header Access-Control-Allow-Origin;
        proxy_hide_header Access-Control-Allow-Credentials;
        proxy_hide_header Access-Control-Allow-Methods;
        proxy_hide_header Access-Control-Allow-Headers;
        if ($cors_origin != "") {
            add_header Access-Control-Allow-Origin $cors_origin always;
            add_header Access-Control-Allow-Credentials "true" always;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
            add_header Access-Control-Allow-Headers "DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization" always;
        }

        proxy_buffering off;
        proxy_cache off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        chunked_transfer_encoding off;
        proxy_read_timeout 600s;
    }
}
NGINXEOF
sudo nginx -t && sudo systemctl reload nginx'
echo "Done. CORS from ia.ominis.org / la / ai / ominis.org / localhost should work now."
