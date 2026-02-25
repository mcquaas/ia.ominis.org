#!/bin/bash
# Deploy Lambda: pipeline ingest-one-source (writes raw docs to S3 for nightly pipeline).
# After deploy, use 29j-trigger-lambda-ingest-and-pipeline.sh to run ingest then pipeline --from-s3.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

FUNCTION_NAME="${LAMBDA_FUNCTION_INGESTION:-ominis-pipeline-ingest}"
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME:-ominis-lambda-role}"
LAMBDA_DIR="$PROJECT_DIR/lambda/pipeline/ingest"
AWS_REGION="${AWS_REGION:-mx-central-1}"
BUCKET="${PIPELINE_RAW_BUCKET:-$S3_BUCKET_EMBEDDINGS}"
PREFIX="${PIPELINE_RAW_PREFIX:-pipeline/raw_docs}"

echo "=== Deploying Pipeline Ingest Lambda: $FUNCTION_NAME ==="
echo "  Region: $AWS_REGION  Bucket: $BUCKET  Prefix: $PREFIX"
echo ""

# Create deployment package
PACKAGE_DIR=$(mktemp -d)
trap "rm -rf '$PACKAGE_DIR'" EXIT
cd "$LAMBDA_DIR"
pip install -q -r requirements.txt -t "$PACKAGE_DIR" 2>/dev/null || true
cp handler.py "$PACKAGE_DIR/"
cd "$PACKAGE_DIR"
zip -r -q deploy.zip .
cd - > /dev/null

echo "Package size: $(du -h "$PACKAGE_DIR/deploy.zip" | cut -f1)"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" 2>/dev/null; then
    echo "Updating existing function..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$PACKAGE_DIR/deploy.zip" \
        --region "$AWS_REGION" --output text --query 'LastModified'
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --timeout 300 \
        --memory-size 512 \
        --environment "Variables={PIPELINE_RAW_BUCKET=$BUCKET,PIPELINE_RAW_PREFIX=$PREFIX}" \
        --region "$AWS_REGION" --output text --query 'LastModified' 2>/dev/null || true
else
    echo "Creating new function (requires IAM role $ROLE_ARN with S3 PutObject)..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.12 \
        --handler handler.handler \
        --role "$ROLE_ARN" \
        --zip-file "fileb://$PACKAGE_DIR/deploy.zip" \
        --timeout 300 \
        --memory-size 512 \
        --environment "Variables={PIPELINE_RAW_BUCKET=$BUCKET,PIPELINE_RAW_PREFIX=$PREFIX}" \
        --region "$AWS_REGION" --output text --query 'FunctionArn'
fi

aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$AWS_REGION" 2>/dev/null || true
echo ""
echo "✓ Deploy done. Invoke with: aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"source\":\"pubmed\"}' --region $AWS_REGION out.json && cat out.json"
echo "  Or run: ./infrastructure/29j-trigger-lambda-ingest-and-pipeline.sh"
