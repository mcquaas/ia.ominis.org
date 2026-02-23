#!/bin/bash
# Create a venv and install the Vast.ai CLI for use by 24b / 24c scripts.
# Run from repo root or infrastructure/. No need to activate; scripts use this venv automatically.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv-vast"

if [ -x "$VENV_DIR/bin/vastai" ]; then
  echo "Vast CLI already installed at $VENV_DIR/bin/vastai"
  "$VENV_DIR/bin/vastai" --version 2>/dev/null || true
  exit 0
fi

echo "Creating venv and installing vastai in $VENV_DIR ..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q vastai

echo "Done. Use: $VENV_DIR/bin/vastai"
echo "Scripts 24b and 24c will use this venv automatically."
"$VENV_DIR/bin/vastai" --version 2>/dev/null || true
