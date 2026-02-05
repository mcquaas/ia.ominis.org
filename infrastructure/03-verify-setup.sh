#!/bin/bash
# Phase 1: Verify AWS Infrastructure Setup
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

echo "=== Verifying Ominis Health AWS Infrastructure ==="
echo ""

ERRORS=0

# Check S3 buckets
echo "Checking S3 Buckets..."
for bucket in "$S3_BUCKET_RAW" "$S3_BUCKET_PROCESSED" "$S3_BUCKET_EMBEDDINGS" "$S3_BUCKET_MODELS"; do
    if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
        echo "  ✓ $bucket"
    else
        echo "  ✗ $bucket - NOT FOUND"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# Check IAM roles
echo "Checking IAM Roles..."
for role in "$SAGEMAKER_ROLE_NAME" "$LAMBDA_ROLE_NAME"; do
    if aws iam get-role --role-name "$role" >/dev/null 2>&1; then
        echo "  ✓ $role"
    else
        echo "  ✗ $role - NOT FOUND"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# Test S3 write access
echo "Testing S3 Write Access..."
TEST_FILE="/tmp/ominis-test-$$.txt"
echo "test" > "$TEST_FILE"

if aws s3 cp "$TEST_FILE" "s3://$S3_BUCKET_RAW/test/connection-test.txt" >/dev/null 2>&1; then
    echo "  ✓ Write access verified"
    aws s3 rm "s3://$S3_BUCKET_RAW/test/connection-test.txt" >/dev/null 2>&1
else
    echo "  ✗ Write access failed"
    ERRORS=$((ERRORS + 1))
fi

rm -f "$TEST_FILE"

echo ""
echo "=== Verification Complete ==="

if [ $ERRORS -eq 0 ]; then
    echo "✓ All checks passed! Infrastructure is ready."
    exit 0
else
    echo "✗ $ERRORS error(s) found. Please fix before proceeding."
    exit 1
fi
