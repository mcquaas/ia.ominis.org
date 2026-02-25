#!/bin/bash
# Launch a small EC2 to run only the nightly pipeline (same region/VPC as backend so it can reach RDS).
# No GPU needed (MiniLM embedding runs on CPU). After launch, set config/pipeline_worker.txt and run 29e-setup-pipeline-worker.sh.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
source "$CONFIG_DIR/haystack_backend.txt" 2>/dev/null || true

REGION="${BACKEND_REGION:-mx-central-1}"
KEY_NAME="${AWS_KEY_NAME:-ominis-ollama-key}"
INSTANCE_TYPE="t3.medium"   # 2 vCPU, 4 GB RAM - enough for embedding (no GPU)
SG_NAME="ominis-pipeline-worker-sg"
AMI_ID="ami-0a57f819c3fccde4f"   # Ubuntu 24.04 in mx-central-1 (check if valid for your region)

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Launching pipeline worker EC2 (no GPU)                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Region: $REGION  Type: $INSTANCE_TYPE"
echo ""

# Get VPC from backend instance so worker can reach same RDS
VPC_ID=""
SUBNET_ID=""
if [ -n "$BACKEND_INSTANCE_ID" ]; then
  VPC_ID=$(aws ec2 describe-instances --instance-ids "$BACKEND_INSTANCE_ID" --region "$REGION" \
    --query 'Reservations[0].Instances[0].VpcId' --output text 2>/dev/null || true)
  SUBNET_ID=$(aws ec2 describe-instances --instance-ids "$BACKEND_INSTANCE_ID" --region "$REGION" \
    --query 'Reservations[0].Instances[0].SubnetId' --output text 2>/dev/null || true)
fi
if [ -z "$VPC_ID" ] || [ "$VPC_ID" = "None" ]; then
  echo "Could not get VPC from backend instance; using default VPC."
  VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region "$REGION" --query 'Vpcs[0].VpcId' --output text 2>/dev/null || true)
  SUBNET_ID=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" --region "$REGION" --query 'Subnets[0].SubnetId' --output text 2>/dev/null || true)
fi
echo "VPC: $VPC_ID  Subnet: $SUBNET_ID"
echo ""

# Security group for worker
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo "Creating security group $SG_NAME ..."
  SG_ID=$(aws ec2 create-security-group \
    --group-name "$SG_NAME" \
    --description "Pipeline worker for Ominis health datastore" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' --output text --region "$REGION")
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0 --region "$REGION"
  echo "  ✓ Created $SG_ID"
fi

echo "Launching instance ..."
OUT=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=ominis-pipeline-worker}]" \
  --region "$REGION" \
  --query 'Instances[0].InstanceId' --output text)
INSTANCE_ID="$OUT"
echo "  Instance ID: $INSTANCE_ID"
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
PIPELINE_WORKER_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "  Public IP:   $PIPELINE_WORKER_IP"
echo ""
echo "Wait ~1 min for SSH, then:"
echo "  1. cp config/pipeline_worker.txt.example config/pipeline_worker.txt"
echo "  2. Set PIPELINE_WORKER_IP=$PIPELINE_WORKER_IP in config/pipeline_worker.txt"
echo "  3. ./infrastructure/29e-setup-pipeline-worker.sh"
echo "  4. ./infrastructure/29d-remove-pipeline-cron-from-backend.sh"
echo ""
echo "If RDS is in this VPC, ensure RDS security group allows inbound PostgreSQL (5432) from $SG_ID (this worker SG)."
