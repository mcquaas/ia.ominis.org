#!/bin/bash
# Deploy Ollama LLM Server on EC2 in Mexico (mx-central-1)
# This keeps ALL data and inference in Mexico - no cross-region calls
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

# EC2 Configuration
INSTANCE_TYPE="c6i.4xlarge"  # 16 vCPU, 32GB RAM - good for 7B models on CPU
INSTANCE_NAME="ominis-ollama-server"
KEY_NAME="ominis-ollama-key"
SECURITY_GROUP_NAME="ominis-ollama-sg"

# Use standard Ubuntu 24.04 AMI (will install Ollama via user-data)
AMI_ID="ami-0a57f819c3fccde4f"  # Ubuntu 24.04 LTS

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      Deploying Ollama LLM Server in Mexico (mx-central-1)     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE"
echo "AMI: $AMI_ID (Ubuntu 24.04 + Ollama install)"
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
        --description "Ollama LLM Server for Ominis Health" \
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
    
    # Allow Ollama API (port 11434)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 11434 \
        --cidr 0.0.0.0/0 \
        --region "$AWS_REGION"
    
    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# User data script to install and configure Ollama
USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e
exec > /var/log/ollama-setup.log 2>&1

echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

# Configure Ollama to listen on all interfaces
mkdir -p /etc/systemd/system/ollama.service.d
cat << EOF > /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
EOF
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

# Wait for Ollama to start
sleep 15

echo "=== Creating Ominis-2.0 model ==="
# Create custom Ominis-2.0 model based on medical LLM
cat << 'MODELFILE' > /tmp/Modelfile
FROM cniongolo/biomistral

PARAMETER temperature 0.3
PARAMETER num_predict 1024

SYSTEM """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD.
Tu objetivo es proporcionar información de salud precisa y útil basada en fuentes confiables.
Siempre responde en español y recomienda consultar a un profesional médico cuando sea apropiado."""
MODELFILE

ollama create ominis-2.0 -f /tmp/Modelfile

echo "=== Pulling Mistral (fallback) ==="
ollama pull mistral:7b-instruct-q4_K_M

echo "=== Setup complete! ==="
ollama list
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
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health}]" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
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

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text \
    --region "$AWS_REGION")

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║               Ollama Server Deployed in Mexico                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:  $INSTANCE_ID"
echo "Public IP:    $PUBLIC_IP"
echo "Ollama API:   http://$PUBLIC_IP:11434"
echo ""
echo "SSH Access:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
echo ""
echo "Test Ollama (wait ~5 min for model download):"
echo "  curl http://$PUBLIC_IP:11434/api/tags"
echo ""
echo "Query the Ominis-2.0 model:"
echo "  curl http://$PUBLIC_IP:11434/api/generate -d '{"
echo "    \"model\": \"ominis-2.0\","
echo "    \"prompt\": \"¿Qué es la diabetes?\","
echo "    \"stream\": false"
echo "  }'"
echo ""

# Save configuration
cat << EOF > "$SCRIPT_DIR/../config/ollama_server.txt"
OLLAMA_INSTANCE_ID=$INSTANCE_ID
OLLAMA_PUBLIC_IP=$PUBLIC_IP
OLLAMA_API_URL=http://$PUBLIC_IP:11434
EOF

echo "Configuration saved to config/ollama_server.txt"
