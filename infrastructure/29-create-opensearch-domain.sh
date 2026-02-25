#!/bin/bash
# Create AWS OpenSearch domain for health datastore (BM25). Uses AWS CLI.
# Requires: AWS credentials configured (env or ~/.aws). Region from AWS_REGION or AWS_DEFAULT_REGION.
set -e

DOMAIN_NAME="${OPENSEARCH_DOMAIN_NAME:-ominis-health-datastore}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
# Allow same AWS account to access the domain
ACCESS_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":"arn:aws:iam::'"$ACCOUNT_ID"':root"},"Action":"es:*","Resource":"arn:aws:es:'"$REGION"'::'"$DOMAIN_NAME"'/*"}]}'

echo "Creating OpenSearch domain: $DOMAIN_NAME in $REGION"

aws opensearch create-domain \
  --domain-name "$DOMAIN_NAME" \
  --engine-version "OpenSearch_2.11" \
  --cluster-config "InstanceType=t3.small.search,InstanceCount=1" \
  --ebs-options "EBSEnabled=true,VolumeType=gp3,VolumeSize=10" \
  --access-policies "$ACCESS_POLICY" \
  --region "$REGION" \
  --output json > /tmp/opensearch-create.json 2>&1 || true

if grep -q "DomainAlreadyExists" /tmp/opensearch-create.json 2>/dev/null; then
  echo "Domain $DOMAIN_NAME already exists."
else
  cat /tmp/opensearch-create.json
fi

# Get endpoint (domain may take 5–10 min to become active) (domain may take 5–10 min to become active)
ENDPOINT=$(aws opensearch describe-domain --domain-name "$DOMAIN_NAME" --region "$REGION" --query 'DomainStatus.Endpoint' --output text 2>/dev/null || echo "")
if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "None" ]; then
  echo "Domain is still creating. Run again later to get endpoint:"
  echo "  aws opensearch describe-domain --domain-name $DOMAIN_NAME --region $REGION --query 'DomainStatus.Endpoint' --output text"
  echo "Then set: OPENSEARCH_URL=https://<endpoint>"
else
  echo ""
  echo "OPENSEARCH_URL=https://$ENDPOINT"
  echo "Add to backend .env: OPENSEARCH_URL=https://$ENDPOINT"
  echo "Add to pipeline .env: OPENSEARCH_URL=https://$ENDPOINT"
fi
