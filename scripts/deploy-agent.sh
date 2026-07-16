#!/usr/bin/env bash
# Starship OS — Remote Agent Deployer
# Installs staragent + osquery + configs on a remote endpoint.
# Usage: ./deploy-agent.sh <hostname> [user]
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn() { echo -e "${YELLOW}[DEPLOY]${NC} $*"; }
err()  { echo -e "${RED}[DEPLOY]${NC} $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-}"
USER="${2:-root}"
if [[ -z "$HOST" ]]; then
    echo "Usage: $0 <hostname> [user]"
    echo "Example: $0 10.0.1.50"
    exit 1
fi

# ─── Build staragent if needed ─────────────────────────────────────
STARAGENT_BIN="$REPO_DIR/agent/target/release/staragent"
if [[ ! -f "$STARAGENT_BIN" ]]; then
    log "Building staragent..."
    (cd "$REPO_DIR/agent" && cargo build --release)
fi

# ─── Detect target OS/arch ─────────────────────────────────────────
log "Detecting remote OS and architecture on $HOST..."
OS=$(ssh "$USER@$HOST" "uname -s" 2>/dev/null || echo "Linux")
ARCH=$(ssh "$USER@$HOST" "uname -m" 2>/dev/null || echo "x86_64")
log "Remote: $OS $ARCH"

# For cross-compilation, build if arch doesn't match local
LOCAL_ARCH=$(uname -m)
if [[ "$ARCH" != "$LOCAL_ARCH" ]]; then
    log "Cross-compiling for $OS/$ARCH..."
    TARGET=""
    case "$OS $ARCH" in
        "Linux x86_64")  TARGET="x86_64-unknown-linux-gnu" ;;
        "Linux aarch64") TARGET="aarch64-unknown-linux-gnu" ;;
        "Darwin x86_64") TARGET="x86_64-apple-darwin" ;;
        "Darwin arm64")  TARGET="aarch64-apple-darwin" ;;
        *) err "Unsupported: $OS $ARCH" ;;
    esac
    if command -v cross &>/dev/null; then
        (cd "$REPO_DIR/agent" && cross build --release --target "$TARGET")
        STARAGENT_BIN="$REPO_DIR/agent/target/$TARGET/release/staragent"
    else
        log "cross not installed, building natively (may fail for cross-arch)"
        (cd "$REPO_DIR/agent" && cargo build --release)
    fi
fi

# ─── Prepare deployment bundle ─────────────────────────────────────
DEPLOY_DIR=$(mktemp -d)
log "Preparing deploy bundle in $DEPLOY_DIR..."

mkdir -p "$DEPLOY_DIR/opt/starship/bin"
mkdir -p "$DEPLOY_DIR/etc/starship/agents"
mkdir -p "$DEPLOY_DIR/etc/starship/osquery/packs"
mkdir -p "$DEPLOY_DIR/var/log/starship"
mkdir -p "$DEPLOY_DIR/var/lib/starship/osquery"

cp "$STARAGENT_BIN" "$DEPLOY_DIR/opt/starship/bin/staragent"
chmod 755 "$DEPLOY_DIR/opt/starship/bin/staragent"

# Configs
if [[ -f "$REPO_DIR/config/osquery/starshipd.conf" ]]; then
    mkdir -p "$DEPLOY_DIR/etc/starship/osquery"
    cp "$REPO_DIR/config/osquery/starshipd.conf" "$DEPLOY_DIR/etc/starship/osquery/"
    cp "$REPO_DIR/config/osquery/packs/"*.conf "$DEPLOY_DIR/etc/starship/osquery/packs/" 2>/dev/null || true
fi

# Create staragent.yaml
NATS_URL="${STARSHIP_NATS_URL:-nats://hub:4222}"
NATS_TOKEN="${STARSHIP_NATS_TOKEN:-}"
HOST_ID=$(ssh "$USER@$HOST" "hostname" 2>/dev/null || echo "$HOST")
cat > "$DEPLOY_DIR/etc/starship/agents/staragent.yaml" <<YAMLEOF
nats:
  url: "$NATS_URL"
  token: "$NATS_TOKEN"

telemetry:
  interval_secs: 10

osquery:
  binary: "/opt/starship/bin/osqueryd"
  config_path: "/etc/starship/osquery/starshipd.conf"
  result_log: "/var/log/starship/osquery_results.jsonl"

commands:
  subscribe:
    - "starship.agent.staragent.command.>"
    - "agnetic.agent.staragent.command.>"

hostname: "$HOST_ID"
YAMLEOF

# Systemd service
cat > "$DEPLOY_DIR/etc/systemd/system/agnetic-staragent.service" <<UNIT
[Unit]
Description=Starship OS - StarAgent Telemetry Collector
After=network.target
Documentation=https://github.com/andromi-hash/starship-os

[Service]
Type=simple
ExecStart=/opt/starship/bin/staragent
Restart=always
RestartSec=5
Environment=RUST_LOG=info
Environment=STARSHIP_ROOT=/opt/starship
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=/var/log/starship /tmp
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT

# ─── Transfer to remote ────────────────────────────────────────────
log "Transferring bundle to $HOST..."
tar czf - -C "$DEPLOY_DIR" . | ssh "$USER@$HOST" "tar xzf - -C /"
log "Files deployed to $HOST"

# ─── Install and start service ────────────────────────────────────
log "Enabling and starting staragent on $HOST..."
ssh "$USER@$HOST" "systemctl daemon-reload && systemctl enable agnetic-staragent && systemctl restart agnetic-staragent" || {
    warn "systemd not available, attempting direct start..."
    ssh "$USER@$HOST" "nohup /opt/starship/bin/staragent > /var/log/starship/staragent.log 2>&1 &"
}

log "Deployment complete for $HOST"
rm -rf "$DEPLOY_DIR"
