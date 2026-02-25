#!/bin/bash
# Build Ominis LibreChat image from source LOCALLY (no sync to server).
# Run from repo root: ./infrastructure/librechat-ominis-build/build-from-source-local.sh
# Output: docker image librechat-ominis:latest. Push to your registry and use on chat server if needed.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -d "$REPO_ROOT/frontend-librechat/client" ]; then
    echo "Error: frontend-librechat not found. Run from repo root: git submodule update --init --recursive"
    exit 1
fi

cd "$REPO_ROOT"
echo "Building librechat-ominis:latest from source (context: repo root)..."
docker build -f infrastructure/librechat-ominis-build/Dockerfile.from-source -t librechat-ominis:latest .
echo "Done. Image: librechat-ominis:latest"
