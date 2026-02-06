#!/bin/bash
# Setup Nginx reverse proxy and Let's Encrypt SSL for Strapi
# Run this on the server where Strapi will be hosted

set -e

DOMAIN="admin.ominis.org"
STRAPI_PORT=1337
EMAIL="${LETSENCRYPT_EMAIL:-admin@ominis.org}"

echo "==========================================="
echo "  Nginx + SSL Setup for $DOMAIN"
echo "==========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo: sudo $0"
  exit 1
fi

# Detect package manager
if command -v apt-get &> /dev/null; then
  PKG_MANAGER="apt"
elif command -v yum &> /dev/null; then
  PKG_MANAGER="yum"
elif command -v dnf &> /dev/null; then
  PKG_MANAGER="dnf"
else
  echo "Unsupported package manager"
  exit 1
fi

echo "1. Installing Nginx and Certbot..."
if [ "$PKG_MANAGER" = "apt" ]; then
  apt-get update
  apt-get install -y nginx certbot python3-certbot-nginx
elif [ "$PKG_MANAGER" = "yum" ] || [ "$PKG_MANAGER" = "dnf" ]; then
  $PKG_MANAGER install -y nginx certbot python3-certbot-nginx
  systemctl enable nginx
fi

echo ""
echo "2. Creating Nginx configuration..."

# Create nginx config (HTTP only first, certbot will add SSL)
cat > /etc/nginx/sites-available/$DOMAIN.conf << 'NGINXEOF'
# Nginx configuration for admin.ominis.org (Strapi)

server {
    listen 80;
    server_name admin.ominis.org;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Strapi backend
    location / {
        proxy_pass http://127.0.0.1:1337;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # Strapi uploads
    location /uploads {
        proxy_pass http://127.0.0.1:1337/uploads;
        proxy_set_header Host $host;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
NGINXEOF

# Create sites-available and sites-enabled if they don't exist (Amazon Linux)
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

# Check if nginx.conf includes sites-enabled
if ! grep -q "sites-enabled" /etc/nginx/nginx.conf; then
  echo "Adding sites-enabled include to nginx.conf..."
  sed -i '/http {/a \    include /etc/nginx/sites-enabled/*.conf;' /etc/nginx/nginx.conf
fi

# Enable the site
ln -sf /etc/nginx/sites-available/$DOMAIN.conf /etc/nginx/sites-enabled/

echo ""
echo "3. Testing Nginx configuration..."
nginx -t

echo ""
echo "4. Starting/Reloading Nginx..."
systemctl start nginx 2>/dev/null || systemctl reload nginx

echo ""
echo "5. Obtaining SSL certificate from Let's Encrypt..."
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email $EMAIL --redirect

echo ""
echo "6. Setting up auto-renewal..."
# Certbot auto-renewal is typically set up automatically, but let's ensure
if [ -f /etc/cron.d/certbot ]; then
  echo "Auto-renewal cron already exists"
else
  echo "0 12 * * * root certbot renew --quiet" > /etc/cron.d/certbot
  echo "Created auto-renewal cron job"
fi

echo ""
echo "7. Final Nginx reload..."
systemctl reload nginx

echo ""
echo "==========================================="
echo "  Setup Complete!"
echo "==========================================="
echo ""
echo "Nginx is configured to proxy:"
echo "  https://$DOMAIN → http://127.0.0.1:$STRAPI_PORT"
echo ""
echo "SSL certificate installed and auto-renewal enabled."
echo ""
echo "Next steps:"
echo "  1. Make sure Strapi is running on port $STRAPI_PORT"
echo "  2. Access admin panel: https://$DOMAIN/admin"
echo ""
