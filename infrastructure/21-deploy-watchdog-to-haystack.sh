#!/bin/bash
# =============================================================================
# Deploy OMINIS Status Watchdog to Haystack Backend Server
# =============================================================================
# Run from project root. Deploys watchdog to 78.12.33.205 (Haystack).
# Requires: SSH access via ominis-api or ssh config for Haystack server.
#
# After running: https://api.ominis.org/status will serve the status page.
# =============================================================================

set -e

HAYSTACK_IP="${HAYSTACK_IP:-78.12.33.205}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

# Key: Haystack was deployed with ominis-ollama-key (same as legacy Mexico servers)
KEY_FILE="${KEY_FILE:-$CONFIG_DIR/ominis-ollama-key.pem}"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15"
[ -f "$KEY_FILE" ] && SSH_OPTS="$SSH_OPTS -i $KEY_FILE"

HAYSTACK_HOST="ubuntu@${HAYSTACK_IP}"

echo "=== Deploying Watchdog to Haystack Server ==="
echo "Target: $HAYSTACK_IP"
echo ""

# 1. Create directory on server
echo "Step 1: Creating /opt/ominis-watchdog on server..."
ssh $SSH_OPTS "$HAYSTACK_HOST" "sudo mkdir -p /opt/ominis-watchdog /var/www/status && sudo chown ubuntu:ubuntu /opt/ominis-watchdog /var/www/status"

# 2. Copy watchdog script
echo "Step 2: Copying status_watchdog.py..."
scp $SSH_OPTS "$SCRIPT_DIR/status_watchdog.py" "$HAYSTACK_HOST:/opt/ominis-watchdog/status_watchdog.py"
ssh $SSH_OPTS "$HAYSTACK_HOST" "chmod +x /opt/ominis-watchdog/status_watchdog.py"

# 3. Create systemd service
echo "Step 3: Installing systemd service..."
ssh $SSH_OPTS "$HAYSTACK_HOST" 'sudo tee /etc/systemd/system/ominis-watchdog.service << '\''SVC'\''
[Unit]
Description=OMINIS Status Watchdog
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/ominis-watchdog/status_watchdog.py
WorkingDirectory=/opt/ominis-watchdog
User=ubuntu

[Install]
WantedBy=multi-user.target
SVC'

# 4. Create systemd timer
echo "Step 4: Installing systemd timer..."
ssh $SSH_OPTS "$HAYSTACK_HOST" 'sudo tee /etc/systemd/system/ominis-watchdog.timer << '\''TMR'\''
[Unit]
Description=Run OMINIS Watchdog every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
TMR'

# 5. Enable and start timer
echo "Step 5: Enabling watchdog timer..."
ssh $SSH_OPTS "$HAYSTACK_HOST" "sudo systemctl daemon-reload && sudo systemctl enable ominis-watchdog.timer && sudo systemctl start ominis-watchdog.timer"

# 6. Run once immediately (may exit 1 if critical services down - that's OK)
echo "Step 6: Running watchdog once..."
ssh $SSH_OPTS "$HAYSTACK_HOST" "sudo systemctl start ominis-watchdog.service" || true

# 7. Add Nginx location for /status
echo "Step 7: Configuring Nginx for /status..."

# Create status snippet and add to main config
ssh $SSH_OPTS "$HAYSTACK_HOST" 'bash -s' << 'NGINXREMOTE'
sudo mkdir -p /etc/nginx/snippets
sudo tee /etc/nginx/snippets/ominis-status.conf << 'SNIP'
location = /status {
    return 301 /status/;
}
location /status/ {
    alias /var/www/status/;
    index index.html;
    default_type text/html;
}
location = /status/status.json {
    alias /var/www/status/status.json;
    default_type application/json;
}
SNIP

# Find config that proxies to port 8000
CONF_FILE=""
for f in /etc/nginx/sites-enabled/*; do
  [ -f "$f" ] || continue
  if grep -q "proxy_pass.*8000" "$f" 2>/dev/null; then
    CONF_FILE="$f"
    break
  fi
done
[ -z "$CONF_FILE" ] && for f in /etc/nginx/conf.d/*.conf; do
  [ -f "$f" ] || continue
  if grep -q "proxy_pass.*8000" "$f" 2>/dev/null; then
    CONF_FILE="$f"
    break
  fi
done

if [ -n "$CONF_FILE" ] && ! sudo grep -q "ominis-status" "$CONF_FILE" 2>/dev/null; then
  # Insert include before first location block
  sudo sed -i '/server {/a\
    include /etc/nginx/snippets/ominis-status.conf;
' "$CONF_FILE"
  echo "Added status include to $CONF_FILE"
fi

sudo nginx -t && sudo systemctl reload nginx && echo "Nginx reloaded OK"
NGINXREMOTE

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Status page: https://api.ominis.org/status/"
echo "JSON API:    https://api.ominis.org/status/status.json"
echo ""
echo "Verify: curl -s https://api.ominis.org/status/ | head -20"
echo ""
echo "Next: Decommission legacy server 78.13.254.66 (see infrastructure/22-decommission-legacy-rag.sh)"
