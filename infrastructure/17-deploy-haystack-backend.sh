#!/bin/bash
# =============================================================================
# Deploy Haystack Backend (FastAPI + Haystack) on EC2
#
# Replaces the Strapi Node.js backend with the new Python backend.
# Instance: t3.large (2 vCPU, 8GB RAM) - enough for FastAPI + sentence-transformers
#
# This instance does NOT run LLM inference - it connects to:
#   - Ollama on g4dn.xlarge (ominis-2.0 / BioMistral)
#   - Ollama on g5.2xlarge  (falcon-40b-instruct)
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# --- Configuration ---
REGION="${AWS_REGION:-mx-central-1}"
INSTANCE_TYPE="t3.large"          # 2 vCPU, 8GB RAM - enough for FastAPI + embeddings
INSTANCE_NAME="ominis-haystack-backend"
KEY_NAME="${AWS_KEY_NAME:-ominis-ollama-key}"
SECURITY_GROUP_NAME="ominis-haystack-sg"
VOLUME_SIZE=50                    # GB

# Ubuntu 24.04 LTS
AMI_ID="ami-0a57f819c3fccde4f"

# Source GPU server configs if available
source "$SCRIPT_DIR/../config/ollama_gpu_server.txt" 2>/dev/null || true
source "$SCRIPT_DIR/../config/falcon_gpu_server.txt" 2>/dev/null || true

# GPU server IPs
GPU_OLLAMA_IP="${GPU_ELASTIC_IP:-3.213.91.241}"
FALCON_OLLAMA_IP="${FALCON_ELASTIC_IP:-18.235.182.22}"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploying Haystack Backend (FastAPI + RAG)                 ║"
echo "║   Replaces Strapi - Python backend with full RBAC            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE (2 vCPU, 8GB RAM)"
echo "Region:        $REGION"
echo "Connects to:"
echo "  ominis-2.0 Ollama:  http://$GPU_OLLAMA_IP:11434"
if [ -n "$FALCON_OLLAMA_IP" ]; then
    echo "  falcon-40b Ollama:  http://$FALCON_OLLAMA_IP:11434"
else
    echo "  falcon-40b Ollama:  (not configured yet - run 16-deploy-falcon-gpu.sh first)"
fi
echo ""

# --- Security Group ---
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[0].GroupId' \
    --output text \
    --region "$REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "Haystack Backend for Ominis Health" \
        --query 'GroupId' \
        --output text \
        --region "$REGION")

    # SSH (22)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0 --region "$REGION"
    # HTTP (80) - for nginx reverse proxy
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 --region "$REGION"
    # HTTPS (443)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0 --region "$REGION"
    # FastAPI direct (8000) - for development/testing
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region "$REGION"
    # PostgreSQL (5432) - only from localhost
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 5432 --cidr 127.0.0.1/32 --region "$REGION"

    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# --- User Data ---
USER_DATA=$(cat << USERDATA
#!/bin/bash
set -e
exec > /var/log/haystack-setup.log 2>&1

echo "=== \$(date) Starting Haystack backend setup ==="

# System updates
apt-get update && apt-get upgrade -y
apt-get install -y python3.12 python3.12-venv python3-pip git nginx postgresql postgresql-contrib

# PostgreSQL setup
sudo -u postgres psql -c "CREATE USER ominis_admin WITH PASSWORD 'CHANGE_ME_SECURE_PASSWORD';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE ominis_haystack OWNER ominis_admin;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ominis_haystack TO ominis_admin;" 2>/dev/null || true

# Create app directory
mkdir -p /opt/ominis-backend
cd /opt/ominis-backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# The actual application code will be synced via rsync/git
# For now, create a placeholder requirements.txt
cat << 'REQS' > requirements.txt
haystack-ai>=2.23.0
ollama-haystack>=1.0.0
sentence-transformers>=2.3.0
fastapi>=0.115.0
uvicorn[standard]>=0.27.0
sqlalchemy[asyncio]>=2.0.0
alembic>=1.13.0
psycopg2-binary>=2.9.0
asyncpg>=0.29.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
bcrypt>=4.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
boto3>=1.34.0
numpy>=1.26.0
tqdm>=4.66.0
REQS

pip install -r requirements.txt

# Create .env template
cat << 'ENVFILE' > .env
HOST=0.0.0.0
PORT=8000
DEBUG=false
DATABASE_URL=postgresql+asyncpg://ominis_admin:CHANGE_ME_SECURE_PASSWORD@127.0.0.1:5432/ominis_haystack
DATABASE_URL_SYNC=postgresql+psycopg2://ominis_admin:CHANGE_ME_SECURE_PASSWORD@127.0.0.1:5432/ominis_haystack
JWT_SECRET=CHANGE_ME_GENERATE_A_LONG_RANDOM_STRING
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440
OLLAMA_URL=http://${GPU_OLLAMA_IP}:11434
OLLAMA_MODEL=ominis-2.0
FALCON_OLLAMA_URL=http://${FALCON_OLLAMA_IP:-localhost}:11434
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
AWS_REGION=mx-central-1
EMBEDDINGS_BUCKET=ominis-health-embeddings-mx
VECTOR_PREFIX=vectors
FRONTEND_URL=https://ominis.org
ALLOWED_ORIGINS=https://ominis.org,http://localhost:3000
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ENVFILE

# Systemd service
cat << 'SERVICEEOF' > /etc/systemd/system/ominis-backend.service
[Unit]
Description=Ominis Health Haystack Backend
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ominis-backend
ExecStart=/opt/ominis-backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10
EnvironmentFile=/opt/ominis-backend/.env

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable ominis-backend

# Nginx reverse proxy
cat << 'NGINXEOF' > /etc/nginx/sites-available/ominis-backend
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE streaming support
        proxy_buffering off;
        proxy_cache off;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;
        proxy_read_timeout 120s;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/ominis-backend /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== \$(date) Setup complete! ==="
echo "Next: sync the backend code, update .env, run alembic upgrade head, and start the service."
USERDATA
)

# --- Check for existing instance ---
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    echo ""
    echo "Instance already exists: $EXISTING_INSTANCE"
    INSTANCE_ID="$EXISTING_INSTANCE"

    STATE=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text \
        --region "$REGION")
    if [ "$STATE" = "stopped" ]; then
        echo "  Starting stopped instance..."
        aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
        aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
    fi
else
    echo ""
    echo "Launching t3.large instance..."

    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health},{Key=Purpose,Value=haystack-backend}]" \
        --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$VOLUME_SIZE,\"VolumeType\":\"gp3\"}}]" \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$REGION")

    echo "  ✓ Instance launched: $INSTANCE_ID"
fi

# --- Wait & get IP ---
echo ""
echo "Waiting for instance..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

# Elastic IP
EXISTING_EIP=$(aws ec2 describe-addresses \
    --filters "Name=tag:Name,Values=ominis-haystack-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-haystack-eip},{Key=Project,Value=ominis-health}]" \
        --query 'AllocationId' \
        --output text \
        --region "$REGION")
    echo "  ✓ Elastic IP allocated"
else
    ALLOCATION_ID="$EXISTING_EIP"
    echo "  ✓ Elastic IP exists"
fi

aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOCATION_ID" \
    --region "$REGION" 2>/dev/null || true

BACKEND_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$REGION")

# --- Save config ---
cat << EOF > "$SCRIPT_DIR/../config/haystack_backend.txt"
# Ominis Health - Haystack Backend Configuration
BACKEND_INSTANCE_ID=$INSTANCE_ID
BACKEND_INSTANCE_TYPE=$INSTANCE_TYPE
BACKEND_IP=$BACKEND_IP
BACKEND_REGION=$REGION
BACKEND_URL=http://$BACKEND_IP:8000
BACKEND_URL_PUBLIC=http://$BACKEND_IP
EOF

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        Haystack Backend Deployed                             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Instance Type: $INSTANCE_TYPE"
echo "Elastic IP:    $BACKEND_IP"
echo "API URL:       http://$BACKEND_IP:8000  (direct)"
echo "               http://$BACKEND_IP       (via nginx)"
echo "Region:        $REGION"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                      NEXT STEPS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Wait ~5 min for setup to complete, then SSH in:"
echo "   ssh -i config/${KEY_NAME}.pem ubuntu@$BACKEND_IP"
echo ""
echo "2. Sync the backend code:"
echo "   rsync -avz --exclude='venv' --exclude='.env' backend-haystack/ ubuntu@$BACKEND_IP:/opt/ominis-backend/"
echo ""
echo "3. On the server, update .env with real secrets:"
echo "   sudo nano /opt/ominis-backend/.env"
echo ""
echo "4. Run database migrations:"
echo "   cd /opt/ominis-backend && source venv/bin/activate"
echo "   alembic upgrade head"
echo ""
echo "5. Start the service:"
echo "   sudo systemctl start ominis-backend"
echo "   sudo systemctl status ominis-backend"
echo ""
echo "6. Update frontend NEXT_PUBLIC_STRAPI_URL to:"
echo "   http://$BACKEND_IP"
echo ""
echo "Configuration saved to config/haystack_backend.txt"
echo ""
echo "⚠️  COST: t3.large ≈ \$0.0832/hour ≈ \$60/month"
