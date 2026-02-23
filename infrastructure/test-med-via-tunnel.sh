#!/bin/bash
# Test Ominis 2.0 Med (med42) via SSH tunnel. Run with the tunnel active in another terminal:
#   ssh -i ~/.ssh/gustavo-aws-FS.pem -p 13782 root@ssh8.vast.ai -L 11434:localhost:11434
# Then: ./infrastructure/test-med-via-tunnel.sh
set -e

BASE="${1:-http://localhost:11434}"
MODEL="${OLLAMA_MED_MODEL:-med42}"

echo "=== Test Med (Ollama) at $BASE ==="
echo ""

echo "1. Listing models..."
curl -s "$BASE/api/tags" | head -30
echo ""

echo "2. Quick generate (model=$MODEL, stream=false)..."
RESP=$(curl -s -X POST "$BASE/api/generate" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Di en una palabra: ¿qué día es hoy?\",\"stream\":false}" \
  --max-time 60)
if echo "$RESP" | grep -q '"response"'; then
  echo "$RESP" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print('Response:', (d.get('response') or '')[:500])
    print('Done:', d.get('done'))
except Exception as e:
    print('Raw:', sys.stdin.read()[:400])
" 2>/dev/null || echo "$RESP" | head -5
  echo ""
  echo "✓ Med responded correctly."
else
  echo "Response (raw): $RESP"
  echo "✗ No 'response' in output (model missing or error)."
fi
echo ""
