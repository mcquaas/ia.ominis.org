#!/bin/bash
# Check whether the backend is using RDS or local PostgreSQL (via /v1/health)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../config/haystack_backend.txt" ]; then
    source "$SCRIPT_DIR/../config/haystack_backend.txt"
fi
URL="${BACKEND_URL:-http://localhost:8000}/v1/health"

echo "Checking: $URL"
RESP=$(curl -sS "$URL" 2>/dev/null || true)
if [ -z "$RESP" ]; then
    echo "Error: Could not reach backend at $URL"
    exit 1
fi

DB=$(echo "$RESP" | sed -n 's/.*"database"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
if [ -z "$DB" ]; then
    echo "$RESP"
    echo "Could not determine database type from response"
    exit 1
fi

echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"
echo ""
if [ "$DB" = "rds" ]; then
    echo "✓ Backend is using RDS."
else
    echo "→ Backend is using: $DB (not RDS). To switch to RDS see docs/RDS_MIGRATION.md"
fi
