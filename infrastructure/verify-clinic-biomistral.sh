#!/bin/bash
# Verify that Ominis 2.0 Clinic is configured to use BioMistral and that the Ollama server has that model.
# 1) Reads OLLAMA_URL, OLLAMA_CLINIC_URL, OLLAMA_CLINIC_MODEL from backend .env (via SSH).
# 2) Curls the effective Ollama server /api/tags and checks that the clinic model name appears.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

[ ! -f "$CONFIG_DIR/haystack_backend.txt" ] && echo "Error: config/haystack_backend.txt not found." && exit 1
source "$CONFIG_DIR/haystack_backend.txt"

KEY_FILE="$CONFIG_DIR/ominis-ollama-key.pem"
SSH_USER="ubuntu"

[ ! -f "$KEY_FILE" ] && echo "Error: SSH key not found at $KEY_FILE" && exit 1

echo "Checking backend config and Ollama server for Ominis 2.0 Clinic (BioMistral)..."
echo ""

# Get env from backend (strip quotes and comments)
ENV_BLOCK=$(ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "$SSH_USER@$BACKEND_IP" "grep -E '^OLLAMA_URL=|^OLLAMA_CLINIC_URL=|^OLLAMA_CLINIC_MODEL=' /opt/ominis-backend/.env 2>/dev/null || true")
OLLAMA_URL=$(echo "$ENV_BLOCK" | grep '^OLLAMA_URL=' | sed 's/^OLLAMA_URL=//' | tr -d '"' | xargs)
OLLAMA_CLINIC_URL=$(echo "$ENV_BLOCK" | grep '^OLLAMA_CLINIC_URL=' | sed 's/^OLLAMA_CLINIC_URL=//' | tr -d '"' | xargs)
OLLAMA_CLINIC_MODEL=$(echo "$ENV_BLOCK" | grep '^OLLAMA_CLINIC_MODEL=' | sed 's/^OLLAMA_CLINIC_MODEL=//' | tr -d '"' | xargs)

# Effective URL for clinic: CLINIC_URL or OLLAMA_URL
EFFECTIVE_URL="${OLLAMA_CLINIC_URL:-$OLLAMA_URL}"
CLINIC_MODEL="${OLLAMA_CLINIC_MODEL:-biomistral}"

if [ -z "$EFFECTIVE_URL" ]; then
  echo "Could not read OLLAMA_URL from backend .env (or it is empty)."
  exit 1
fi

echo "  OLLAMA_URL (backend):     $OLLAMA_URL"
echo "  OLLAMA_CLINIC_URL:       ${OLLAMA_CLINIC_URL:-<empty, using OLLAMA_URL>}"
echo "  OLLAMA_CLINIC_MODEL:     $CLINIC_MODEL"
echo "  Ollama server to check:  $EFFECTIVE_URL"
echo ""

# Normalize URL (add http if missing, strip trailing slash)
BASE="${EFFECTIVE_URL}"
[[ "$BASE" != http* ]] && BASE="http://$BASE"
BASE="${BASE%/}"

# Fetch /api/tags from Ollama (may be unreachable from this machine)
TAGS_JSON=$(curl -s -m 10 "$BASE/api/tags" 2>/dev/null || true)
if [ -z "$TAGS_JSON" ]; then
  echo "  Could not reach $BASE/api/tags (timeout or network). Check from backend or dashboard."
  echo "  Backend sends model name \"$CLINIC_MODEL\" for ominis-2.0-clinic (see app/config.py)."
  exit 0
fi

MODEL_NAMES=$(echo "$TAGS_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    for m in d.get('models', []):
        print(m.get('name', ''))
except Exception:
    pass
" 2>/dev/null)

if echo "$MODEL_NAMES" | grep -qE "^${CLINIC_MODEL}(:|$)"; then
  echo "  ✓ Server has model matching OLLAMA_CLINIC_MODEL: $CLINIC_MODEL"
  echo "  ✓ Ominis 2.0 Clinic is using BioMistral (or the configured clinic model)."
else
  echo "  ✗ Server models: $(echo "$MODEL_NAMES" | tr '\n' ' ')"
  echo "  ✗ No model named \"$CLINIC_MODEL\" found. Clinic requests may fail."
  echo "  On the Ollama server run: ollama pull $CLINIC_MODEL"
  exit 1
fi
