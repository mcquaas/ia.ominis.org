#!/bin/bash
# Deploy Next.js Frontend on EC2 in Mexico (mx-central-1)
# Small instance for serving the Ominis Health frontend at ia.ominis.org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

# EC2 Configuration - small instance is sufficient for Next.js
INSTANCE_TYPE="t3.small"  # 2 vCPU, 2GB RAM - plenty for Next.js
INSTANCE_NAME="ominis-frontend-server"
KEY_NAME="ominis-frontend-key"
SECURITY_GROUP_NAME="ominis-frontend-sg"
DOMAIN_NAME="ia.ominis.org"

# Use standard Ubuntu 24.04 AMI
AMI_ID="ami-0a57f819c3fccde4f"  # Ubuntu 24.04 LTS in mx-central-1

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    Deploying Frontend Server in Mexico (mx-central-1)        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE"
echo "Domain:        $DOMAIN_NAME"
echo "AMI:           $AMI_ID (Ubuntu 24.04)"
echo ""

# Create key pair if it doesn't exist
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$AWS_REGION" 2>/dev/null; then
    echo "Creating SSH key pair..."
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --query 'KeyMaterial' \
        --output text \
        --region "$AWS_REGION" > "$SCRIPT_DIR/../config/${KEY_NAME}.pem"
    chmod 400 "$SCRIPT_DIR/../config/${KEY_NAME}.pem"
    echo "  ✓ Key saved to config/${KEY_NAME}.pem"
else
    echo "  ✓ Key pair already exists"
fi

# Create security group if it doesn't exist
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[0].GroupId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "Frontend Server for Ominis Health (ia.ominis.org)" \
        --query 'GroupId' \
        --output text \
        --region "$AWS_REGION")
    
    # Allow SSH
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region "$AWS_REGION"
    
    # Allow HTTP (for Let's Encrypt verification and redirect)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 \
        --region "$AWS_REGION"
    
    # Allow HTTPS
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0 \
        --region "$AWS_REGION"
    
    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# Read Ollama server config for API endpoint
if [ -f "$SCRIPT_DIR/../config/ollama_server.txt" ]; then
    source "$SCRIPT_DIR/../config/ollama_server.txt"
    RAG_API_URL="${RAG_API_URL:-http://$ELASTIC_IP/query}"
else
    RAG_API_URL="http://78.13.254.66/query"
fi

# User data script to set up frontend
USER_DATA=$(cat << USERDATA
#!/bin/bash
set -e
exec > /var/log/frontend-setup.log 2>&1

echo "=== Updating system ==="
apt-get update && apt-get upgrade -y

echo "=== Installing Node.js 20 LTS ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo "=== Installing Nginx ==="
apt-get install -y nginx

echo "=== Installing PM2 ==="
npm install -g pm2

echo "=== Creating app directory ==="
mkdir -p /opt/ominis-frontend
cd /opt/ominis-frontend

echo "=== Creating Next.js app structure ==="
# Create package.json
cat << 'PKGJSON' > package.json
{
  "name": "ominis-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start -p 3000"
  },
  "dependencies": {
    "next": "15.1.6",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/node": "^22",
    "@types/react": "^19",
    "typescript": "^5"
  }
}
PKGJSON

# Create .env.local with API endpoint
cat << ENVFILE > .env.local
NEXT_PUBLIC_API_ENDPOINT=$RAG_API_URL
ENVFILE

echo "=== Installing dependencies ==="
npm install

echo "=== App files will be synced via rsync ==="
# Placeholder - actual app will be synced after instance is up

echo "=== Configuring Nginx ==="
cat << NGINXCONF > /etc/nginx/sites-available/ominis-frontend
server {
    listen 80;
    server_name ia.ominis.org;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \\\$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \\\$host;
        proxy_set_header X-Real-IP \\\$remote_addr;
        proxy_set_header X-Forwarded-For \\\$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \\\$scheme;
        proxy_cache_bypass \\\$http_upgrade;
    }
}
NGINXCONF

ln -sf /etc/nginx/sites-available/ominis-frontend /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== Installing Certbot for SSL ==="
apt-get install -y certbot python3-certbot-nginx

echo "=== Setup complete ==="
echo "Next steps:"
echo "1. Point DNS to this server"
echo "2. Run: certbot --nginx -d $DOMAIN_NAME"
echo "3. Sync frontend code and run: pm2 start npm --name ominis-frontend -- start"
USERDATA
)

# Check if instance already exists
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo ""
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID="$EXISTING_INSTANCE"
else
    echo ""
    echo "Launching EC2 instance..."
    
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health},{Key=Domain,Value=$DOMAIN_NAME}]" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$AWS_REGION")
    
    echo "  ✓ Instance launched: $INSTANCE_ID"
fi

# Wait for instance to be running
echo ""
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
echo "  ✓ Instance is running"

# Allocate Elastic IP for stable DNS
echo ""
echo "Setting up Elastic IP..."
EXISTING_EIP=$(aws ec2 describe-addresses \
    --filters "Name=tag:Name,Values=ominis-frontend-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-frontend-eip},{Key=Project,Value=ominis-health}]" \
        --query 'AllocationId' \
        --output text \
        --region "$AWS_REGION")
    echo "  ✓ Elastic IP allocated: $ALLOCATION_ID"
else
    ALLOCATION_ID="$EXISTING_EIP"
    echo "  ✓ Elastic IP exists: $ALLOCATION_ID"
fi

# Associate Elastic IP with instance
aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOCATION_ID" \
    --region "$AWS_REGION" 2>/dev/null || true

# Get the Elastic IP address
ELASTIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$AWS_REGION")

echo "  ✓ Elastic IP associated: $ELASTIC_IP"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            Frontend Server Deployed in Mexico                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Elastic IP:    $ELASTIC_IP"
echo "Domain:        $DOMAIN_NAME"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                      NEXT STEPS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Configure DNS (Route53 or your DNS provider):"
echo "   ┌─────────────────────────────────────────────────────────┐"
echo "   │  Type: A                                                │"
echo "   │  Name: ia.ominis.org                                    │"
echo "   │  Value: $ELASTIC_IP                                     │"
echo "   │  TTL: 300                                               │"
echo "   └─────────────────────────────────────────────────────────┘"
echo ""
echo "2. Wait for instance setup (~3 min), then sync frontend code:"
echo "   ./infrastructure/12-sync-frontend.sh"
echo ""
echo "3. SSH into server and enable SSL:"
echo "   ssh -i config/${KEY_NAME}.pem ubuntu@$ELASTIC_IP"
echo "   sudo certbot --nginx -d $DOMAIN_NAME"
echo ""
echo "SSH Access:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$ELASTIC_IP"
echo ""
echo "View setup logs:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$ELASTIC_IP 'tail -f /var/log/frontend-setup.log'"
echo ""

# Save configuration
cat << EOF > "$SCRIPT_DIR/../config/frontend_server.txt"
# Ominis Health - Frontend Server Configuration
FRONTEND_INSTANCE_ID=$INSTANCE_ID
FRONTEND_ELASTIC_IP=$ELASTIC_IP
FRONTEND_DOMAIN=$DOMAIN_NAME
FRONTEND_URL=https://$DOMAIN_NAME
EOF

echo "Configuration saved to config/frontend_server.txt"
