#!/bin/bash
# Delete SageMaker endpoint (to save costs when not in use)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

ENDPOINT_NAME="$SAGEMAKER_ENDPOINT_NAME"

echo "=== Deleting SageMaker Endpoint ==="
echo "Endpoint: $ENDPOINT_NAME"
echo ""

read -p "Are you sure you want to delete this endpoint? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Get endpoint config name
CONFIG_NAME=$(aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --query 'EndpointConfigName' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "")

# Delete endpoint
echo "Deleting endpoint..."
aws sagemaker delete-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --region "$AWS_REGION" 2>/dev/null || echo "Endpoint not found"

# Delete endpoint config
if [ -n "$CONFIG_NAME" ]; then
    echo "Deleting endpoint configuration..."
    aws sagemaker delete-endpoint-config \
        --endpoint-config-name "$CONFIG_NAME" \
        --region "$AWS_REGION" 2>/dev/null || true
fi

echo ""
echo "✓ Endpoint deleted. This will stop incurring costs."
