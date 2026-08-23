#!/bin/bash
# Verify Vast.ai endpoints (Ollama Qwen/VL and Power gpt-oss) from config.
# Run from repo root. If curls fail locally, the backend may still reach Vast; test in the app.
# See: docs/VAST_RECREATE_INSTANCE.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"

echo "=== Vast endpoint verification ==="
echo ""

# Ollama Qwen/VL
if [ -f "$CONFIG_DIR/ollama_qwen_vast.txt" ]; then
  source "$CONFIG_DIR/ollama_qwen_vast.txt"
  if [ -n "$OLLAMA_QWEN_VAST_URL" ]; then
    echo "Ollama (Qwen/VL): $OLLAMA_QWEN_VAST_URL"
    if curl -s -m 15 "$OLLAMA_QWEN_VAST_URL/api/tags" > /tmp/ollama_tags.json 2>/dev/null; then
      echo "  OK – /api/tags reachable"
      (python3 -c "
import json
try:
    d = json.load(open('/tmp/ollama_tags.json'))
    models = d.get('models', [])
    names = [m.get('name', m.get('model', '')) for m in models]
    if names:
        print('  Models:', ', '.join(names[:10]))
    else:
        print('  Models: (none listed – pull qwen3:14b and qwen2.5vl:7b)')
except Exception as e:
    print('  (parse)', e)
" 2>/dev/null) || true
    else
      echo "  FAIL – cannot reach /api/tags (check IP:port and that Ollama is running on the instance)"
    fi
  fi
  echo ""
fi

# Power (gpt-oss)
if [ -f "$CONFIG_DIR/power_gpt_server.txt" ]; then
  source "$CONFIG_DIR/power_gpt_server.txt"
  if [ -n "$POWER_API_URL" ]; then
    echo "Power (gpt-oss): $POWER_API_URL"
    if curl -s -m 15 "$POWER_API_URL/v1/models" > /tmp/power_models.json 2>/dev/null; then
      echo "  OK – /v1/models reachable"
      (python3 -c "
import json
try:
    d = json.load(open('/tmp/power_models.json'))
    models = d.get('data', [])
    ids = [m.get('id', '') for m in models]
    if ids:
        print('  Models:', ', '.join(ids[:5]))
    else:
        print('  Models: (none or still loading)')
except Exception as e:
    print('  (parse)', e)
" 2>/dev/null) || true
    else
      echo "  FAIL – cannot reach /v1/models (check IP:port and that vLLM has finished loading)"
    fi
  fi
  echo ""
fi

echo "If curls failed from this machine, the backend EC2 may still reach Vast. Test chat/vision in the app."
