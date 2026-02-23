#!/bin/bash
# Deploy Ominis Live Avatar to Pipecat Cloud (uses ominis-2.0-clinic)
#
# Prerequisites:
# 1. Pipecat Cloud account: https://pipecat.ai
# 2. Docker Hub account
# 3. Python 3.12 venv with pipecatcloud: cd liveavatar-demo && python3.12 -m venv .venv && . .venv/bin/activate && pip install pipecatcloud
#
# Usage:
#   1. cp liveavatar-demo/.env.pipecat.example liveavatar-demo/.env.pipecat
#   2. Edit .env.pipecat with HEYGEN_LIVE_AVATAR_API_KEY, DEEPGRAM_API_KEY, CARTESIA_API_KEY, OMINIS_BACKEND_URL
#   3. Replace YOUR_DOCKERHUB_USER in liveavatar-demo/pcc-deploy.toml
#   4. pcc auth login (in liveavatar-demo with venv active)
#   5. Run: ./infrastructure/23-deploy-liveavatar-pipecat.sh
#   6. Backend .env: PIPECAT_AGENT_NAME=ominis-live-avatar PIPECAT_API_TOKEN=xxx
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$SCRIPT_DIR/../liveavatar-demo"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploy Ominis Live Avatar to Pipecat Cloud                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ ! -f "$DEMO_DIR/Dockerfile" ]; then
    echo "Error: liveavatar-demo/Dockerfile not found"
    exit 1
fi

if grep -q "YOUR_DOCKERHUB_USER" "$DEMO_DIR/pcc-deploy.toml" 2>/dev/null; then
    echo "Error: Replace YOUR_DOCKERHUB_USER in liveavatar-demo/pcc-deploy.toml with your Docker Hub username"
    exit 1
fi

cd "$DEMO_DIR"

# Activate venv if exists
if [ -d ".venv" ]; then
    . .venv/bin/activate
fi

# Check pcc is available
if ! command -v pcc &>/dev/null; then
    echo "Error: pcc not found. Run: python3.12 -m venv .venv && . .venv/bin/activate && pip install pipecatcloud"
    exit 1
fi

# Optional: push secrets (if .env.pipecat exists)
if [ -f ".env.pipecat" ]; then
    echo "1. Pushing secrets to Pipecat Cloud..."
    pcc secrets set ominis-live-avatar-secrets --file .env.pipecat --skip || {
        echo "Warning: Could not push secrets. Run: pcc auth login"
    }
    echo ""
fi

echo "2. Building and pushing Docker image..."
pcc docker build-push || {
    echo "Failed. Ensure: pcc auth login, docker login"
    exit 1
}

echo ""
echo "3. Deploying to Pipecat Cloud..."
pcc deploy --force || {
    echo "Failed. Check pcc-deploy.toml (image, secret_set)"
    exit 1
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Agent deployed. Next: configure backend                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Add to backend .env (or run 20j script):"
echo "  PIPECAT_AGENT_NAME=ominis-live-avatar"
echo "  PIPECAT_API_TOKEN=<your Pipecat Cloud API token>"
echo ""
echo "Then sync backend: ./infrastructure/20-sync-backend.sh"
echo ""
