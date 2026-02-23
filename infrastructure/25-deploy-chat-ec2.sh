#!/bin/bash
# Create EC2 for chat.ominis.org (LibreChat, Ominis look & feel, Haystack backend)
# Minimal instance: t3.small, Docker + LibreChat
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

INSTANCE_TYPE="t3.small"
INSTANCE_NAME="ominis-chat-server"
KEY_NAME="ominis-chat-key"
SECURITY_GROUP_NAME="ominis-chat-sg"
DOMAIN_NAME="chat.ominis.org"
AMI_ID="ami-0a57f819c3fccde4f"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    Deploying Chat Server (chat.ominis.org) in mx-central-1   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE"
echo "Domain:        $DOMAIN_NAME"
echo ""

# Key pair
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

# Security group
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[0].GroupId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "Chat server for Ominis (chat.ominis.org)" \
        --query 'GroupId' \
        --output text \
        --region "$AWS_REGION")
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22   --cidr 0.0.0.0/0 --region "$AWS_REGION"
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80   --cidr 0.0.0.0/0 --region "$AWS_REGION"
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 443  --cidr 0.0.0.0/0 --region "$AWS_REGION"
    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# User data: Docker + Docker Compose + app dir
USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e
exec > /var/log/chat-setup.log 2>&1
echo "=== Updating system ==="
apt-get update && apt-get upgrade -y
echo "=== Installing Docker ==="
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu
echo "=== Creating app directory ==="
mkdir -p /opt/librechat-ominis/uploads /opt/librechat-ominis/logs
chown -R ubuntu:ubuntu /opt/librechat-ominis
echo "=== Installing Nginx ==="
apt-get install -y nginx
echo "=== Installing Certbot ==="
apt-get install -y certbot python3-certbot-nginx
echo "=== Setup complete ==="
USERDATA
)

# Launch or reuse instance
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID="$EXISTING_INSTANCE"
else
    echo "Launching EC2 instance..."
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis},{Key=Domain,Value=$DOMAIN_NAME}]" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$AWS_REGION")
    echo "  ✓ Instance launched: $INSTANCE_ID"
fi

echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"
echo "  ✓ Instance is running"

# Elastic IP
EXISTING_EIP=$(aws ec2 describe-addresses \
    --filters "Name=tag:Name,Values=ominis-chat-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-chat-eip},{Key=Project,Value=ominis}]" \
        --query 'AllocationId' \
        --output text \
        --region "$AWS_REGION")
else
    ALLOCATION_ID="$EXISTING_EIP"
fi

aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOCATION_ID" \
    --region "$AWS_REGION" 2>/dev/null || true

ELASTIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$AWS_REGION")

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            Chat EC2 created                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Instance ID:   $INSTANCE_ID"
echo "Elastic IP:    $ELASTIC_IP"
echo "Domain:        $DOMAIN_NAME"
echo ""
echo "Next steps:"
echo "1. Add CORS origin https://chat.ominis.org to backend (ALLOWED_ORIGINS)"
echo "2. Generate CREDS_KEY/CREDS_IV: https://librechat.ai/toolkit/creds_generator"
echo "3. Copy infrastructure/librechat-chat/.env.example to .env and set CREDS_KEY, CREDS_IV"
echo "4. Run: ./infrastructure/26-sync-chat-librechat.sh"
echo "5. DNS A record: chat.ominis.org -> $ELASTIC_IP"
echo "6. SSH and SSL: ssh -i config/${KEY_NAME}.pem ubuntu@$ELASTIC_IP ; sudo certbot --nginx -d $DOMAIN_NAME"
echo ""

cat << EOF > "$SCRIPT_DIR/../config/chat_server.txt"
# Ominis Chat (chat.ominis.org)
CHAT_INSTANCE_ID=$INSTANCE_ID
CHAT_ELASTIC_IP=$ELASTIC_IP
CHAT_DOMAIN=$DOMAIN_NAME
CHAT_URL=https://$DOMAIN_NAME
CHAT_KEY_NAME=$KEY_NAME
EOF
echo "Configuration saved to config/chat_server.txt"
