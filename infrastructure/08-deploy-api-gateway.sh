#!/bin/bash
# Deploy REST API Gateway for Ominis Health Query API (for regions without HTTP API support)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

API_NAME="$API_NAME"
FUNCTION_NAME="$LAMBDA_FUNCTION_QUERY"

echo "=== Deploying REST API Gateway: $API_NAME ==="
echo ""

# Get Lambda function ARN
LAMBDA_ARN=$(aws lambda get-function \
    --function-name "$FUNCTION_NAME" \
    --query 'Configuration.FunctionArn' \
    --output text \
    --region "$AWS_REGION")

echo "Lambda ARN: $LAMBDA_ARN"

# Check if API already exists
API_ID=$(aws apigateway get-rest-apis \
    --query "items[?name=='$API_NAME'].id" \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "")

if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
    echo "API already exists: $API_ID"
else
    echo "Creating new REST API..."
    
    API_ID=$(aws apigateway create-rest-api \
        --name "$API_NAME" \
        --description "Ominis Health Query API" \
        --endpoint-configuration types=REGIONAL \
        --query 'id' \
        --output text \
        --region "$AWS_REGION")
    
    echo "  Created API: $API_ID"
fi

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id "$API_ID" \
    --query 'items[?path==`/`].id' \
    --output text \
    --region "$AWS_REGION")

echo "Root resource ID: $ROOT_ID"

# Create /query resource if it doesn't exist
QUERY_RESOURCE_ID=$(aws apigateway get-resources \
    --rest-api-id "$API_ID" \
    --query "items[?path=='/query'].id" \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "")

if [ -z "$QUERY_RESOURCE_ID" ] || [ "$QUERY_RESOURCE_ID" = "None" ]; then
    echo "Creating /query resource..."
    QUERY_RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$ROOT_ID" \
        --path-part "query" \
        --query 'id' \
        --output text \
        --region "$AWS_REGION")
    echo "  Created resource: $QUERY_RESOURCE_ID"
fi

# Create POST method
echo "Creating POST method..."
aws apigateway put-method \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method POST \
    --authorization-type NONE \
    --region "$AWS_REGION" 2>/dev/null || true

# Create OPTIONS method for CORS
echo "Creating OPTIONS method for CORS..."
aws apigateway put-method \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method OPTIONS \
    --authorization-type NONE \
    --region "$AWS_REGION" 2>/dev/null || true

# Set up Lambda integration for POST
echo "Setting up Lambda integration..."
aws apigateway put-integration \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region "$AWS_REGION"

# Set up mock integration for OPTIONS (CORS)
aws apigateway put-integration \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method OPTIONS \
    --type MOCK \
    --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
    --region "$AWS_REGION" 2>/dev/null || true

# Set up OPTIONS method response
aws apigateway put-method-response \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":true,"method.response.header.Access-Control-Allow-Methods":true,"method.response.header.Access-Control-Allow-Origin":true}' \
    --region "$AWS_REGION" 2>/dev/null || true

# Set up OPTIONS integration response
aws apigateway put-integration-response \
    --rest-api-id "$API_ID" \
    --resource-id "$QUERY_RESOURCE_ID" \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"'"'"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"'"'","method.response.header.Access-Control-Allow-Methods":"'"'"'POST,OPTIONS'"'"'","method.response.header.Access-Control-Allow-Origin":"'"'"'*'"'"'"}' \
    --region "$AWS_REGION" 2>/dev/null || true

# Add Lambda permission for API Gateway
echo "Adding Lambda permission..."
aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "apigateway-invoke-$(date +%s)" \
    --action "lambda:InvokeFunction" \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT_ID}:${API_ID}/*/*/query" \
    --region "$AWS_REGION" 2>/dev/null || true

# Deploy API
echo "Deploying API to 'prod' stage..."
aws apigateway create-deployment \
    --rest-api-id "$API_ID" \
    --stage-name prod \
    --region "$AWS_REGION" 2>/dev/null || \
aws apigateway create-deployment \
    --rest-api-id "$API_ID" \
    --stage-name prod \
    --region "$AWS_REGION"

# Get API endpoint
API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   API Gateway Deployed                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "API Endpoint: $API_ENDPOINT"
echo "Query URL:    $API_ENDPOINT/query"
echo ""
echo "Test with:"
echo "  curl -X POST '$API_ENDPOINT/query' \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"question\": \"¿Qué es la diabetes?\"}'"
echo ""

# Save endpoint to config
echo "API_ENDPOINT=$API_ENDPOINT" > "$SCRIPT_DIR/../config/api_endpoint.txt"
