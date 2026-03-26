#!/bin/bash
# Test all Vast endpoints FROM the backend EC2 (same path as the app).
# Run from repo root. Requires config/haystack_backend.txt and config/ominis-ollama-key.pem.
# See: docs/VAST_RECREATE_INSTANCE.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
[ ! -f "$CONFIG_DIR/ominis-ollama-key.pem" ] && echo "Error: config/ominis-ollama-key.pem not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

echo "=== Vast endpoints test FROM backend $BACKEND_IP ==="
echo ""

# Ominis 2.0 (Ollama Qwen/VL)
if [ -f "$CONFIG_DIR/ollama_qwen_vast.txt" ]; then
  source "$CONFIG_DIR/ollama_qwen_vast.txt"
  echo "Ominis 2.0 (Ollama): $OLLAMA_QWEN_VAST_URL"
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$CONFIG_DIR/ominis-ollama-key.pem" ubuntu@$BACKEND_IP "curl -s -m 15 $OLLAMA_QWEN_VAST_URL/api/tags" 2>/dev/null | grep -q models; then
    echo "  OK – /api/tags reachable"
  else
    echo "  FAIL – backend cannot reach this URL (connection refused / timeout). Check instance is running and Ollama is listening (ollama serve)."
  fi
  echo ""
fi

# Ominis 2.0 Med (optional)
if [ -f "$CONFIG_DIR/ollama_med_server.txt" ]; then
  source "$CONFIG_DIR/ollama_med_server.txt"
  if [ -n "$OLLAMA_MED_URL" ]; then
    echo "Ominis 2.0 Med: $OLLAMA_MED_URL"
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$CONFIG_DIR/ominis-ollama-key.pem" ubuntu@$BACKEND_IP "curl -s -m 15 $OLLAMA_MED_URL/api/tags" 2>/dev/null | grep -q models; then
      echo "  OK – /api/tags reachable"
    else
      echo "  FAIL – backend cannot reach this URL"
    fi
    echo ""
  fi
fi

# OpenScholar 128K (optional)
if [ -f "$CONFIG_DIR/openscholar_128k_vast.txt" ]; then
  source "$CONFIG_DIR/openscholar_128k_vast.txt"
  if [ -n "$OPENSCHOLAR_128K_API_URL" ]; then
    echo "OpenScholar 128K: $OPENSCHOLAR_128K_API_URL"
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$CONFIG_DIR/ominis-ollama-key.pem" ubuntu@$BACKEND_IP "curl -s -m 15 $OPENSCHOLAR_128K_API_URL/v1/models" 2>/dev/null | grep -q object; then
      echo "  OK – /v1/models reachable"
    else
      echo "  FAIL – backend cannot reach this URL"
    fi
    echo ""
  fi
fi

echo "If Ominis 2.0 fails: in Vast check instance is running, IP & Port for 11434, and run 'ollama serve' + 'ollama list' in Connect shell."
