#!/bin/bash
# Phase 1: Create S3 Buckets for Ominis Health LLM
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

echo "=== Creating S3 Buckets for Ominis Health LLM ==="
echo "Region: $AWS_REGION"
echo ""

# Function to create bucket if it doesn't exist
create_bucket() {
    local bucket_name=$1
    local description=$2
    
    echo "Creating bucket: $bucket_name ($description)"
    
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        echo "  ✓ Bucket already exists"
    else
        # For mx-central-1, we need LocationConstraint
        if [ "$AWS_REGION" = "us-east-1" ]; then
            aws s3api create-bucket \
                --bucket "$bucket_name" \
                --region "$AWS_REGION"
        else
            aws s3api create-bucket \
                --bucket "$bucket_name" \
                --region "$AWS_REGION" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi
        
        # Enable versioning for data integrity
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled
        
        # Block public access
        aws s3api put-public-access-block \
            --bucket "$bucket_name" \
            --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
        
        echo "  ✓ Created and configured"
    fi
}

# Create all required buckets
create_bucket "$S3_BUCKET_RAW" "Raw WordPress data"
create_bucket "$S3_BUCKET_PROCESSED" "Processed/cleaned documents"
create_bucket "$S3_BUCKET_EMBEDDINGS" "Vector embeddings"
create_bucket "$S3_BUCKET_MODELS" "Model artifacts"

echo ""
echo "=== S3 Buckets Ready ==="

# Create folder structure in raw bucket
echo "Creating folder structure..."
aws s3api put-object --bucket "$S3_BUCKET_RAW" --key "wordpress/" --content-length 0
aws s3api put-object --bucket "$S3_BUCKET_PROCESSED" --key "documents/" --content-length 0
aws s3api put-object --bucket "$S3_BUCKET_PROCESSED" --key "chunks/" --content-length 0
aws s3api put-object --bucket "$S3_BUCKET_EMBEDDINGS" --key "vectors/" --content-length 0

echo "  ✓ Folder structure created"
echo ""
echo "Buckets created:"
aws s3 ls | grep ominis-health
