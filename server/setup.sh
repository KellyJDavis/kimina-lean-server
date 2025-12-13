#!/usr/bin/env bash
set -euxo pipefail

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

ensure_apple_ld() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return
  fi

  APPLE_LD_PATH=""
  if command -v xcrun >/dev/null 2>&1; then
    APPLE_LD_PATH="$(xcrun --find ld 2>/dev/null || true)"
  fi
  APPLE_LD_PATH="${APPLE_LD_PATH:-/usr/bin/ld}"

  # Ensure the linker we expose is the Apple ld64 (not lld).
  if ! "$APPLE_LD_PATH" -v 2>&1 | grep -qi "apple"; then
    echo "ERROR: Expected Apple ld64, but found $(\"$APPLE_LD_PATH\" -v 2>&1 | head -n 1)" >&2
    echo "Please install Xcode command line tools (xcode-select --install) to get ld64." >&2
    exit 1
  fi

  # Prepend the Apple ld64 bin dir in case other setup steps override PATH (e.g., elan).
  export PATH="$(dirname "$APPLE_LD_PATH"):${PATH}"
  export LD="$APPLE_LD_PATH"
  export REAL_LD64="$APPLE_LD_PATH"
  echo "Using Apple ld64 at $APPLE_LD_PATH"
}

ensure_apple_ld

LEAN_SERVER_LEAN_VERSION="${LEAN_SERVER_LEAN_VERSION:-v4.15.0}"
REPL_REPO_URL="${REPL_REPO_URL:-https://github.com/KellyJDavis/repl.git}"
REPL_BRANCH="${REPL_BRANCH:-$LEAN_SERVER_LEAN_VERSION}"
AST_REPO_URL="${AST_REPO_URL:-https://github.com/KellyJDavis/ast_export.git}"
AST_BRANCH="${AST_BRANCH:-$LEAN_SERVER_LEAN_VERSION}"
MATHLIB_REPO_URL="${MATHLIB_REPO_URL:-https://github.com/leanprover-community/mathlib4.git}"
MATHLIB_BRANCH="${MATHLIB_BRANCH:-$LEAN_SERVER_LEAN_VERSION}"

command -v curl >/dev/null 2>&1 || { echo >&2 "curl is required"; exit 1; }
command -v git  >/dev/null 2>&1 || { echo >&2 "git is required";  exit 1; }

echo "Installing Elan"
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf \
  | sh -s -- --default-toolchain "${LEAN_SERVER_LEAN_VERSION}" -y
source "$HOME/.elan/env"

# elan/env prepends its own toolchain binaries to PATH, so re-assert Apple ld.
ensure_apple_ld

echo "Installing Lean ${LEAN_SERVER_LEAN_VERSION}"
lean --version

version_lte() {
  local ver1="$1"
  local ver2="$2"

  if ! [[ "$ver1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || ! [[ "$ver2" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    return 1
  fi

  local v1="${ver1#v}"
  local v2="${ver2#v}"
  printf '%s\n%s\n' "$v1" "$v2" | sort -V -C
}

install_repo() {
  local name="$1" url="$2" branch="$3" upd_manifest="$4"
  echo "Installing ${name}@${branch}..."
  if [ ! -d "$name" ]; then
    git clone --branch "${branch}" --single-branch --depth 1 "$url" "$name"
  fi
  pushd "$name"
    git checkout "${branch}"
    if [ "$name" = "mathlib4" ]; then
      # On macOS avoid downloading prebuilt caches that might be linked with lld;
      # force local builds with Apple ld64 instead.
      if [[ "$(uname -s)" != "Darwin" ]]; then
        lake exe cache get
      else
        echo "Skipping mathlib4 cache download on macOS to force ld64-local build"
      fi
    fi
    lake build
    if [ "$upd_manifest" = "true" ]; then
      jq '.packages |= map(.type="path"|del(.url)|.dir=".lake/packages/"+.name)' \
         lake-manifest.json > lake-manifest.json.tmp && mv lake-manifest.json.tmp lake-manifest.json
    fi
  popd
}

install_repo repl "$REPL_REPO_URL" "$REPL_BRANCH" false

if version_lte "$REPL_BRANCH" "v4.9.0"; then
  echo "Applying commit 4fc1e6d1dda170e8f0a6b698dd5f7e17a9cf52b4 for $REPL_BRANCH (<=v4.9.0)..."
  pushd repl
    git fetch origin 4fc1e6d1dda170e8f0a6b698dd5f7e17a9cf52b4
    git cherry-pick 4fc1e6d1dda170e8f0a6b698dd5f7e17a9cf52b4
    lake build
  popd
fi

install_repo ast_export "$AST_REPO_URL" "$AST_BRANCH" false
install_repo mathlib4 "$MATHLIB_REPO_URL" "$MATHLIB_BRANCH" true

