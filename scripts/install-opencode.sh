#!/usr/bin/env bash
# Install OpenCode + oh-my-opencode-slim for Starship OS.
# Prefers vendored tarballs under third_party/ (offline/ISO); falls back to npm/curl.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PINS="$REPO_DIR/third_party/pins.json"
OC_DIR="$REPO_DIR/third_party/opencode"
SLIM_DIR="$REPO_DIR/third_party/oh-my-opencode-slim"
CONFIG_SRC="$REPO_DIR/config/opencode/oh-my-opencode-slim.starship.json"
SYSTEM_CONFIG_DIR="${STARSHIP_OPENCODE_CONFIG_DIR:-/etc/starship/opencode}"

read_pin() {
  local key="$1"
  if [[ -f "$PINS" ]] && command -v python3 >/dev/null 2>&1; then
    python3 -c "import json; print(json.load(open('$PINS'))['components']['$key']['version'])"
  else
    case "$key" in
      opencode) echo "1.18.2" ;;
      oh-my-opencode-slim) echo "2.2.2" ;;
    esac
  fi
}

OC_VER="$(read_pin opencode)"
SLIM_VER="$(read_pin oh-my-opencode-slim)"

echo "=== Starship OpenCode install ==="
echo "  opencode-ai@${OC_VER}"
echo "  oh-my-opencode-slim@${SLIM_VER}"

install_from_tgz() {
  local tgz="$1"
  echo "Installing from vendored package: $tgz"
  npm install -g "$tgz"
}

# 1) Prefer vendored npm packs
OC_TGZ="$(ls -1 "$OC_DIR"/opencode-ai-*.tgz 2>/dev/null | head -1 || true)"
SLIM_TGZ="$(ls -1 "$SLIM_DIR"/oh-my-opencode-slim-*.tgz 2>/dev/null | head -1 || true)"

if command -v npm >/dev/null 2>&1; then
  if [[ -n "$OC_TGZ" ]]; then
    install_from_tgz "$OC_TGZ"
  else
    echo "No vendored opencode-ai tgz — installing from npm registry..."
    npm install -g "opencode-ai@${OC_VER}"
  fi

  if [[ -n "$SLIM_TGZ" ]]; then
    install_from_tgz "$SLIM_TGZ"
  else
    echo "No vendored oh-my-opencode-slim tgz — installing from npm registry..."
    npm install -g "oh-my-opencode-slim@${SLIM_VER}" || true
  fi
else
  echo "npm not found — trying official OpenCode installer..."
  curl -fsSL https://opencode.ai/install | bash
fi

# 2) Install Starship preset config
if [[ -f "$CONFIG_SRC" ]]; then
  if [[ "$(id -u)" == "0" ]]; then
    mkdir -p "$SYSTEM_CONFIG_DIR"
    cp "$CONFIG_SRC" "$SYSTEM_CONFIG_DIR/oh-my-opencode-slim.json"
    echo "Config installed: $SYSTEM_CONFIG_DIR/oh-my-opencode-slim.json"
  else
    USER_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/starship/opencode"
    mkdir -p "$USER_CFG"
    cp "$CONFIG_SRC" "$USER_CFG/oh-my-opencode-slim.json"
    echo "Config installed (user): $USER_CFG/oh-my-opencode-slim.json"
    echo "(run as root to install system-wide under $SYSTEM_CONFIG_DIR)"
  fi
fi

# 3) Verify
echo ""
if command -v opencode >/dev/null 2>&1; then
  echo "OpenCode: $(opencode --version 2>/dev/null || opencode version 2>/dev/null || echo installed)"
else
  # common install paths
  for p in "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode; do
    if [[ -x "$p" ]]; then
      echo "OpenCode: $($p --version 2>/dev/null || echo "$p")"
      echo "Add to PATH: export PATH=\"$(dirname "$p"):\$PATH\""
      break
    fi
  done
fi
echo "Done."
