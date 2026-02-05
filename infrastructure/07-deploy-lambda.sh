#!/bin/bash
# Deploy Lambda function for Ominis Health Query API
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/../config/settings.sh"

FUNCTION_NAME="$LAMBDA_FUNCTION_QUERY"
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
LAMBDA_DIR="$PROJECT_DIR/lambda/query"

echo "=== Deploying Lambda Function: $FUNCTION_NAME ==="
echo ""

# Create deployment package
echo "Creating deployment package..."
PACKAGE_DIR=$(mktemp -d)
DEPLOY_ZIP="$PACKAGE_DIR/lambda.zip"

# Install dependencies (boto3 is already in Lambda runtime, but install if needed)
echo "Installing dependencies..."
pip install -q -t "$PACKAGE_DIR/package/" boto3 2>/dev/null || true

# Add handler code
cp "$LAMBDA_DIR/handler.py" "$PACKAGE_DIR/package/"

# Create zip
cd "$PACKAGE_DIR/package"
zip -r -q "$DEPLOY_ZIP" .
cd - > /dev/null

echo "  Package size: $(du -h "$DEPLOY_ZIP" | cut -f1)"

# Check if function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" 2>/dev/null; then
    echo "Updating existing function..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$DEPLOY_ZIP" \
        --region "$AWS_REGION" > /dev/null
    
    # Update configuration
    # OLLAMA_URL should be set after deploying EC2 (see config/ollama_server.txt)
    OLLAMA_URL_VALUE=${OLLAMA_URL:-"http://REPLACE_WITH_EC2_IP:11434"}
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --timeout 90 \
        --memory-size 512 \
        --environment "Variables={EMBEDDINGS_BUCKET=$S3_BUCKET_EMBEDDINGS,VECTOR_PREFIX=vectors,OLLAMA_URL=$OLLAMA_URL_VALUE,OLLAMA_MODEL=ominis-2.0,OMINIS_REGION=$AWS_REGION}" \
        --region "$AWS_REGION" > /dev/null
else
    echo "Creating new function..."
    # OLLAMA_URL should be set after deploying EC2 (see config/ollama_server.txt)
    OLLAMA_URL_VALUE=${OLLAMA_URL:-"http://REPLACE_WITH_EC2_IP:11434"}
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.11 \
        --handler handler.handler \
        --role "$ROLE_ARN" \
        --zip-file "fileb://$DEPLOY_ZIP" \
        --timeout 90 \
        --memory-size 512 \
        --environment "Variables={EMBEDDINGS_BUCKET=$S3_BUCKET_EMBEDDINGS,VECTOR_PREFIX=vectors,OLLAMA_URL=$OLLAMA_URL_VALUE,OLLAMA_MODEL=ominis-2.0,OMINIS_REGION=$AWS_REGION}" \
        --region "$AWS_REGION" > /dev/null
fi

# Wait for function to be ready
echo "Waiting for function to be active..."
aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$AWS_REGION"

# Cleanup
rm -rf "$PACKAGE_DIR"

echo ""
echo "✓ Lambda function deployed: $FUNCTION_NAME"
echo ""
echo "Function ARN:"
aws lambda get-function --function-name "$FUNCTION_NAME" --query 'Configuration.FunctionArn' --output text --region "$AWS_REGION"
