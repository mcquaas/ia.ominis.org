#!/bin/bash
# Master setup script for Ominis Health LLM Infrastructure
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        Ominis Health LLM - AWS Infrastructure Setup          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check AWS CLI is configured
echo "Checking AWS CLI configuration..."
if aws sts get-caller-identity >/dev/null 2>&1; then
    ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    USER=$(aws sts get-caller-identity --query Arn --output text)
    echo "  ✓ Authenticated as: $USER"
    echo "  ✓ Account: $ACCOUNT"
else
    echo "  ✗ AWS CLI not configured. Run 'aws configure' first."
    exit 1
fi

echo ""

# Run setup scripts in order
echo "Step 1: Creating S3 Buckets..."
bash "$SCRIPT_DIR/01-setup-s3.sh"
echo ""

echo "Step 2: Creating IAM Roles..."
bash "$SCRIPT_DIR/02-setup-iam.sh"
echo ""

echo "Step 3: Verifying Setup..."
bash "$SCRIPT_DIR/03-verify-setup.sh"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Phase 1 Complete - Infrastructure Ready         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Configure WordPress API credentials in config/settings.sh"
echo "  2. Run the data ingestion script (scripts/ingestion/)"
echo ""
