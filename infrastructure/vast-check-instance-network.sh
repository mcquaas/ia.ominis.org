#!/bin/bash
# Use Vast CLI to report network/port status for your instances.
# Vast.ai does NOT expose a per-instance firewall or IP allowlist in the CLI or API.
# Ports opened with -p are public on the instance's public_ipaddr; connectivity
# depends on network path (e.g. your backend EC2 may not reach some Vast host IPs).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VASTAI_CMD=""
[ -x "$SCRIPT_DIR/venv-vast/bin/vastai" ] && VASTAI_CMD="$SCRIPT_DIR/venv-vast/bin/vastai"
[ -z "$VASTAI_CMD" ] && command -v vastai &>/dev/null && VASTAI_CMD="vastai"

if [ -z "$VASTAI_CMD" ]; then
  echo "vastai CLI not found. Run: ./infrastructure/setup-vast-cli.sh"
  exit 1
fi

echo "=== Vast instances (network summary) ==="
echo ""

$VASTAI_CMD show instances 2>&1 | head -20

echo ""
echo "=== Per-instance network (--raw) ==="
for id in $($VASTAI_CMD show instances --raw 2>/dev/null | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    instances = data if isinstance(data, list) else data.get('instances', [])
    for i in instances:
        print(i.get('id', i.get('instance_id', '')))
except Exception:
    pass
" 2>/dev/null); do
  [ -z "$id" ] && continue
  echo "--- Instance $id ---"
  $VASTAI_CMD show instance "$id" --raw 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('  label:       ', d.get('label') or d.get('id'))
    print('  public_ip:   ', d.get('public_ipaddr'))
    print('  external:    ', d.get('external'), '(True = dedicated IP)')
    print('  static_ip:   ', d.get('static_ip'))
    print('  port_range:  ', d.get('direct_port_start'), '-', d.get('direct_port_end'))
    ports = d.get('ports') or {}
    for k, v in ports.items():
        hp = v[0]['HostPort'] if isinstance(v, list) and v else v.get('HostPort', '')
        print('  map ', k, '->', hp)
except Exception as e:
    print('  error:', e)
" 2>/dev/null || true
  echo ""
done

echo "=== Firewall note ==="
echo "  Vast CLI has no firewall or IP-allowlist commands."
echo "  show ipaddrs = history of IPs that accessed the Vast API (your account), not instance access."
echo "  If your backend cannot reach an instance, try: same-region offer, or use Vast 'Instance Portal' (Cloudflare tunnel)."
echo ""
