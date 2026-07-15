#!/usr/bin/env bash
# Vendor OpenCode + oh-my-opencode-slim npm packages for offline/ISO builds.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PINS="$REPO_DIR/third_party/pins.json"
OC_DIR="$REPO_DIR/third_party/opencode"
SLIM_DIR="$REPO_DIR/third_party/oh-my-opencode-slim"

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm required to vendor packages" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 required to read pins.json" >&2
  exit 1
fi

read_pin() {
  local key="$1"
  python3 -c "import json; print(json.load(open('$PINS'))['components']['$key']['version'])"
}

OC_VER="$(read_pin opencode)"
SLIM_VER="$(read_pin oh-my-opencode-slim)"

mkdir -p "$OC_DIR" "$SLIM_DIR"
cd /tmp

echo "=== Vendoring opencode-ai@${OC_VER} ==="
npm pack "opencode-ai@${OC_VER}" --pack-destination "$OC_DIR"

echo "=== Vendoring oh-my-opencode-slim@${SLIM_VER} ==="
npm pack "oh-my-opencode-slim@${SLIM_VER}" --pack-destination "$SLIM_DIR"

# Copy Starship preset next to vendored slim package
cp "$REPO_DIR/config/opencode/oh-my-opencode-slim.starship.json" \
  "$SLIM_DIR/oh-my-opencode-slim.starship.json"

cat > "$OC_DIR/VERSION" <<EOF
opencode-ai=${OC_VER}
oh-my-opencode-slim=${SLIM_VER}
vendored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo ""
echo "Vendored:"
ls -lh "$OC_DIR"/*.tgz 2>/dev/null || true
ls -lh "$SLIM_DIR"/*.tgz 2>/dev/null || true
cat "$OC_DIR/VERSION"
echo "Done."
