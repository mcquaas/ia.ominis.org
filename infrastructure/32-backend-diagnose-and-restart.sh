#!/usr/bin/env bash
# Diagnose why the backend is not responding: SSH in, show systemctl status and logs, optionally restart.
# Run from your MacBook (needs SSH access to the backend). Uses config/haystack_backend.txt.
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
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -i $KEY_FILE"

if [ ! -f "$KEY_FILE" ]; then
  echo "Error: SSH key not found at $KEY_FILE"
  exit 1
fi

echo "Backend: $BACKEND_IP (api.ominis.org)"
echo ""

echo "=== 1. systemctl status ominis-backend ==="
ssh $SSH_OPTS "$SSH_USER@$BACKEND_IP" 'sudo systemctl status ominis-backend --no-pager' 2>&1 || true
echo ""

echo "=== 2. Last 60 lines of journalctl (ominis-backend) ==="
ssh $SSH_OPTS "$SSH_USER@$BACKEND_IP" 'sudo journalctl -u ominis-backend -n 60 --no-pager' 2>&1 || true
echo ""

echo "=== 3. Local health (curl :8000/v1/health) ==="
HTTP=$(ssh $SSH_OPTS "$SSH_USER@$BACKEND_IP" 'curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://127.0.0.1:8000/v1/health' 2>/dev/null || echo "000")
echo "  HTTP $HTTP"
echo ""

if [ "$HTTP" != "200" ]; then
  if [ "$1" = "--restart" ]; then
    echo "Restarting ominis-backend..."
    ssh $SSH_OPTS "$SSH_USER@$BACKEND_IP" 'sudo systemctl restart ominis-backend && sleep 3 && sudo systemctl status ominis-backend --no-pager'
    echo ""
    echo "Checking health again..."
    sleep 2
    ssh $SSH_OPTS "$SSH_USER@$BACKEND_IP" 'curl -s http://127.0.0.1:8000/v1/health' 2>/dev/null || true
  else
    echo "To restart and see status, run: $0 --restart"
    echo "Or: ssh -i $KEY_FILE $SSH_USER@$BACKEND_IP 'sudo systemctl restart ominis-backend'"
    echo "Or sync code and restart: ./infrastructure/20-sync-backend.sh"
  fi
fi
