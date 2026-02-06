#!/bin/bash
# Deploy Strapi Backend to Ominis Server
set -e

SERVER_IP="78.13.254.66"
SERVER_USER="ec2-user"
SSH_KEY="${SSH_KEY:-~/.ssh/ominis-key.pem}"
REMOTE_DIR="/opt/ominis-admin"
LOCAL_BACKEND="$(dirname "$0")/../backend"

echo "==========================================="
echo "  Deploying Strapi to $SERVER_IP"
echo "==========================================="

# Check SSH key
if [ ! -f "$SSH_KEY" ]; then
  echo "SSH key not found at $SSH_KEY"
  echo "Set SSH_KEY environment variable or place key at ~/.ssh/ominis-key.pem"
  exit 1
fi

echo ""
echo "1. Syncing backend code to server..."
rsync -avz --exclude 'node_modules' --exclude '.tmp' --exclude '.cache' --exclude '.env' \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  "$LOCAL_BACKEND/" "$SERVER_USER@$SERVER_IP:$REMOTE_DIR/"

echo ""
echo "2. Setting up server..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'REMOTE_SCRIPT'
set -e

REMOTE_DIR="/opt/ominis-admin"
cd $REMOTE_DIR

echo "Installing Node.js 22 if needed..."
if ! command -v node &> /dev/null || [[ $(node -v) != v22* ]]; then
  curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
  sudo yum install -y nodejs
fi

echo "Node version: $(node -v)"
echo "NPM version: $(npm -v)"

echo "Installing dependencies..."
npm install --production

echo "Creating .env if not exists..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  IMPORTANT: Edit .env with production secrets!"
  echo "   Run: node scripts/generate-secrets.js"
  echo "   Then update /opt/ominis-admin/.env"
fi

echo "Building Strapi..."
npm run build

echo "Setting up PM2..."
if ! command -v pm2 &> /dev/null; then
  sudo npm install -g pm2
fi

# Stop existing if running
pm2 delete strapi 2>/dev/null || true

# Start Strapi with PM2
pm2 start npm --name strapi -- run start
pm2 save

# Setup PM2 startup
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u ec2-user --hp /home/ec2-user

echo ""
echo "Strapi is running on port 1337"
pm2 status
REMOTE_SCRIPT

echo ""
echo "3. Setting up Nginx and SSL..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'NGINX_SCRIPT'
set -e

# Install nginx and certbot if needed
if ! command -v nginx &> /dev/null; then
  sudo yum install -y nginx
  sudo systemctl enable nginx
fi

if ! command -v certbot &> /dev/null; then
  sudo yum install -y certbot python3-certbot-nginx
fi

# Create nginx config for api.ominis.org
sudo tee /etc/nginx/conf.d/api.ominis.org.conf > /dev/null << 'NGINXCONF'
server {
    listen 80;
    server_name api.ominis.org admin.ominis.org;

    # Strapi backend at /v1
    location /v1/ {
        rewrite ^/v1/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:1337;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # RAG/Agent API at root
    location /query {
        proxy_pass http://127.0.0.1:8000/query;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # Admin panel redirect (optional, for backwards compatibility)
    location /admin {
        rewrite ^/admin(.*)$ /v1/admin$1 redirect;
    }

    # Default - could serve health check or redirect
    location / {
        return 200 '{"status":"ok","service":"ominis-api"}';
        add_header Content-Type application/json;
    }
}
NGINXCONF

# Remove old config if exists
sudo rm -f /etc/nginx/conf.d/admin.ominis.org.conf 2>/dev/null

sudo nginx -t
sudo systemctl start nginx 2>/dev/null || sudo systemctl reload nginx

echo ""
echo "Getting SSL certificate..."
sudo certbot --nginx -d api.ominis.org -d admin.ominis.org --non-interactive --agree-tos --email admin@ominis.org --redirect || echo "SSL setup may need manual intervention"

sudo systemctl reload nginx
NGINX_SCRIPT

echo ""
echo "==========================================="
echo "  Deployment Complete!"
echo "==========================================="
echo ""
echo "API Endpoints:"
echo "  Strapi API:   https://api.ominis.org/v1/api"
echo "  Admin Panel:  https://api.ominis.org/v1/admin"
echo "  RAG Query:    https://api.ominis.org/query"
echo ""
echo "Next steps:"
echo "  1. SSH to server: ssh -i $SSH_KEY $SERVER_USER@$SERVER_IP"
echo "  2. Generate new secrets: cd $REMOTE_DIR && node scripts/generate-secrets.js"
echo "  3. Update .env: nano $REMOTE_DIR/.env"
echo "  4. Restart Strapi: pm2 restart strapi"
echo "  5. Create first admin at https://api.ominis.org/v1/admin"
echo ""
