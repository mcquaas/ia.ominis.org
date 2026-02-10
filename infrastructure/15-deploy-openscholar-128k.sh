#!/bin/bash
# =============================================================================
# OMINIS Health - OpenScholar 128K (long-context) GPU Deployment
# =============================================================================
# Deploys the same OpenScholar model with --max-model-len 32768 for long-context
# research reports. Same architecture as 14-deploy-openscholar.sh but separate
# instance; start/stop from dashboard. Auto-stops after 60 min when started from UI.
#
# Backend .env must set after deploy:
#   OPENSCHOLAR_128K_API_URL=http://<ELASTIC_IP>:8000
#   OPENSCHOLAR_128K_INSTANCE_ID=<instance id from this script>
# =============================================================================

set -e

REGION="us-east-1"
INSTANCE_TYPE="g5.2xlarge"
KEY_NAME="ominis-openscholar-key"
SECURITY_GROUP_NAME="ominis-openscholar-128k-sg"
INSTANCE_NAME="ominis-openscholar-128k"

MODEL_NAME="OpenSciLM/Llama-3.1_OpenScholar-8B"
HAYSTACK_BACKEND_IP="78.12.33.205"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== OMINIS OpenScholar 128K Deployment ===${NC}"
echo "Region: $REGION"
echo "Instance Type: $INSTANCE_TYPE"
echo "Model: $MODEL_NAME (max-model-len 32768)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
mkdir -p "$CONFIG_DIR"

# Reuse key from 8K deploy if present
KEY_FILE="$CONFIG_DIR/${KEY_NAME}.pem"
if [ ! -f "$KEY_FILE" ]; then
    echo "Creating key pair..."
    aws ec2 create-key-pair --region $REGION --key-name $KEY_NAME --query 'KeyMaterial' --output text > "$KEY_FILE"
    chmod 400 "$KEY_FILE"
fi

# Security group for 128k instance
VPC_ID=$(aws ec2 describe-vpcs --region $REGION --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups --region $REGION --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group --region $REGION --group-name $SECURITY_GROUP_NAME --description "OpenScholar 128K LLM - restricted" --vpc-id $VPC_ID --query 'GroupId' --output text)
    MY_IP=$(curl -s ifconfig.me)
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID --protocol tcp --port 22 --cidr ${MY_IP}/32 2>/dev/null || true
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID --protocol tcp --port 8000 --cidr ${HAYSTACK_BACKEND_IP}/32 2>/dev/null || true
fi

AMI_ID=$(aws ec2 describe-images --region $REGION --owners amazon --filters "Name=name,Values=Deep Learning AMI (Ubuntu 22.04)*" "Name=state,Values=available" --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' --output text)
[ -z "$AMI_ID" ] || [ "$AMI_ID" == "None" ] && AMI_ID=$(aws ec2 describe-images --region $REGION --owners 099720109477 --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" "Name=state,Values=available" --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' --output text)

USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e
exec > >(tee /var/log/openscholar-128k-setup.log) 2>&1
echo "Starting OpenScholar 128K setup at $(date)"
apt-get update
apt-get install -y docker.io nvidia-container-toolkit jq
systemctl enable docker && systemctl start docker
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
for i in {1..30}; do
  nvidia-smi &>/dev/null && break
  sleep 10
done
mkdir -p /opt/openscholar-128k /root/.cache/huggingface
cat > /opt/openscholar-128k/docker-compose.yml << 'COMPOSE'
version: '3.8'
services:
  openscholar:
    image: vllm/vllm-openai:latest
    container_name: openscholar-128k-llm
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
      --max-model-len 32768
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
cat > /etc/systemd/system/openscholar-128k.service << 'SVC'
[Unit]
Description=OpenScholar 128K LLM Service
After=docker.service
Requires=docker.service
[Service]
Type=simple
WorkingDirectory=/opt/openscholar-128k
ExecStartPre=/usr/bin/docker compose pull
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable openscholar-128k
docker pull vllm/vllm-openai:latest
systemctl start openscholar-128k
for i in {1..60}; do
  curl -s http://localhost:8000/v1/models | grep -q openscholar && break
  sleep 30
done
echo "OpenScholar 128K setup complete at $(date)"
USERDATA
)

EXISTING_INSTANCE=$(aws ec2 describe-instances --region $REGION --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    INSTANCE_ID=$EXISTING_INSTANCE
else
    INSTANCE_ID=$(aws ec2 run-instances --region $REGION --image-id $AMI_ID --instance-type $INSTANCE_TYPE --key-name $KEY_NAME --security-group-ids $SG_ID --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' --user-data "$USER_DATA" --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis},{Key=Service,Value=openscholar-128k}]" --query 'Instances[0].InstanceId' --output text)
fi

aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID

EIP_ALLOC=$(aws ec2 describe-addresses --region $REGION --filters "Name=instance-id,Values=$INSTANCE_ID" --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo "None")
if [ "$EIP_ALLOC" == "None" ] || [ -z "$EIP_ALLOC" ]; then
    EIP_ALLOC=$(aws ec2 allocate-address --region $REGION --domain vpc --query 'AllocationId' --output text)
    aws ec2 associate-address --region $REGION --instance-id $INSTANCE_ID --allocation-id $EIP_ALLOC
fi
ELASTIC_IP=$(aws ec2 describe-addresses --region $REGION --allocation-ids $EIP_ALLOC --query 'Addresses[0].PublicIp' --output text)

cat > "$CONFIG_DIR/openscholar_128k_server.txt" << EOF
# OMINIS Health - OpenScholar 128K Server
OPENSCHOLAR_128K_INSTANCE_ID=$INSTANCE_ID
OPENSCHOLAR_128K_ELASTIC_IP=$ELASTIC_IP
OPENSCHOLAR_128K_API_URL=http://$ELASTIC_IP:8000
EOF

echo ""
echo -e "${GREEN}=== OpenScholar 128K Deployment Complete ===${NC}"
echo "Instance ID:    $INSTANCE_ID"
echo "Elastic IP:     $ELASTIC_IP"
echo "API URL:        http://$ELASTIC_IP:8000"
echo ""
echo -e "${YELLOW}Next: update backend .env so the dashboard switch works:${NC}"
echo "  ./infrastructure/20a-update-backend-env-128k.sh"
echo ""
echo "Then sync code and restart backend/frontend if needed:"
echo "  ./infrastructure/20-sync-backend.sh"
echo "  ./infrastructure/12-sync-frontend.sh"
echo ""
echo -e "${RED}Instance is running. Stop when not needed to save cost:${NC}"
echo "  aws ec2 stop-instances --region $REGION --instance-ids $INSTANCE_ID"
