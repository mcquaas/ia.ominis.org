#!/bin/bash
# One-shot: push secrets + build+push Docker + deploy agent.
# Prereqs: Docker Hub account, docker login, pcc auth login (run once)
#
# Usage:
#   DOCKERHUB_USER=youruser ./infrastructure/23a-deploy-liveavatar-production.sh
#   # Or edit liveavatar-demo/pcc-deploy.toml image= before running
#
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$SCRIPT_DIR/../liveavatar-demo"
cd "$DEMO_DIR"
[ -d .venv ] && . .venv/bin/activate

if [ -n "$DOCKERHUB_USER" ]; then
  echo "Using Docker Hub user: $DOCKERHUB_USER"
  sed -i.bak "s|image = \"docker.io/[^/]*/|image = \"docker.io/$DOCKERHUB_USER/|" pcc-deploy.toml
fi

echo "1. Pushing secrets to Pipecat Cloud..."
pcc secrets set ominis-live-avatar-secrets --file .env.pipecat --skip

echo ""
echo "2. Building and pushing Docker image..."
echo "Y" | pcc docker build-push

echo ""
echo "3. Deploying agent to Pipecat Cloud..."
pcc deploy --force

echo ""
echo "Done. Backend already has PIPECAT_AGENT_NAME + PIPECAT_API_TOKEN."
echo "Test: https://ia.ominis.org/live"
