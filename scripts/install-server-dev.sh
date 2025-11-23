#!/bin/bash
# Helper script to install server package in development mode
# Usage: ./scripts/install-server-dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# Backup original pyproject.toml
if [ -f "pyproject.toml" ]; then
    cp pyproject.toml pyproject.toml.backup
    echo "Backed up pyproject.toml to pyproject.toml.backup"
fi

# Use server pyproject.toml
cp pyproject-server.toml pyproject.toml
echo "Using pyproject-server.toml for installation"

# Install in editable mode
pip install -e .

# Restore original
if [ -f "pyproject.toml.backup" ]; then
    mv pyproject.toml.backup pyproject.toml
    echo "Restored original pyproject.toml"
fi

echo "✓ Server package installed in editable mode"
echo "You can now use: kimina-ast-server"

