#!/bin/bash
# =============================================================================
# Decommission Legacy RAG API Server (78.13.254.66)
# =============================================================================
# Run AFTER deploying watchdog to Haystack and verifying status page works.
#
# Prerequisites:
#   1. Watchdog deployed and running on Haystack (78.12.33.205)
#   2. verify: curl -s https://api.ominis.org/status/ | head -5
#
# This script STOPS the instance. Use --terminate to permanently delete.
# =============================================================================

set -e

LEGACY_INSTANCE_ID="i-02264316b8b094bad"
LEGACY_IP="78.13.254.66"
REGION="mx-central-1"

TERMINATE=false
SKIP_CONFIRM=false
for arg in "$@"; do
    case $arg in
        --terminate) TERMINATE=true ;;
        -y|--yes) SKIP_CONFIRM=true ;;
    esac
done

echo "=== Decommission Legacy RAG API Server ==="
echo "Instance: $LEGACY_INSTANCE_ID ($LEGACY_IP)"
echo ""

# Safety check
echo "Before proceeding, ensure:"
echo "  1. Watchdog is running on Haystack: ssh ominis-haystack 'systemctl is-active ominis-watchdog.timer'"
echo "  2. Status page works: curl -s https://api.ominis.org/status/ | head -5"
echo ""
if [ "$SKIP_CONFIRM" != true ]; then
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

echo "Stopping instance $LEGACY_INSTANCE_ID..."
aws ec2 stop-instances --region $REGION --instance-ids $LEGACY_INSTANCE_ID
aws ec2 wait instance-stopped --region $REGION --instance-ids $LEGACY_INSTANCE_ID
echo "Instance stopped."

if [ "$TERMINATE" = true ]; then
    echo ""
    echo "WARNING: --terminate will PERMANENTLY DELETE the instance and its EBS volume."
    echo "Elastic IP will be disassociated and can be released separately."
    if [ "$SKIP_CONFIRM" != true ]; then
        read -p "Terminate permanently? (y/N) " -n 1 -r
        echo
    fi
    if [[ $SKIP_CONFIRM = true || $REPLY =~ ^[Yy]$ ]]; then
        aws ec2 terminate-instances --region $REGION --instance-ids $LEGACY_INSTANCE_ID
        echo "Instance terminated. Release Elastic IP separately if desired."
    else
        echo "Termination cancelled."
    fi
else
    echo ""
    echo "Instance stopped (not terminated). To terminate: $0 --terminate"
    echo "To start again: aws ec2 start-instances --region $REGION --instance-ids $LEGACY_INSTANCE_ID"
fi
