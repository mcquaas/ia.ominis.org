#!/bin/bash
# Deploy Strapi Backend to EC2
# This script deploys the Ominis Admin Backend (Strapi V5)

set -e

# Load settings
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# Default configuration
REGION="${AWS_REGION:-mx-central-1}"
INSTANCE_TYPE="${STRAPI_INSTANCE_TYPE:-t3.medium}"
KEY_NAME="${AWS_KEY_NAME:-ominis-key}"
AMI_ID="${AMI_ID:-ami-0c55b159cbfafe1f0}"  # Amazon Linux 2023

echo "==================================="
echo "  Ominis Strapi Backend Deployment"
echo "==================================="
echo ""
echo "Region: $REGION"
echo "Instance Type: $INSTANCE_TYPE"
echo ""

# Check if instance already exists
EXISTING_INSTANCE=$(aws ec2 describe-instances \
  --region "$REGION" \
  --filters "Name=tag:Name,Values=ominis-strapi" "Name=instance-state-name,Values=running,pending" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
  echo "Strapi instance already exists: $EXISTING_INSTANCE"
  PUBLIC_IP=$(aws ec2 describe-instances \
    --region "$REGION" \
    --instance-ids "$EXISTING_INSTANCE" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)
  echo "Public IP: $PUBLIC_IP"
  echo "Admin Panel: http://$PUBLIC_IP:1337/admin"
  exit 0
fi

# Create security group if needed
SG_NAME="ominis-strapi-sg"
SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || echo "None")

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
  echo "Creating security group..."
  SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$SG_NAME" \
    --description "Security group for Ominis Strapi backend" \
    --query 'GroupId' \
    --output text)
  
  # Allow SSH (22), HTTP (80), HTTPS (443), Strapi (1337)
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp --port 22 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp --port 80 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp --port 1337 --cidr 0.0.0.0/0
  
  echo "Security group created: $SG_ID"
fi

# User data script for instance initialization
USER_DATA=$(cat <<'EOF'
#!/bin/bash
set -e

# Install dependencies
yum update -y
yum install -y git nodejs npm postgresql15

# Install Node.js 22 via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.nvm/nvm.sh
nvm install 22
nvm use 22
nvm alias default 22

# Create app directory
mkdir -p /opt/ominis-admin
cd /opt/ominis-admin

# Clone or download the backend code
# git clone https://github.com/your-org/ominis-backend.git .
# OR sync from S3:
# aws s3 sync s3://ominis-health-models-mx/backend/ .

# Install dependencies
npm install --production

# Create systemd service
cat > /etc/systemd/system/strapi.service << 'SERVICEEOF'
[Unit]
Description=Strapi Admin Backend
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/ominis-admin
ExecStart=/usr/bin/npm run start
Restart=always
RestartSec=10
Environment=NODE_ENV=production
EnvironmentFile=/opt/ominis-admin/.env

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Enable and start service
systemctl daemon-reload
systemctl enable strapi
# Don't start yet - need to configure .env first
# systemctl start strapi

echo "Strapi setup complete. Configure .env and run: sudo systemctl start strapi"
EOF
)

# Launch instance
echo "Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --user-data "$USER_DATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=ominis-strapi},{Key=Project,Value=ominis-health}]" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "Instance launched: $INSTANCE_ID"
echo "Waiting for instance to be running..."

aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo ""
echo "==================================="
echo "  Deployment Complete!"
echo "==================================="
echo ""
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo ""
echo "Next steps:"
echo "1. SSH into the instance: ssh -i $KEY_NAME.pem ec2-user@$PUBLIC_IP"
echo "2. Copy the backend code to /opt/ominis-admin"
echo "3. Create .env file with secrets"
echo "4. Run: npm run build && sudo systemctl start strapi"
echo "5. Access admin panel: http://$PUBLIC_IP:1337/admin"
echo ""
echo "Save server info:"
echo "$PUBLIC_IP" > "$SCRIPT_DIR/../config/strapi_server.txt"
