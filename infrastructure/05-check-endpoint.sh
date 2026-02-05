#!/bin/bash
# Check SageMaker endpoint status
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

ENDPOINT_NAME="$SAGEMAKER_ENDPOINT_NAME"

echo "=== Checking SageMaker Endpoint Status ==="
echo "Endpoint: $ENDPOINT_NAME"
echo ""

# Get endpoint status
STATUS=$(aws sagemaker describe-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --query 'EndpointStatus' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

case "$STATUS" in
    "InService")
        echo "✓ Endpoint is READY and serving traffic"
        echo ""
        echo "Endpoint ARN:"
        aws sagemaker describe-endpoint \
            --endpoint-name "$ENDPOINT_NAME" \
            --query 'EndpointArn' \
            --output text \
            --region "$AWS_REGION"
        ;;
    "Creating")
        echo "⏳ Endpoint is being created..."
        echo "   This typically takes 10-15 minutes."
        echo ""
        echo "Check again in a few minutes."
        ;;
    "Updating")
        echo "⏳ Endpoint is being updated..."
        ;;
    "Failed")
        echo "✗ Endpoint creation FAILED"
        echo ""
        echo "Failure reason:"
        aws sagemaker describe-endpoint \
            --endpoint-name "$ENDPOINT_NAME" \
            --query 'FailureReason' \
            --output text \
            --region "$AWS_REGION"
        ;;
    "NOT_FOUND")
        echo "✗ Endpoint not found"
        echo "  Run ./infrastructure/04-deploy-sagemaker.sh first"
        ;;
    *)
        echo "Status: $STATUS"
        ;;
esac
