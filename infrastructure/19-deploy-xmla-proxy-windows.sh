#!/bin/bash
# =============================================================================
# Deploy XMLA Proxy on Windows EC2 (t3.micro)
#
# ADOMD.NET on Linux cannot connect to on-premises SSAS via TCP.
# This deploys a minimal Windows Server instance that runs the .NET proxy
# with native MSOLAP TCP support for querying SINBA OLAP cubes.
#
# Cost: t3.micro Windows ≈ $18/month (~$0.025/hr)
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/settings.sh" 2>/dev/null || true

# --- Configuration ---
REGION="${AWS_REGION:-mx-central-1}"
INSTANCE_TYPE="t3.micro"          # 2 vCPU, 1GB RAM — enough for the proxy
INSTANCE_NAME="ominis-xmla-proxy"
KEY_NAME="${AWS_KEY_NAME:-ominis-ollama-key}"
SECURITY_GROUP_NAME="ominis-xmla-proxy-sg"
VOLUME_SIZE=30                    # GB (Windows needs ~30GB minimum)

# Windows Server 2022 AMI (mx-central-1)
AMI_ID="ami-0bd08629b1f8dbe37"

# Load backend config
source "$SCRIPT_DIR/../config/haystack_backend.txt" 2>/dev/null || true
BACKEND_HOST="${BACKEND_IP:-78.12.33.205}"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Deploying XMLA Proxy (Windows EC2 for SSAS TCP)            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance Type: $INSTANCE_TYPE (2 vCPU, 1GB RAM)"
echo "Region:        $REGION"
echo "Backend:       $BACKEND_HOST"
echo "Cost:          ~\$18/month"
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
        --description "XMLA Proxy for SINBA OLAP Cubes (Windows)" \
        --query 'GroupId' \
        --output text \
        --region "$REGION")

    # RDP (3389) — for initial setup
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 3389 --cidr 0.0.0.0/0 --region "$REGION"
    # Proxy port (5001) — only from backend server
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 5001 --cidr "${BACKEND_HOST}/32" --region "$REGION"
    # WinRM (5985/5986) — for remote management
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 5985 --cidr 0.0.0.0/0 --region "$REGION"

    echo "  ✓ Security group created: $SG_ID"
else
    echo "  ✓ Security group exists: $SG_ID"
fi

# --- User Data (PowerShell bootstrap) ---
USER_DATA=$(cat << 'USERDATA'
<powershell>
# Install .NET 8 SDK
Write-Host "Installing .NET 8 SDK..."
$dotnetUrl = "https://dot.net/v1/dotnet-install.ps1"
Invoke-WebRequest -Uri $dotnetUrl -OutFile "$env:TEMP\dotnet-install.ps1"
& "$env:TEMP\dotnet-install.ps1" -Channel 8.0 -InstallDir "C:\dotnet"
[Environment]::SetEnvironmentVariable("DOTNET_ROOT", "C:\dotnet", "Machine")
[Environment]::SetEnvironmentVariable("PATH", "$env:PATH;C:\dotnet;C:\dotnet\tools", "Machine")

# Create proxy directory
New-Item -Path "C:\xmla-proxy" -ItemType Directory -Force

# Open firewall port 5001
New-NetFirewallRule -DisplayName "XMLA Proxy" -Direction Inbound -Port 5001 -Protocol TCP -Action Allow

Write-Host "Setup complete. Upload proxy code and run: dotnet publish + dotnet run"
</powershell>
USERDATA
)

# --- Check for existing instance ---
EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,pending,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region "$REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
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
    echo "Launching Windows t3.micro instance..."

    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --user-data "$USER_DATA" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=ominis-health},{Key=Purpose,Value=xmla-proxy}]" \
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
    --filters "Name=tag:Name,Values=ominis-xmla-proxy-eip" \
    --query 'Addresses[0].AllocationId' \
    --output text \
    --region "$REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    ALLOCATION_ID=$(aws ec2 allocate-address \
        --domain vpc \
        --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=ominis-xmla-proxy-eip},{Key=Project,Value=ominis-health}]" \
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

PROXY_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOCATION_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text \
    --region "$REGION")

# --- Save config ---
cat << EOF > "$SCRIPT_DIR/../config/xmla_proxy_server.txt"
# Ominis Health - XMLA Proxy (Windows) Configuration
XMLA_PROXY_INSTANCE_ID=$INSTANCE_ID
XMLA_PROXY_INSTANCE_TYPE=$INSTANCE_TYPE
XMLA_PROXY_IP=$PROXY_IP
XMLA_PROXY_REGION=$REGION
XMLA_PROXY_URL=http://$PROXY_IP:5001
EOF

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        XMLA Proxy (Windows) Deployed                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Instance Type: $INSTANCE_TYPE"
echo "Elastic IP:    $PROXY_IP"
echo "Proxy URL:     http://$PROXY_IP:5001"
echo "Region:        $REGION"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                      NEXT STEPS"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Wait ~10 min for Windows setup, then get the password:"
echo "   aws ec2 get-password-data --instance-id $INSTANCE_ID \\"
echo "     --priv-launch-key config/${KEY_NAME}.pem --region $REGION"
echo ""
echo "2. RDP into the server: $PROXY_IP:3389"
echo "   Username: Administrator"
echo ""
echo "3. Copy the xmla-proxy code and build:"
echo "   scp -r xmla-proxy/ Administrator@$PROXY_IP:C:\\xmla-proxy\\"
echo "   dotnet publish -c Release -o C:\\xmla-proxy\\publish"
echo ""
echo "4. Run the proxy:"
echo "   dotnet C:\\xmla-proxy\\publish\\XmlaProxy.dll"
echo ""
echo "5. Update backend .env:"
echo "   SINBA_XMLA_URL=http://$PROXY_IP:5001"
echo ""
echo "Config saved to config/xmla_proxy_server.txt"
echo ""
echo "⚠️  COST: t3.micro Windows ≈ \$0.025/hr ≈ \$18/month"
