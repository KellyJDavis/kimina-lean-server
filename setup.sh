#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Delegate to the packaged setup script so that development and PyPI installs
# always share the same instructions.
exec "$SCRIPT_DIR/server/setup.sh" "$@"
