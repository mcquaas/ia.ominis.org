#!/bin/bash
# =============================================================================
# OMINIS Health - OpenScholar Academic LLM Deployment
# =============================================================================
# Deploys OpenScholar (Llama-3.1-8B fine-tuned for scientific literature)
# on a GPU EC2 instance using vLLM for OpenAI-compatible inference API.
#
# Architecture:
#   - EC2 g5.xlarge (A10G 24GB GPU) or g4dn.xlarge (T4 16GB GPU)
#   - vLLM serving OpenScholar model
#   - OpenAI-compatible API on port 8000
#   - Secured for internal access only (from Haystack backend)
#
# License: Apache 2.0 (OpenScholar is Apache 2.0 licensed)
# =============================================================================

set -e

# Configuration
REGION="us-east-1"  # GPU availability
INSTANCE_TYPE="g5.2xlarge"  # A10G 24GB GPU + 32GB RAM - required for 8B model in fp16
KEY_NAME="ominis-openscholar-key"
SECURITY_GROUP_NAME="ominis-openscholar-sg"
INSTANCE_NAME="ominis-openscholar"

# OpenScholar model
MODEL_NAME="OpenSciLM/Llama-3.1_OpenScholar-8B"
MODEL_ALIAS="openscholar"

# Haystack backend IP (will be allowed to connect)
HAYSTACK_BACKEND_IP="78.12.33.205"
# Old RAG API (for migration period)
OLD_RAG_IP="78.13.254.66"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== OMINIS OpenScholar Deployment ===${NC}"
echo "Region: $REGION"
echo "Instance Type: $INSTANCE_TYPE"
echo "Model: $MODEL_NAME"
echo ""

# Get config directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
mkdir -p "$CONFIG_DIR"

# Step 1: Create Key Pair
echo -e "${YELLOW}Step 1: Creating SSH key pair...${NC}"
KEY_FILE="$CONFIG_DIR/${KEY_NAME}.pem"

if [ -f "$KEY_FILE" ]; then
    echo "Key already exists: $KEY_FILE"
else
    aws ec2 create-key-pair \
        --region $REGION \
        --key-name $KEY_NAME \
        --query 'KeyMaterial' \
        --output text > "$KEY_FILE"
    chmod 400 "$KEY_FILE"
    echo "Created: $KEY_FILE"
fi

# Step 2: Create Security Group
echo -e "${YELLOW}Step 2: Creating security group...${NC}"

# Get default VPC
VPC_ID=$(aws ec2 describe-vpcs \
    --region $REGION \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text)

# Check if security group exists
SG_ID=$(aws ec2 describe-security-groups \
    --region $REGION \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --region $REGION \
        --group-name $SECURITY_GROUP_NAME \
        --description "OpenScholar LLM API access - restricted" \
        --vpc-id $VPC_ID \
        --query 'GroupId' \
        --output text)
    echo "Created security group: $SG_ID"
    
    # Get current IP for SSH access
    MY_IP=$(curl -s ifconfig.me)
    
    # Allow SSH from current IP only
    aws ec2 authorize-security-group-ingress \
        --region $REGION \
        --group-id $SG_ID \
        --protocol tcp \
        --port 22 \
        --cidr ${MY_IP}/32 2>/dev/null || true
    
    # Allow API access from Haystack backend only
    aws ec2 authorize-security-group-ingress \
        --region $REGION \
        --group-id $SG_ID \
        --protocol tcp \
        --port 8000 \
        --cidr ${HAYSTACK_BACKEND_IP}/32 2>/dev/null || true
    
    # Allow API access from old RAG server (migration period)
    aws ec2 authorize-security-group-ingress \
        --region $REGION \
        --group-id $SG_ID \
        --protocol tcp \
        --port 8000 \
        --cidr ${OLD_RAG_IP}/32 2>/dev/null || true
    
    echo "Security group configured for restricted access"
else
    echo "Security group exists: $SG_ID"
fi

# Step 3: Get AMI (Ubuntu 22.04 with Deep Learning)
echo -e "${YELLOW}Step 3: Finding Deep Learning AMI...${NC}"

# Use Deep Learning AMI for pre-installed CUDA
AMI_ID=$(aws ec2 describe-images \
    --region $REGION \
    --owners amazon \
    --filters \
        "Name=name,Values=Deep Learning AMI (Ubuntu 22.04)*" \
        "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text)

if [ -z "$AMI_ID" ] || [ "$AMI_ID" == "None" ]; then
    # Fallback to regular Ubuntu 22.04
    AMI_ID=$(aws ec2 describe-images \
        --region $REGION \
        --owners 099720109477 \
        --filters \
            "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
fi

echo "AMI: $AMI_ID"

# Step 4: Create User Data Script
echo -e "${YELLOW}Step 4: Preparing user data...${NC}"

USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e

# Log everything
exec > >(tee /var/log/openscholar-setup.log) 2>&1
echo "Starting OpenScholar setup at $(date)"

# Update system
apt-get update
apt-get install -y docker.io nvidia-container-toolkit jq

# Start Docker
systemctl enable docker
systemctl start docker

# Configure NVIDIA runtime for Docker
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# Wait for NVIDIA driver
for i in {1..30}; do
    if nvidia-smi &>/dev/null; then
        echo "NVIDIA driver ready"
        break
    fi
    echo "Waiting for NVIDIA driver... ($i/30)"
    sleep 10
done

# Create directories
mkdir -p /opt/openscholar
mkdir -p /root/.cache/huggingface

# Create docker-compose.yml for vLLM
cat > /opt/openscholar/docker-compose.yml << 'COMPOSE'
version: '3.8'
services:
  openscholar:
    image: vllm/vllm-openai:latest
    container_name: openscholar-llm
    runtime: nvidia
    ports:
      - "8000:8000"
    volumes:
      - /root/.cache/huggingface:/root/.cache/huggingface
    environment:
      - HF_TOKEN=${HF_TOKEN:-}
      - VLLM_ATTENTION_BACKEND=FLASHINFER
    command: >
      --model OpenSciLM/Llama-3.1_OpenScholar-8B
      --served-model-name openscholar
      --host 0.0.0.0
      --port 8000
      --max-model-len 8192
      --gpu-memory-utilization 0.9
      --trust-remote-code
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
COMPOSE

# Create systemd service
cat > /etc/systemd/system/openscholar.service << 'SERVICE'
[Unit]
Description=OpenScholar LLM Service
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/openscholar
ExecStartPre=/usr/bin/docker compose pull
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

# Enable and start service
systemctl daemon-reload
systemctl enable openscholar

# Pull the image (this takes time)
echo "Pulling vLLM Docker image..."
docker pull vllm/vllm-openai:latest

# Start the service
echo "Starting OpenScholar service..."
systemctl start openscholar

# Wait for model to load (can take 5-10 minutes first time)
echo "Waiting for model to load (this may take several minutes)..."
for i in {1..60}; do
    if curl -s http://localhost:8000/v1/models | grep -q openscholar; then
        echo "OpenScholar model loaded successfully!"
        break
    fi
    echo "Loading model... ($i/60)"
    sleep 30
done

# Create test script
cat > /opt/openscholar/test.sh << 'TESTSCRIPT'
#!/bin/bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openscholar",
    "messages": [
      {"role": "system", "content": "You are a scientific research assistant. Provide accurate, well-cited responses."},
      {"role": "user", "content": "What are the latest findings on CRISPR gene therapy for sickle cell disease?"}
    ],
    "max_tokens": 500,
    "temperature": 0.3
  }' | jq .
TESTSCRIPT
chmod +x /opt/openscholar/test.sh

echo "OpenScholar setup complete at $(date)"
echo "Test with: /opt/openscholar/test.sh"
USERDATA
)

# Step 5: Launch Instance
echo -e "${YELLOW}Step 5: Launching EC2 instance...${NC}"

# Check if instance already exists
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --region $REGION \
    --filters \
        "Name=tag:Name,Values=$INSTANCE_NAME" \
        "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID=$EXISTING_INSTANCE
else
    INSTANCE_ID=$(aws ec2 run-instances \
        --region $REGION \
        --image-id $AMI_ID \
        --instance-type $INSTANCE_TYPE \
        --key-name $KEY_NAME \
        --security-group-ids $SG_ID \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis},{Key=Service,Value=openscholar}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    echo "Launched instance: $INSTANCE_ID"
fi

# Step 6: Wait for instance
echo -e "${YELLOW}Step 6: Waiting for instance to be running...${NC}"
aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
echo "Instance is running"

# Step 7: Allocate and associate Elastic IP
echo -e "${YELLOW}Step 7: Setting up Elastic IP...${NC}"

# Check if instance already has an EIP
CURRENT_EIP=$(aws ec2 describe-instances \
    --region $REGION \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

# Check if it's an EIP or just a public IP
EIP_ALLOC=$(aws ec2 describe-addresses \
    --region $REGION \
    --filters "Name=instance-id,Values=$INSTANCE_ID" \
    --query 'Addresses[0].AllocationId' \
    --output text 2>/dev/null || echo "None")

if [ "$EIP_ALLOC" == "None" ] || [ -z "$EIP_ALLOC" ]; then
    # Allocate new EIP
    EIP_ALLOC=$(aws ec2 allocate-address \
        --region $REGION \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$INSTANCE_NAME-eip},{Key=Project,Value=ominis}]" \
        --query 'AllocationId' \
        --output text)
    
    # Associate EIP
    aws ec2 associate-address \
        --region $REGION \
        --instance-id $INSTANCE_ID \
        --allocation-id $EIP_ALLOC
    
    echo "Allocated and associated Elastic IP"
fi

# Get the public IP
ELASTIC_IP=$(aws ec2 describe-addresses \
    --region $REGION \
    --allocation-ids $EIP_ALLOC \
    --query 'Addresses[0].PublicIp' \
    --output text)

echo "Elastic IP: $ELASTIC_IP"

# Step 8: Save configuration
echo -e "${YELLOW}Step 8: Saving configuration...${NC}"

cat > "$CONFIG_DIR/openscholar_server.txt" << EOF
# OMINIS Health - OpenScholar Server Configuration
OPENSCHOLAR_INSTANCE_ID=$INSTANCE_ID
OPENSCHOLAR_ELASTIC_IP=$ELASTIC_IP
OPENSCHOLAR_REGION=$REGION
OPENSCHOLAR_MODEL=$MODEL_NAME
OPENSCHOLAR_API_URL=http://$ELASTIC_IP:8000
OPENSCHOLAR_ENDPOINT=http://$ELASTIC_IP:8000/v1/chat/completions
EOF

echo "Configuration saved to: $CONFIG_DIR/openscholar_server.txt"

# Step 9: Print summary
echo ""
echo -e "${GREEN}=== OpenScholar Deployment Complete ===${NC}"
echo ""
echo "Instance ID:    $INSTANCE_ID"
echo "Elastic IP:     $ELASTIC_IP"
echo "API URL:        http://$ELASTIC_IP:8000"
echo "Model:          $MODEL_NAME (alias: openscholar)"
echo ""
echo -e "${YELLOW}SSH Access:${NC}"
echo "ssh -i $KEY_FILE ubuntu@$ELASTIC_IP"
echo ""
echo -e "${YELLOW}Test API (from allowed IPs):${NC}"
echo "curl http://$ELASTIC_IP:8000/v1/models"
echo ""
echo -e "${YELLOW}Notes:${NC}"
echo "- Model download takes 5-15 minutes on first start"
echo "- Check status: ssh ubuntu@$ELASTIC_IP 'sudo journalctl -u openscholar -f'"
echo "- API is OpenAI-compatible (use model name 'openscholar')"
echo "- Access restricted to Haystack backend ($HAYSTACK_BACKEND_IP)"
echo ""
echo -e "${RED}Cost Warning:${NC}"
echo "g5.2xlarge costs ~\$1.60/hour (~\$1,150/month)"
echo "Consider stopping when not in use:"
echo "aws ec2 stop-instances --region $REGION --instance-ids $INSTANCE_ID"
