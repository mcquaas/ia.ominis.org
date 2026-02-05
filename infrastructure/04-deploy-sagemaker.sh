#!/bin/bash
# Deploy BioMistral model to SageMaker
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

echo "=== Deploying BioMistral to SageMaker ==="
echo ""

# Configuration for HuggingFace LLM deployment
MODEL_ID="BioMistral/BioMistral-7B"
INSTANCE_TYPE="ml.g5.2xlarge"  # GPU instance for inference
ENDPOINT_NAME="$SAGEMAKER_ENDPOINT_NAME"

# Get SageMaker role ARN
ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${SAGEMAKER_ROLE_NAME}"

echo "Model: $MODEL_ID"
echo "Instance: $INSTANCE_TYPE"
echo "Endpoint: $ENDPOINT_NAME"
echo "Role: $ROLE_ARN"
echo ""

# Check if endpoint already exists
if aws sagemaker describe-endpoint --endpoint-name "$ENDPOINT_NAME" 2>/dev/null; then
    echo "Endpoint already exists. Use update or delete first."
    exit 1
fi

# Create model configuration
echo "Creating SageMaker model..."

# Use HuggingFace Deep Learning Container for LLM inference
# Get the latest HuggingFace LLM DLC image
HF_IMAGE_URI="763104351884.dkr.ecr.${AWS_REGION}.amazonaws.com/huggingface-pytorch-tgi-inference:2.1.1-tgi1.4.0-gpu-py310-cu121-ubuntu22.04"

# Create model
MODEL_NAME="ominis-biomistral-model-$(date +%Y%m%d%H%M%S)"

aws sagemaker create-model \
    --model-name "$MODEL_NAME" \
    --primary-container \
        Image="$HF_IMAGE_URI",Environment="{HF_MODEL_ID=$MODEL_ID,HF_TASK=text-generation,SM_NUM_GPUS=1}" \
    --execution-role-arn "$ROLE_ARN" \
    --region "$AWS_REGION"

echo "  ✓ Model created: $MODEL_NAME"

# Create endpoint configuration
CONFIG_NAME="ominis-biomistral-config-$(date +%Y%m%d%H%M%S)"

aws sagemaker create-endpoint-config \
    --endpoint-config-name "$CONFIG_NAME" \
    --production-variants \
        VariantName=AllTraffic,ModelName="$MODEL_NAME",InitialInstanceCount=1,InstanceType="$INSTANCE_TYPE" \
    --region "$AWS_REGION"

echo "  ✓ Endpoint config created: $CONFIG_NAME"

# Create endpoint
echo "Creating endpoint (this may take 10-15 minutes)..."

aws sagemaker create-endpoint \
    --endpoint-name "$ENDPOINT_NAME" \
    --endpoint-config-name "$CONFIG_NAME" \
    --region "$AWS_REGION"

echo ""
echo "Endpoint creation initiated. Monitor status with:"
echo "  aws sagemaker describe-endpoint --endpoint-name $ENDPOINT_NAME --query 'EndpointStatus'"
echo ""
echo "Or run: ./infrastructure/05-check-endpoint.sh"
