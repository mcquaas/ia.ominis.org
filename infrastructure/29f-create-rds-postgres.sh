#!/bin/bash
# Create minimal RDS PostgreSQL for Ominis backend (production). Uses AWS CLI; account 9... (e.g. 945284793685).
# Run from repo root. Prereq: backend EC2 already exists (config/haystack_backend.txt) so we use its VPC.
# Output: RDS endpoint and password in config/rds.txt (gitignored). Update backend .env with DATABASE_URL* and migrate.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/haystack_backend.txt" ]; then
  echo "Error: config/haystack_backend.txt not found. Deploy backend first (17-deploy-haystack-backend.sh)."
  exit 1
fi
source "$CONFIG_DIR/haystack_backend.txt"

REGION="${BACKEND_REGION:-mx-central-1}"
DB_ID="ominis-haystack-db"
DB_INSTANCE_CLASS="db.t4g.micro"
DB_ENGINE="postgres"
DB_ENGINE_VERSION="16.6"
DB_NAME="ominis_haystack"
DB_MASTER_USER="ominis_admin"
ALLOCATED_STORAGE=20
STORAGE_TYPE="gp3"

VPC_ID=$(aws ec2 describe-instances --instance-ids "$BACKEND_INSTANCE_ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].VpcId' --output text)
BACKEND_SG=$(aws ec2 describe-instances --instance-ids "$BACKEND_INSTANCE_ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -z "$BACKEND_SG" ] || [ "$BACKEND_SG" = "None" ]; then
  BACKEND_SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=ominis-haystack-sg" "Name=vpc-id,Values=$VPC_ID" \
    --region "$REGION" --query 'SecurityGroups[0].GroupId' --output text)
fi

echo "Creating RDS PostgreSQL (minimal production)"
echo "Region: $REGION  VPC: $VPC_ID  Backend SG: $BACKEND_SG"
echo "Instance: $DB_INSTANCE_CLASS  Engine: $DB_ENGINE $DB_ENGINE_VERSION"
echo ""

SUBNET_GROUP="$DB_ID-subnet-group"
EXISTING=$(aws rds describe-db-subnet-groups --db-subnet-group-name "$SUBNET_GROUP" --region "$REGION" 2>/dev/null || true)
if [ -z "$EXISTING" ] || echo "$EXISTING" | grep -q "DBSubnetGroupNotFoundFault"; then
  SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region "$REGION" \
    --query 'Subnets[*].SubnetId' --output text | tr '\t' ' ')
  aws rds create-db-subnet-group \
    --db-subnet-group-name "$SUBNET_GROUP" \
    --db-subnet-group-description "Ominis Haystack RDS subnets" \
    --subnet-ids $SUBNETS \
    --region "$REGION"
  echo "Created DB subnet group: $SUBNET_GROUP"
else
  echo "DB subnet group exists: $SUBNET_GROUP"
fi

RDS_SG_NAME="ominis-rds-sg"
RDS_SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$RDS_SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --region "$REGION" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
if [ "$RDS_SG_ID" = "None" ] || [ -z "$RDS_SG_ID" ]; then
  RDS_SG_ID=$(aws ec2 create-security-group \
    --group-name "$RDS_SG_NAME" \
    --description "RDS PostgreSQL for Ominis Haystack" \
    --vpc-id "$VPC_ID" \
    --region "$REGION" \
    --query 'GroupId' --output text)
  aws ec2 authorize-security-group-ingress \
    --group-id "$RDS_SG_ID" --protocol tcp --port 5432 --source-group "$BACKEND_SG" --region "$REGION"
  echo "Created RDS security group: $RDS_SG_ID"
else
  echo "RDS security group exists: $RDS_SG_ID"
fi

RDS_PASSWORD_FILE="$CONFIG_DIR/rds.txt"
if [ -f "$RDS_PASSWORD_FILE" ]; then
  source "$RDS_PASSWORD_FILE" 2>/dev/null || true
fi
if [ -z "$RDS_MASTER_PASSWORD" ]; then
  RDS_MASTER_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
fi

EXISTING_DB=$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" --region "$REGION" 2>&1) || true
if echo "$EXISTING_DB" | grep -q "DBInstanceNotFound"; then
  echo "Creating RDS instance: $DB_ID ..."
  aws rds create-db-instance \
    --db-instance-identifier "$DB_ID" \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --engine "$DB_ENGINE" \
    --engine-version "$DB_ENGINE_VERSION" \
    --master-username "$DB_MASTER_USER" \
    --master-user-password "$RDS_MASTER_PASSWORD" \
    --allocated-storage "$ALLOCATED_STORAGE" \
    --storage-type "$STORAGE_TYPE" \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$RDS_SG_ID" \
    --db-subnet-group-name "$SUBNET_GROUP" \
    --no-publicly-accessible \
    --storage-encrypted \
    --region "$REGION" \
    --no-enable-performance-insights

  echo "Waiting for RDS (5–10 min)..."
  aws rds wait db-instance-available --db-instance-identifier "$DB_ID" --region "$REGION"
else
  echo "RDS instance already exists: $DB_ID"
  if [ -z "$RDS_MASTER_PASSWORD" ]; then
    echo "Set RDS_MASTER_PASSWORD in $RDS_PASSWORD_FILE"
    exit 1
  fi
fi

ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
PORT=$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Port' --output text)

cat > "$RDS_PASSWORD_FILE" << EOF
# RDS connection (gitignored)
RDS_ENDPOINT=$ENDPOINT
RDS_PORT=${PORT:-5432}
RDS_DB_NAME=$DB_NAME
RDS_MASTER_USER=$DB_MASTER_USER
RDS_MASTER_PASSWORD=$RDS_MASTER_PASSWORD
EOF

echo ""
echo "RDS created: $ENDPOINT:$PORT  DB: $DB_NAME  User: $DB_MASTER_USER"
echo "Config: $RDS_PASSWORD_FILE"
echo "Next: set backend .env DATABASE_URL and DATABASE_URL_SYNC to this host, then migrate (see docs/RDS_MIGRATION.md)."
