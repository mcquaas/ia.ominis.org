#!/bin/bash
# =============================================================================
# Deploy XMLA Proxy (.NET 8) on the Haystack Backend EC2
#
# Installs .NET 8 runtime, deploys the XMLA proxy C# app, and runs it as
# a systemd service on port 5001 (localhost only).
#
# This proxy enables the Python backend to query SINBA OLAP cubes
# (SQL Server Analysis Services) using ADOMD.NET via TCP.
#
# Prerequisites: Haystack backend EC2 must be deployed (17-deploy-haystack-backend.sh)
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# --- Load backend config ---
if [ ! -f "$SCRIPT_DIR/../config/haystack_backend.txt" ]; then
    echo "Error: Haystack backend not deployed. Run 17-deploy-haystack-backend.sh first."
    exit 1
fi
source "$SCRIPT_DIR/../config/haystack_backend.txt"

BACKEND_HOST="${BACKEND_IP}"
KEY_NAME="${AWS_KEY_NAME:-ominis-ollama-key}"
KEY_FILE="$SCRIPT_DIR/../config/${KEY_NAME}.pem"
SSH_USER="ubuntu"
PROXY_DIR="/opt/xmla-proxy"
LOCAL_PROXY_DIR="$SCRIPT_DIR/../xmla-proxy"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploying XMLA Proxy (.NET 8) for SINBA Cubes              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Backend Host:  $BACKEND_HOST"
echo "Proxy Port:    5001 (localhost only)"
echo "Proxy Dir:     $PROXY_DIR"
echo ""

# Check SSH key
if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

# Check that the proxy source exists
if [ ! -f "$LOCAL_PROXY_DIR/Program.cs" ]; then
    echo "Error: XMLA proxy source not found at $LOCAL_PROXY_DIR"
    exit 1
fi

# Wait for SSH
echo "Connecting to backend server..."
for i in {1..10}; do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$KEY_FILE" "$SSH_USER@$BACKEND_HOST" "echo ok" 2>/dev/null; then
        echo "  ✓ SSH connected"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "Error: Could not connect via SSH"
        exit 1
    fi
    echo "  Attempt $i/10..."
    sleep 5
done

# --- Step 1: Install .NET 8 SDK/Runtime ---
echo ""
echo "Step 1: Installing .NET 8 runtime..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_HOST" << 'INSTALL_DOTNET'
# Check if dotnet is already installed
if command -v dotnet &> /dev/null; then
    DOTNET_VER=$(dotnet --version 2>/dev/null || echo "unknown")
    echo "  .NET already installed: $DOTNET_VER"
else
    echo "  Installing .NET 8 SDK..."

    # Install Microsoft package repository
    wget -q https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb -O /tmp/packages-microsoft-prod.deb
    sudo dpkg -i /tmp/packages-microsoft-prod.deb
    rm /tmp/packages-microsoft-prod.deb

    # Install .NET 8 SDK
    sudo apt-get update -qq
    sudo apt-get install -y -qq dotnet-sdk-8.0

    echo "  ✓ .NET 8 installed: $(dotnet --version)"
fi
INSTALL_DOTNET

# --- Step 2: Sync proxy source code ---
echo ""
echo "Step 2: Syncing XMLA proxy source..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_HOST" "sudo mkdir -p $PROXY_DIR && sudo chown $SSH_USER:$SSH_USER $PROXY_DIR"

rsync -avz --progress \
    -e "ssh -o StrictHostKeyChecking=no -i $KEY_FILE" \
    "$LOCAL_PROXY_DIR/" \
    "$SSH_USER@$BACKEND_HOST:$PROXY_DIR/"

echo "  ✓ Source synced"

# --- Step 3: Build and configure the proxy ---
echo ""
echo "Step 3: Building XMLA proxy..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_HOST" << 'BUILD_PROXY'
cd /opt/xmla-proxy

# Restore NuGet packages and build
dotnet restore
dotnet publish -c Release -o /opt/xmla-proxy/publish --self-contained false

echo "  ✓ Build complete"

# Create systemd service
sudo tee /etc/systemd/system/xmla-proxy.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=XMLA Proxy for SINBA OLAP Cubes (.NET 8)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/xmla-proxy/publish
ExecStart=/usr/bin/dotnet /opt/xmla-proxy/publish/XmlaProxy.dll
Restart=always
RestartSec=10
Environment=DOTNET_ENVIRONMENT=Production
Environment=ASPNETCORE_URLS=http://127.0.0.1:5001

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable xmla-proxy
sudo systemctl restart xmla-proxy

# Wait a moment for the service to start
sleep 3

# Health check
if curl -s http://127.0.0.1:5001/health | grep -q "healthy"; then
    echo "  ✓ XMLA proxy is running and healthy"
else
    echo "  ⚠ XMLA proxy may not be running correctly"
    sudo systemctl status xmla-proxy --no-pager || true
fi
BUILD_PROXY

# --- Step 4: Update backend .env ---
echo ""
echo "Step 4: Configuring backend to use XMLA proxy..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_HOST" << 'UPDATE_ENV'
# Add SINBA_XMLA_URL to .env if not present
if ! grep -q "SINBA_XMLA_URL" /opt/ominis-backend/.env 2>/dev/null; then
    echo "" >> /opt/ominis-backend/.env
    echo "# SINBA OLAP Cubes - XMLA Proxy" >> /opt/ominis-backend/.env
    echo "SINBA_XMLA_URL=http://127.0.0.1:5001" >> /opt/ominis-backend/.env
    echo "  ✓ Added SINBA_XMLA_URL to backend .env"
else
    echo "  ✓ SINBA_XMLA_URL already configured"
fi

# Restart backend to pick up new config
sudo systemctl restart ominis-backend 2>/dev/null || true
UPDATE_ENV

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         XMLA Proxy Deployed Successfully!                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Proxy:    http://127.0.0.1:5001 (localhost only)"
echo "Health:   http://127.0.0.1:5001/health"
echo ""
echo "The SINBA cubes are now queryable via:"
echo "  Backend API:  POST http://$BACKEND_HOST/v1/sinba/query"
echo "  Frontend:     https://ia.ominis.org/sinba"
echo ""
echo "To check status:"
echo "  ssh -i $KEY_FILE $SSH_USER@$BACKEND_HOST"
echo "  sudo systemctl status xmla-proxy"
echo "  curl http://127.0.0.1:5001/health"
echo ""
echo "To view logs:"
echo "  ssh -i $KEY_FILE $SSH_USER@$BACKEND_HOST 'sudo journalctl -u xmla-proxy -f'"
echo ""
