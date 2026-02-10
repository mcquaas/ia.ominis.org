#!/bin/bash
# Inject AWS credentials from local 'aws configure' into backend .env so the backend
# can call EC2 (DescribeInstances, StartInstances, StopInstances) in us-east-1.
# Does not print the secret.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
    echo "Error: config/haystack_backend.txt not found."
    exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"
REMOTE_DIR="/opt/ominis-backend"

AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id 2>/dev/null || true)
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key 2>/dev/null || true)

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Error: Run 'aws configure' and set aws_access_key_id and aws_secret_access_key."
    exit 1
fi

echo "Injecting AWS credentials into backend .env (backend: $BACKEND_IP)..."

# Write creds to a temp file so we don't echo the secret; then push to remote
TMP=$(mktemp)
trap "rm -f $TMP" EXIT
echo "# AWS for research instance start/stop (us-east-1) - 20b" >> "$TMP"
echo "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" >> "$TMP"
echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" >> "$TMP"

scp -o StrictHostKeyChecking=no -i "$KEY_FILE" "$TMP" "$SSH_USER@$BACKEND_IP:/tmp/aws_env_block.txt"

ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" << 'REMOTECMD'
set -e
cd /opt/ominis-backend
# Remove existing AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY lines
if [ -f .env ]; then
  grep -v '^AWS_ACCESS_KEY_ID=' .env | grep -v '^AWS_SECRET_ACCESS_KEY=' | grep -v '^# AWS for research' > .env.tmp
  sudo mv .env.tmp .env
  sudo chown ubuntu:ubuntu .env
fi
sudo cat /tmp/aws_env_block.txt >> .env
rm -f /tmp/aws_env_block.txt
sudo systemctl restart ominis-backend
sleep 2
sudo systemctl status ominis-backend --no-pager
REMOTECMD

echo "✓ AWS credentials injected and backend restarted."
echo "  Dashboard research instance switch should now show status (stopped/running)."
echo ""
