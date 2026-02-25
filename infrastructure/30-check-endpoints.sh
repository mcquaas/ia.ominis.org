#!/usr/bin/env bash
# Check backend and frontend auth endpoints manually.
# Run from your machine (needs curl). Adjust BASE_BACKEND / BASE_FRONTEND if needed.
set -e

BASE_BACKEND="${BASE_BACKEND:-https://api.ominis.org}"
BASE_FRONTEND="${BASE_FRONTEND:-https://ia.ominis.org}"

echo "=== Backend (Haystack) ==="
echo "  Base: $BASE_BACKEND"
echo ""

echo "1. GET $BASE_BACKEND/v1/health"
HTTP=$(curl -s -o /tmp/health.json -w "%{http_code}" --connect-timeout 10 "$BASE_BACKEND/v1/health" 2>/dev/null) || HTTP="000"
[ -z "$HTTP" ] && HTTP="000"
if [ "$HTTP" = "200" ]; then
  echo "   Status: $HTTP OK"
  [ -f /tmp/health.json ] && cat /tmp/health.json | head -c 200
  echo ""
else
  echo "   Status: ${HTTP:-000} (failed or timeout if 000)"
fi
echo ""

echo "2. POST $BASE_BACKEND/v1/api/auth/local (login; 400 = invalid creds, backend is up)"
HTTP_BACKEND=$(curl -s -o /tmp/login_backend.json -w "%{http_code}" --connect-timeout 10 -X POST "$BASE_BACKEND/v1/api/auth/local" \
  -H "Content-Type: application/json" \
  -d '{"identifier":"gustavo","password":"test"}' 2>/dev/null) || HTTP_BACKEND="000"
[ -z "$HTTP_BACKEND" ] && HTTP_BACKEND="000"
echo "   Status: $HTTP_BACKEND"
[ -f /tmp/login_backend.json ] && echo "   Body: $(cat /tmp/login_backend.json | head -c 120)"
echo ""

echo "=== Frontend (Next.js proxy) ==="
echo "  Base: $BASE_FRONTEND"
echo ""

echo "3. POST $BASE_FRONTEND/api/auth/login (proxy to backend)"
HTTP=$(curl -s -o /tmp/login_frontend.json -w "%{http_code}" --connect-timeout 15 -X POST "$BASE_FRONTEND/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"identifier":"gustavo","password":"test"}' 2>/dev/null) || HTTP="000"
[ -z "$HTTP" ] && HTTP="000"
echo "   Status: $HTTP"
[ -f /tmp/login_frontend.json ] && echo "   Body: $(cat /tmp/login_frontend.json | head -c 200)"
echo ""

echo "--- Summary ---"
if [ "$HTTP_BACKEND" = "000" ]; then
  echo "Backend (2): unreachable from this machine (timeout/firewall). Run from a host that can reach $BASE_BACKEND."
fi
if [ "$HTTP" = "200" ]; then
  echo "Login proxy (3): 200 = backend reachable from frontend; login works."
elif [ "$HTTP" = "400" ]; then
  echo "Login proxy (3): 400 = backend reachable; invalid credentials (expected for test)."
elif [ "$HTTP" = "502" ]; then
  echo "Login proxy (3): 502 = frontend server could not reach backend. Set BACKEND_URL on frontend host and ensure $BASE_BACKEND is up."
elif [ "$HTTP" = "000" ]; then
  echo "Login proxy (3): unreachable from this machine. Run from a host that can reach $BASE_FRONTEND."
fi
