#!/bin/bash
# Helper script to install client package in development mode
# Usage: ./scripts/install-client-dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Ensure we're using the client pyproject.toml (should be default)
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found"
    exit 1
fi

# Check if it's the client one (quick check)
if ! grep -q "kimina-ast-client" pyproject.toml; then
    echo "Warning: pyproject.toml doesn't appear to be for the client package"
    echo "If you just installed the server, restore pyproject.toml first"
fi

# Install in editable mode
pip install -e .

echo "✓ Client package installed in editable mode"

