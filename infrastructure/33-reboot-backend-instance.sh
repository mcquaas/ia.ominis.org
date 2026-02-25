#!/usr/bin/env bash
# Reboot the Haystack backend EC2 instance from AWS CLI (no SSH needed).
# Use when sshd is unresponsive and EC2 Instance Connect also fails.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
REGION="${AWS_REGION:-mx-central-1}"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

INSTANCE_ID="${BACKEND_INSTANCE_ID:-i-04464c8355e364211}"

echo "Instance: $INSTANCE_ID (api.ominis.org)"
echo "Region:   $REGION"
echo ""
echo "Rebooting..."
aws ec2 reboot-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
echo "  ✓ Reboot requested. Instance will be back in ~1–2 min."
echo ""
echo "Wait 2 min, then try:"
echo "  - EC2 Instance Connect in the console"
echo "  - ssh ubuntu@78.12.33.205 (from your machine)"
echo "  - curl https://api.ominis.org/v1/health"
