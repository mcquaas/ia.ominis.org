#!/bin/bash
# Pull Med42 on an Ollama server via its API (e.g. Vast instance). No SSH needed.
# Usage: ./infrastructure/pull-med42-via-api.sh [BASE_URL]
#   BASE_URL = base URL of Ollama (e.g. http://69.63.236.190:39123). If omitted, reads from config/ollama_med_server.txt OLLAMA_MED_URL.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

if [ -n "$1" ]; then
  BASE_URL="${1%/}"
else
  [ -f "$CONFIG_DIR/ollama_med_server.txt" ] && source "$CONFIG_DIR/ollama_med_server.txt"
  BASE_URL="${OLLAMA_MED_URL%/}"
fi

MED_MODEL="${OLLAMA_MED_MODEL:-med42}"

if [ -z "$BASE_URL" ]; then
  echo "Usage: $0 <Ollama base URL>"
  echo "  Example: $0 http://69.63.236.190:39123"
  echo "  Or set OLLAMA_MED_URL in config/ollama_med_server.txt and run $0"
  exit 1
fi

echo "Pulling $MED_MODEL on $BASE_URL (via API)..."
echo ""

curl -s -X POST "$BASE_URL/api/pull" -d "{\"name\":\"$MED_MODEL\"}" --max-time 600

echo ""
echo "✓ Pull requested. Check with: curl -s $BASE_URL/api/tags | head -20"
echo "  Then set config/ollama_med_server.txt: OLLAMA_MED_URL=$BASE_URL"
echo "  Run: ./infrastructure/20med-update-backend-env-ollama-med.sh"
echo ""
