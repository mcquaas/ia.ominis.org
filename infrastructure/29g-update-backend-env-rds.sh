#!/bin/bash
# Print DATABASE_URL and DATABASE_URL_SYNC for RDS. Add these to backend .env (or run the SSH block below if you prefer).
# Run after 29f-create-rds-postgres.sh. Requires config/rds.txt.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/../config"
if [ ! -f "$CONFIG_DIR/rds.txt" ]; then
  echo "Error: config/rds.txt not found. Run ./infrastructure/29f-create-rds-postgres.sh first."
  exit 1
fi
source "$CONFIG_DIR/rds.txt"
source "$CONFIG_DIR/haystack_backend.txt" 2>/dev/null || true
KEY_FILE="${CONFIG_DIR}/ominis-ollama-key.pem"
SSH_USER="ubuntu"

DATABASE_URL="postgresql+asyncpg://${RDS_MASTER_USER}:${RDS_MASTER_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}"
DATABASE_URL_SYNC="postgresql://${RDS_MASTER_USER}:${RDS_MASTER_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DB_NAME}"

echo "Add these lines to /opt/ominis-backend/.env on the server (replace existing DATABASE_URL*):"
echo ""
echo "DATABASE_URL=$DATABASE_URL"
echo "DATABASE_URL_SYNC=$DATABASE_URL_SYNC"
echo ""
echo "Then on the server: sudo systemctl restart ominis-backend  (and run pg_restore if migrating from local DB; see docs/RDS_MIGRATION.md)"
