#!/bin/bash
# Get OpenSearch domain endpoint (run after domain is Active). Optionally wait for it.
# Usage: ./29b-get-opensearch-endpoint.sh [--wait]
set -e

DOMAIN_NAME="${OPENSEARCH_DOMAIN_NAME:-ominis-health-datastore}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
WAIT="${1:-}"

echo "Domain: $DOMAIN_NAME  Region: $REGION"
echo ""

if [ "$WAIT" = "--wait" ]; then
  echo "Waiting for domain to become Active (polling every 30s, max ~15 min)..."
  while true; do
    STATUS=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query 'DomainStatus.DomainProcessingStatus' --output text 2>/dev/null || echo "Unknown")
    echo "  Status: $STATUS"
    if [ "$STATUS" = "Active" ]; then
      break
    fi
    if [ "$STATUS" = "CreateFailed" ] || [ "$STATUS" = "DeleteRequested" ]; then
      echo "Domain in state $STATUS. Exiting."
      exit 1
    fi
    sleep 30
  done
  echo "Domain is Active."
  echo ""
fi

ENDPOINT=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query 'DomainStatus.Endpoint' --output text 2>/dev/null || echo "")

if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "None" ]; then
  PROCESSING=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query 'DomainStatus.Processing' --output text 2>/dev/null || echo "?")
  echo "Endpoint not available yet (Processing=$PROCESSING)."
  echo "Wait 5–15 minutes and run again, or: ./29b-get-opensearch-endpoint.sh --wait"
  exit 1
fi

echo "OPENSEARCH_URL=https://$ENDPOINT"
echo ""
echo "Add to backend .env:"
echo "  OPENSEARCH_URL=https://$ENDPOINT"
echo "  OPENSEARCH_INDEX=health-chunks"
