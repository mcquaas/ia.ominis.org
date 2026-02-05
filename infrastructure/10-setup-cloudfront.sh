#!/bin/bash
# Set up CloudFront for HTTPS access to the RAG API
# This creates a CloudFront distribution that proxies to the EC2 instance
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"
source "$SCRIPT_DIR/../config/ollama_server.txt"

DISTRIBUTION_NAME="ominis-health-api"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       Setting up CloudFront HTTPS for RAG API                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Origin: $OLLAMA_PUBLIC_IP:8080"
echo ""

# Create CloudFront distribution
cat << EOF > /tmp/cloudfront-config.json
{
    "CallerReference": "ominis-$(date +%s)",
    "Comment": "Ominis Health RAG API - HTTPS frontend",
    "Enabled": true,
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "ominis-ec2-origin",
                "DomainName": "$OLLAMA_PUBLIC_IP",
                "CustomOriginConfig": {
                    "HTTPPort": 8080,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only",
                    "OriginSslProtocols": {
                        "Quantity": 1,
                        "Items": ["TLSv1.2"]
                    }
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "ominis-ec2-origin",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
            "Quantity": 7,
            "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
            "CachedMethods": {
                "Quantity": 2,
                "Items": ["GET", "HEAD"]
            }
        },
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
        "Compress": true
    },
    "PriceClass": "PriceClass_100"
}
EOF

echo "Creating CloudFront distribution..."
DISTRIBUTION_ID=$(aws cloudfront create-distribution \
    --distribution-config file:///tmp/cloudfront-config.json \
    --query 'Distribution.Id' \
    --output text 2>&1)

if [[ "$DISTRIBUTION_ID" == *"error"* ]] || [[ "$DISTRIBUTION_ID" == *"Error"* ]]; then
    echo "Error creating distribution: $DISTRIBUTION_ID"
    exit 1
fi

# Get the distribution domain
DISTRIBUTION_DOMAIN=$(aws cloudfront get-distribution \
    --id "$DISTRIBUTION_ID" \
    --query 'Distribution.DomainName' \
    --output text)

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║               CloudFront Distribution Created                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Distribution ID:  $DISTRIBUTION_ID"
echo "Domain:           https://$DISTRIBUTION_DOMAIN"
echo "API Endpoint:     https://$DISTRIBUTION_DOMAIN/query"
echo ""
echo "Note: Distribution takes 5-15 minutes to deploy globally."
echo ""
echo "To check status:"
echo "  aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status'"
echo ""

# Save configuration
cat << EOF >> "$SCRIPT_DIR/../config/cloudfront.txt"
CLOUDFRONT_DISTRIBUTION_ID=$DISTRIBUTION_ID
CLOUDFRONT_DOMAIN=$DISTRIBUTION_DOMAIN
HTTPS_API_URL=https://$DISTRIBUTION_DOMAIN/query
EOF

echo "Configuration saved to config/cloudfront.txt"

# Clean up
rm -f /tmp/cloudfront-config.json
