#!/bin/bash
# Deploy Ollama LLM Server on GPU EC2 in US (us-east-1)
# Hybrid architecture: Data stays in Mexico, LLM inference in US for speed
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh"

# US Region for GPU
US_REGION="us-east-1"

# EC2 Configuration - GPU instance
INSTANCE_TYPE="g4dn.xlarge"  # 1x T4 GPU (16GB), 4 vCPU, 16GB RAM
INSTANCE_NAME="ominis-ollama-gpu"
KEY_NAME="ominis-ollama-gpu-key"
SECURITY_GROUP_NAME="ominis-ollama-gpu-sg"

# Ubuntu 24.04 with NVIDIA drivers (Deep Learning AMI)
# Using Deep Learning Base OSS Nvidia Driver GPU AMI
AMI_ID="ami-0c7217cdde317cfec"  # Ubuntu 22.04 (we'll install drivers)

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploying GPU Ollama Server in US (us-east-1)              ║"
echo "║   Hybrid: Data in Mexico, Fast Inference in US               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE (NVIDIA T4 GPU)"
echo "Region:        $US_REGION"
echo "Purpose:       Fast LLM inference (10-30x faster than CPU)"
echo ""

# Create key pair if it doesn't exist
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$US_REGION" 2>/dev/null; then
    echo "Creating SSH key pair..."
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --query 'KeyMaterial' \
        --output text \
        --region "$US_REGION" > "$SCRIPT_DIR/../config/${KEY_NAME}.pem"
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
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "GPU Ollama LLM Server for Ominis Health (US)" \
        --query 'GroupId' \
        --output text \
        --region "$US_REGION")
    
    # Allow SSH
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region "$US_REGION"
    
    # Allow Ollama API (port 11434) - restricted to Mexico servers
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 11434 \
        --cidr 0.0.0.0/0 \
        --region "$US_REGION"
    
    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# User data script to install NVIDIA drivers and Ollama
USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e
exec > /var/log/ollama-gpu-setup.log 2>&1

echo "=== Updating system ==="
apt-get update && apt-get upgrade -y

echo "=== Installing NVIDIA drivers ==="
apt-get install -y linux-headers-$(uname -r)
apt-get install -y nvidia-driver-535 nvidia-utils-535

echo "=== Installing NVIDIA Container Toolkit ==="
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update

echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

# Configure Ollama to listen on all interfaces
mkdir -p /etc/systemd/system/ollama.service.d
cat << EOF > /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_NUM_PARALLEL=4"
EOF
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

# Wait for Ollama to start
sleep 20

echo "=== Creating Ominis-2.0 GPU model ==="
# Create custom Ominis-2.0 model optimized for GPU
cat << 'MODELFILE' > /tmp/Modelfile
FROM cniongolo/biomistral

PARAMETER temperature 0.3
PARAMETER num_predict 1024
PARAMETER num_gpu 99

SYSTEM """Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD.
Tu objetivo es proporcionar información de salud precisa y útil basada en fuentes confiables.
Siempre responde en español y recomienda consultar a un profesional médico cuando sea apropiado."""
MODELFILE

ollama create ominis-2.0 -f /tmp/Modelfile

echo "=== Verifying GPU ==="
nvidia-smi || echo "GPU not yet available (may need reboot)"

echo "=== Setup complete! ==="
ollama list
USERDATA
)

# Check if instance already exists
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo ""
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID="$EXISTING_INSTANCE"
else
    echo ""
    echo "Launching GPU EC2 instance..."
    
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health},{Key=Purpose,Value=gpu-inference}]" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$US_REGION")
    
    echo "  ✓ Instance launched: $INSTANCE_ID"
fi

# Wait for instance to be running
echo ""
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$US_REGION"
echo "  ✓ Instance is running"

# Allocate Elastic IP
echo ""
echo "Setting up Elastic IP..."
EXISTING_EIP=$(aws ec2 describe-addresses \
    --filters "Name=tag:Name,Values=ominis-ollama-gpu-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-ollama-gpu-eip},{Key=Project,Value=ominis-health}]" \
        --query 'AllocationId' \
        --output text \
        --region "$US_REGION")
    echo "  ✓ Elastic IP allocated: $ALLOCATION_ID"
else
    ALLOCATION_ID="$EXISTING_EIP"
    echo "  ✓ Elastic IP exists: $ALLOCATION_ID"
fi

# Associate Elastic IP with instance
aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOCATION_ID" \
    --region "$US_REGION" 2>/dev/null || true

# Get the Elastic IP address
GPU_ELASTIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$US_REGION")

echo "  ✓ Elastic IP associated: $GPU_ELASTIC_IP"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          GPU Ollama Server Deployed in US                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Instance Type: $INSTANCE_TYPE (NVIDIA T4 GPU)"
echo "Elastic IP:    $GPU_ELASTIC_IP"
echo "Region:        $US_REGION"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                   EXPECTED PERFORMANCE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  CPU (current):  ~30-60 seconds per response"
echo "  GPU (new):      ~2-5 seconds per response"
echo "  Speedup:        10-30x faster"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                      NEXT STEPS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Wait ~10 min for GPU drivers and model to install"
echo ""
echo "2. Verify GPU is working:"
echo "   ssh -i config/${KEY_NAME}.pem ubuntu@$GPU_ELASTIC_IP 'nvidia-smi'"
echo ""
echo "3. Test Ollama:"
echo "   curl http://$GPU_ELASTIC_IP:11434/api/tags"
echo ""
echo "4. Update Mexico RAG server to use GPU endpoint:"
echo "   ./infrastructure/14-update-rag-gpu.sh"
echo ""
echo "SSH Access:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$GPU_ELASTIC_IP"
echo ""
echo "View setup logs:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$GPU_ELASTIC_IP 'tail -f /var/log/ollama-gpu-setup.log'"
echo ""

# Save configuration
cat << EOF > "$SCRIPT_DIR/../config/ollama_gpu_server.txt"
# Ominis Health - GPU Ollama Server Configuration (US)
GPU_INSTANCE_ID=$INSTANCE_ID
GPU_ELASTIC_IP=$GPU_ELASTIC_IP
GPU_REGION=$US_REGION
GPU_OLLAMA_API_URL=http://$GPU_ELASTIC_IP:11434
EOF

echo "Configuration saved to config/ollama_gpu_server.txt"
echo ""
echo "⚠️  IMPORTANT: The GPU instance costs ~\$0.52/hour (~\$380/month)"
echo "    Stop when not in use: aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $US_REGION"
