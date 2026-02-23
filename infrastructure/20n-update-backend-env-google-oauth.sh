#!/bin/bash
# Inject GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET into backend .env for "Continuar con Google".
# Usage: GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... ./infrastructure/20n-update-backend-env-google-oauth.sh
# Optional: BACKEND_PUBLIC_URL=https://api.ominis.org (for OAuth redirect_uri behind proxy)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

if [ -z "$GOOGLE_CLIENT_ID" ] || [ -z "$GOOGLE_CLIENT_SECRET" ]; then
    echo "Usage: GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... $0"
    echo "Optional: BACKEND_PUBLIC_URL=https://api.ominis.org"
    exit 1
fi

echo "Updating Google OAuth config on backend $BACKEND_IP..."
ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << REMOTECMD
set -e
cd $REMOTE_DIR
if [ ! -f .env ]; then
  echo "No .env found. Run 20-sync-backend.sh first."
  exit 1
fi
grep -v '^GOOGLE_CLIENT_ID=' .env | grep -v '^GOOGLE_CLIENT_SECRET=' | grep -v '^BACKEND_PUBLIC_URL=' | grep -v '^# Google OAuth' > .env.tmp || true
echo "# Google OAuth - 20n" >> .env.tmp
echo "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" >> .env.tmp
echo "GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET" >> .env.tmp
mv .env.tmp .env
REMOTECMD

# Inject BACKEND_PUBLIC_URL if provided (use separate SSH so we don't pass empty in heredoc)
if [ -n "$BACKEND_PUBLIC_URL" ]; then
  ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" "cd $REMOTE_DIR && grep -v '^BACKEND_PUBLIC_URL=' .env > .env.tmp 2>/dev/null || cp .env .env.tmp; echo 'BACKEND_PUBLIC_URL=$BACKEND_PUBLIC_URL' >> .env.tmp; mv .env.tmp .env"
fi

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << 'RESTART'
cd /opt/ominis-backend
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
RESTART

echo ""
echo "✓ Google OAuth credentials added to backend .env and service restarted."
