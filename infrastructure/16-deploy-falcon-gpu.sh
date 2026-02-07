#!/bin/bash
# =============================================================================
# Deploy Falcon-40B-Instruct on a new GPU EC2 instance (us-east-1)
#
# Instance: g5.2xlarge (1x A10G GPU, 24GB VRAM, 8 vCPU, 32GB RAM)
# The A10G has enough VRAM for Falcon-40B quantized (Q4_K_M ~22GB)
#
# Architecture:
#   - Existing g4dn.xlarge (T4 16GB) → ominis-2.0 (BioMistral-7B)
#   - New g5.2xlarge (A10G 24GB)     → falcon-40b-instruct
#   - Haystack backend routes to the right server based on model selection
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# --- Configuration ---
US_REGION="us-east-1"
INSTANCE_TYPE="g5.2xlarge"       # 1x A10G GPU (24GB VRAM), 8 vCPU, 32GB RAM
INSTANCE_NAME="ominis-falcon-gpu"
KEY_NAME="ominis-falcon-gpu-key"
SECURITY_GROUP_NAME="ominis-falcon-gpu-sg"
VOLUME_SIZE=150                  # GB - Falcon-40B GGUF is ~23GB + OS

# Ubuntu 22.04 LTS (will install NVIDIA drivers + Ollama)
AMI_ID="ami-0c7217cdde317cfec"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploying Falcon-40B-Instruct GPU Server (us-east-1)       ║"
echo "║   Instance: g5.2xlarge (NVIDIA A10G, 24GB VRAM)              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE"
echo "GPU:           NVIDIA A10G (24GB VRAM)"
echo "Region:        $US_REGION"
echo "Volume:        ${VOLUME_SIZE}GB gp3"
echo ""

# --- Key Pair ---
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$US_REGION" &>/dev/null; then
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

# --- Security Group ---
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[0].GroupId' \
    --output text \
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "Falcon-40B GPU Server for Ominis Health" \
        --query 'GroupId' \
        --output text \
        --region "$US_REGION")

    # SSH
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp --port 22 --cidr 0.0.0.0/0 \
        --region "$US_REGION"

    # Ollama API (11434) - restricted in production; open for setup
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp --port 11434 --cidr 0.0.0.0/0 \
        --region "$US_REGION"

    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# --- User Data (installs NVIDIA drivers, Ollama, pulls Falcon-40B) ---
USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e
exec > /var/log/falcon-gpu-setup.log 2>&1

echo "=== $(date) Starting Falcon-40B GPU setup ==="

echo "=== Updating system ==="
apt-get update && apt-get upgrade -y

echo "=== Installing NVIDIA drivers ==="
apt-get install -y linux-headers-$(uname -r)
apt-get install -y nvidia-driver-535 nvidia-utils-535

echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

# Configure Ollama for external access and GPU
mkdir -p /etc/systemd/system/ollama.service.d
cat << EOF > /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
EOF
systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

# Wait for Ollama to start
echo "=== Waiting for Ollama to start ==="
sleep 30

# Verify Ollama is running
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    echo "Waiting for Ollama..."
    sleep 5
done
echo "Ollama is running."

echo "=== Pulling Falcon-40B-Instruct (this will take 15-30 minutes) ==="
ollama pull falcon:40b-instruct

echo "=== Creating custom Falcon model with Ominis system prompt ==="
cat << 'MODELFILE' > /tmp/Modelfile.falcon
FROM falcon:40b-instruct

PARAMETER temperature 0.3
PARAMETER num_predict 1024
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.1
PARAMETER num_gpu 99
PARAMETER stop "User:"
PARAMETER stop "\nUser:"
PARAMETER stop "\nUsuario:"

SYSTEM """Eres OMINIS, el asistente de investigación en salud de la Fundación Mexicana para la Salud (FUNSALUD). Tu misión es ayudar a investigadores y profesionales de la salud con información precisa y basada en evidencia. Responde siempre en español mexicano. Cita las fuentes que uses por número [1], [2], etc. No proporciones diagnósticos médicos."""
MODELFILE

ollama create falcon-40b-instruct -f /tmp/Modelfile.falcon

echo "=== Verifying GPU ==="
nvidia-smi

echo "=== Verifying models ==="
ollama list

echo "=== $(date) Setup complete! ==="
USERDATA
)

# --- Check for existing instance ---
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo ""
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID="$EXISTING_INSTANCE"

    # Start if stopped
    STATE=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text \
        --region "$US_REGION")
    if [ "$STATE" = "stopped" ]; then
        echo "  Instance is stopped. Starting..."
        aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$US_REGION"
        aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$US_REGION"
        echo "  ✓ Instance started"
    fi
else
    echo ""
    echo "Launching g5.2xlarge GPU instance..."

    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health},{Key=Purpose,Value=falcon-40b-gpu}]" \
        --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$VOLUME_SIZE,\"VolumeType\":\"gp3\"}}]" \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$US_REGION")

    echo "  ✓ Instance launched: $INSTANCE_ID"
fi

# --- Wait for running ---
echo ""
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$US_REGION"
echo "  ✓ Instance is running"

# --- Elastic IP ---
echo ""
echo "Setting up Elastic IP..."
EXISTING_EIP=$(aws ec2 describe-addresses \
    --filters "Name=tag:Name,Values=ominis-falcon-gpu-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$US_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-falcon-gpu-eip},{Key=Project,Value=ominis-health}]" \
        --query 'AllocationId' \
        --output text \
        --region "$US_REGION")
    echo "  ✓ Elastic IP allocated: $ALLOCATION_ID"
else
    ALLOCATION_ID="$EXISTING_EIP"
    echo "  ✓ Elastic IP exists: $ALLOCATION_ID"
fi

aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOCATION_ID" \
    --region "$US_REGION" 2>/dev/null || true

FALCON_ELASTIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$US_REGION")

echo "  ✓ Elastic IP: $FALCON_ELASTIC_IP"

# --- Save config ---
cat << EOF > "$SCRIPT_DIR/../config/falcon_gpu_server.txt"
# Ominis Health - Falcon-40B GPU Server (us-east-1)
FALCON_INSTANCE_ID=$INSTANCE_ID
FALCON_INSTANCE_TYPE=$INSTANCE_TYPE
FALCON_ELASTIC_IP=$FALCON_ELASTIC_IP
FALCON_REGION=$US_REGION
FALCON_OLLAMA_URL=http://$FALCON_ELASTIC_IP:11434
FALCON_MODEL=falcon-40b-instruct
EOF

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        Falcon-40B GPU Server Deployed                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Instance Type: $INSTANCE_TYPE (NVIDIA A10G, 24GB VRAM)"
echo "Elastic IP:    $FALCON_ELASTIC_IP"
echo "Ollama API:    http://$FALCON_ELASTIC_IP:11434"
echo "Region:        $US_REGION"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                      NEXT STEPS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Wait ~30 min for drivers + model download (~23GB GGUF)"
echo ""
echo "2. Monitor setup progress:"
echo "   ssh -i config/${KEY_NAME}.pem ubuntu@$FALCON_ELASTIC_IP 'tail -f /var/log/falcon-gpu-setup.log'"
echo ""
echo "3. Verify GPU:"
echo "   ssh -i config/${KEY_NAME}.pem ubuntu@$FALCON_ELASTIC_IP 'nvidia-smi'"
echo ""
echo "4. Test Falcon model:"
echo "   curl http://$FALCON_ELASTIC_IP:11434/api/generate -d '{"
echo "     \"model\": \"falcon-40b-instruct\","
echo "     \"prompt\": \"¿Qué es la diabetes?\","
echo "     \"stream\": false"
echo "   }'"
echo ""
echo "5. Update Haystack backend config:"
echo "   Set FALCON_OLLAMA_URL=http://$FALCON_ELASTIC_IP:11434 in .env"
echo ""
echo "SSH Access:"
echo "  ssh -i config/${KEY_NAME}.pem ubuntu@$FALCON_ELASTIC_IP"
echo ""
echo "Configuration saved to config/falcon_gpu_server.txt"
echo ""
echo "⚠️  COST: g5.2xlarge ≈ \$1.21/hour ≈ \$880/month"
echo "    Stop when not in use:"
echo "    aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $US_REGION"
