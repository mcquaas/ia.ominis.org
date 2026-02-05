#!/bin/bash
# Phase 1: Create IAM Roles for Ominis Health LLM
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

echo "=== Creating IAM Roles for Ominis Health LLM ==="
echo ""

# Function to create role if it doesn't exist
create_role() {
    local role_name=$1
    local trust_policy=$2
    local execution_policy=$3
    local description=$4
    
    echo "Creating role: $role_name"
    
    if aws iam get-role --role-name "$role_name" 2>/dev/null; then
        echo "  ✓ Role already exists"
    else
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document "file://$trust_policy" \
            --description "$description"
        echo "  ✓ Role created"
    fi
    
    # Attach execution policy
    local policy_name="${role_name}-policy"
    echo "  Attaching execution policy: $policy_name"
    
    if aws iam get-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${policy_name}" 2>/dev/null; then
        echo "    ✓ Policy already exists"
    else
        aws iam create-policy \
            --policy-name "$policy_name" \
            --policy-document "file://$execution_policy"
        echo "    ✓ Policy created"
    fi
    
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${policy_name}" 2>/dev/null || true
    echo "    ✓ Policy attached"
}

# Create SageMaker role
create_role \
    "$SAGEMAKER_ROLE_NAME" \
    "$SCRIPT_DIR/iam-policies/sagemaker-trust-policy.json" \
    "$SCRIPT_DIR/iam-policies/sagemaker-execution-policy.json" \
    "Role for Ominis Health SageMaker endpoints"

# Attach AWS managed policies for SageMaker
echo "  Attaching AWS managed policies..."
aws iam attach-role-policy \
    --role-name "$SAGEMAKER_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess" 2>/dev/null || true

echo ""

# Create Lambda role
create_role \
    "$LAMBDA_ROLE_NAME" \
    "$SCRIPT_DIR/iam-policies/lambda-trust-policy.json" \
    "$SCRIPT_DIR/iam-policies/lambda-execution-policy.json" \
    "Role for Ominis Health Lambda functions"

# Attach AWS managed policies for Lambda
echo "  Attaching AWS managed policies..."
aws iam attach-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>/dev/null || true

echo ""
echo "=== IAM Roles Ready ==="
echo ""
echo "Roles created:"
echo "  - $SAGEMAKER_ROLE_NAME (arn:aws:iam::${AWS_ACCOUNT_ID}:role/${SAGEMAKER_ROLE_NAME})"
echo "  - $LAMBDA_ROLE_NAME (arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME})"
