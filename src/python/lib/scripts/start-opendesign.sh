#!/bin/bash
# Start Open Design daemon for agent design tool access
set -e

NVM_DIR="${NVM_DIR:-/root/.nvm}"
OPEN_DESIGN_DIR="${OPEN_DESIGN_DIR:-/opt/open-design}"
LOG_DIR="${LOG_DIR:-/var/log/agnetic}"
PID_DIR="${PID_DIR:-/var/run/starship}"
OPENDESIGN_PORT="${OPENDESIGN_PORT:-7456}"

mkdir -p "$LOG_DIR" "$PID_DIR"

# Source nvm to find the right node
if [ -f "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
fi

if [ -f "$PID_DIR/opendesign.pid" ] && kill -0 "$(cat "$PID_DIR/opendesign.pid")" 2>/dev/null; then
    echo "Open Design daemon already running"
    exit 0
fi

echo "Starting Open Design daemon on port $OPENDESIGN_PORT..."
cd "$OPEN_DESIGN_DIR"
nohup pnpm tools-dev --port "$OPENDESIGN_PORT" > "$LOG_DIR/opendesign.log" 2>&1 &
echo $! > "$PID_DIR/opendesign.pid"
echo "Open Design daemon started (PID: $(cat "$PID_DIR/opendesign.pid"))"
