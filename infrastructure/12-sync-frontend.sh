#!/bin/bash
# Sync frontend code to EC2 and build/restart the application
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

# Load frontend server config
if [ ! -f "$SCRIPT_DIR/../config/frontend_server.txt" ]; then
    echo "Error: Frontend server not deployed. Run 11-deploy-frontend-ec2.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/frontend_server.txt"

# Load RAG API URL
if [ -f "$SCRIPT_DIR/../config/ollama_server.txt" ]; then
    source "$SCRIPT_DIR/../config/ollama_server.txt"
    API_URL="${RAG_API_URL:-https://api.ominis.org/query}"
else
    API_URL="https://api.ominis.org/query"
fi

# Backend URL for server-side API routes (query-stream, research, etc.)
if [ -f "$SCRIPT_DIR/../config/haystack_backend.txt" ]; then
    source "$SCRIPT_DIR/../config/haystack_backend.txt"
    BACKEND_URL="${BACKEND_URL:-https://api.ominis.org}"
else
    BACKEND_URL="${BACKEND_URL:-https://api.ominis.org}"
fi

KEY_FILE="$SCRIPT_DIR/../config/ominis-frontend-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-frontend"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Syncing Frontend to EC2 Server                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Server:      $FRONTEND_ELASTIC_IP"
echo "Domain:      $FRONTEND_DOMAIN"
echo "API URL:     $API_URL"
echo ""

# Check if key file exists
if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

# Wait for SSH to be available
echo "Waiting for SSH to be available..."
for i in {1..30}; do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$KEY_FILE" "$SSH_USER@$FRONTEND_ELASTIC_IP" "echo ok" 2>/dev/null; then
        echo "  ✓ SSH is available"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: Could not connect via SSH after 30 attempts"
        exit 1
    fi
    echo "  Attempt $i/30..."
    sleep 10
done

# Backend API URL (Haystack)
API_BACKEND_URL="${API_BACKEND_URL:-https://api.ominis.org}"

# Optional: All.Can Strapi token for /api/allcan-directory/* (copy config/allcan_strapi.example.txt → config/allcan_strapi.txt)
if [ -f "$SCRIPT_DIR/../config/allcan_strapi.txt" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/../config/allcan_strapi.txt"
  set +a
fi
ALLCAN_STRAPI_URL="${ALLCAN_STRAPI_URL:-https://api.allcan.mx}"

# Create .env.local with correct API endpoint
echo ""
echo "Creating environment configuration..."
cat << EOF > "$FRONTEND_DIR/.env.local"
NEXT_PUBLIC_API_ENDPOINT=$API_URL
NEXT_PUBLIC_API_URL=$API_BACKEND_URL

# Backend base URL for server-side API routes
BACKEND_URL=$BACKEND_URL

# All.Can México map directory (Strapi REST)
ALLCAN_STRAPI_URL=$ALLCAN_STRAPI_URL
ALLCAN_STRAPI_API_TOKEN=$ALLCAN_STRAPI_API_TOKEN
EOF
echo "  ✓ .env.local created with API_ENDPOINT=$API_URL"
echo "  ✓ .env.local created with NEXT_PUBLIC_API_URL=$API_BACKEND_URL"
echo "  ✓ .env.local created with BACKEND_URL=$BACKEND_URL"

# Build the frontend locally first
echo ""
echo "Building frontend locally..."
cd "$FRONTEND_DIR"
npm run build
echo "  ✓ Build complete"

# Sync frontend files to server (excluding dev files)
echo ""
echo "Syncing files to server..."
rsync -avz --progress \
    --exclude 'node_modules' \
    --exclude '.git' \
    --exclude '.next/cache' \
    -e "ssh -o StrictHostKeyChecking=no -i \"$KEY_FILE\"" \
    "$FRONTEND_DIR/" \
    "$SSH_USER@$FRONTEND_ELASTIC_IP:$REMOTE_DIR/"

echo "  ✓ Files synced"

# Install dependencies and start the app on remote server
echo ""
echo "Installing dependencies and starting application..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$FRONTEND_ELASTIC_IP" << 'REMOTECMD'
cd /opt/ominis-frontend

echo "Installing dependencies..."
npm install --production

echo "Setting up PM2..."
pm2 delete ominis-frontend 2>/dev/null || true
pm2 start npm --name ominis-frontend -- start
pm2 save
pm2 startup systemd -u ubuntu --hp /home/ubuntu 2>/dev/null || true

echo "Nginx long timeouts for SSE (default 60s kills query-stream before backend responds)..."
NGINX_SITE="/etc/nginx/sites-available/ominis-frontend"
if [ -f "$NGINX_SITE" ] && ! grep -q proxy_read_timeout "$NGINX_SITE" 2>/dev/null; then
  sudo python3 << 'PY'
import pathlib
p = pathlib.Path("/etc/nginx/sites-available/ominis-frontend")
t = p.read_text()
if "proxy_read_timeout" in t:
    raise SystemExit(0)
lines = t.splitlines()
out = []
for line in lines:
    out.append(line)
    if line.strip() == "location / {":
        out.append("        proxy_read_timeout 900s;")
        out.append("        proxy_send_timeout 900s;")
p.write_text("\n".join(out) + "\n")
PY
fi

echo "Reloading Nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo "Application status:"
pm2 status
REMOTECMD

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Frontend Deployed Successfully!                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Frontend URL: http://$FRONTEND_ELASTIC_IP"
echo "Domain:       https://$FRONTEND_DOMAIN (after DNS + SSL)"
echo ""
echo "To enable SSL (after DNS is configured):"
echo "  ssh -i $KEY_FILE $SSH_USER@$FRONTEND_ELASTIC_IP"
echo "  sudo certbot --nginx -d $FRONTEND_DOMAIN"
echo ""
echo "To view logs:"
echo "  ssh -i $KEY_FILE $SSH_USER@$FRONTEND_ELASTIC_IP 'pm2 logs ominis-frontend'"
echo ""
