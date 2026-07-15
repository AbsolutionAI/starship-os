#!/bin/bash
# Starship OS - Direct Startup Sequence (for environments without systemd)
# Boot order: ollama -> nats -> agents (romi, proxy, ergo) -> dashboard -> validation

set -e

AGNETIC_ROOT="/opt/agnetic"
PYTHON="/usr/bin/python3"
NATS_BIN="/usr/sbin/nats-server"
OLLAMA_BIN="/usr/local/bin/ollama"
LOG_DIR="/var/log/agnetic"
PID_DIR="/var/run/starship"
OLLAMA_PORT="${OLLAMA_PORT:-11435}"
NATS_PORT="${NATS_PORT:-4222}"

export AGNETIC_ROOT="$AGNETIC_ROOT"
export OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}"
export NATS_URL="nats://127.0.0.1:${NATS_PORT}"

mkdir -p "$LOG_DIR" "$PID_DIR" /var/lib/agnetic/nats /var/lib/agnetic/memory /etc/agnetic/secrets

cleanup() {
    echo "Shutting down Starship OS..."
    for p in romi proxy ergo orchestrator system_health knowledge_store codex-agent designer-agent; do
        if [ -f "$PID_DIR/agent-$p.pid" ]; then
            kill "$(cat "$PID_DIR/agent-$p.pid")" 2>/dev/null || true
            rm -f "$PID_DIR/agent-$p.pid"
        fi
    done
    [ -f "$PID_DIR/dashboard.pid" ] && kill "$(cat "$PID_DIR/dashboard.pid")" 2>/dev/null || true
    [ -f "$PID_DIR/system-telemetry.pid" ] && kill "$(cat "$PID_DIR/system-telemetry.pid")" 2>/dev/null || true
    [ -f "$PID_DIR/agnetic-status.pid" ] && kill "$(cat "$PID_DIR/agnetic-status.pid")" 2>/dev/null || true
    [ -f "$PID_DIR/nats.pid" ] && kill "$(cat "$PID_DIR/nats.pid")" 2>/dev/null || true
    [ -f "$PID_DIR/ollama.pid" ] && kill "$(cat "$PID_DIR/ollama.pid")" 2>/dev/null || true
    echo "Starship OS stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "============================================"
echo " Starship OS - Bridge Startup Sequence"
echo " $(date -Iseconds)"
echo "============================================"

# ---- Layer 1: Ollama LLM Server ----
echo " [1/6] Starting Ollama LLM Server (port $OLLAMA_PORT)..."
if pgrep -x ollama > /dev/null 2>&1; then
    echo "   Ollama already running"
else
    OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" nohup "$OLLAMA_BIN" serve \
        > "$LOG_DIR/ollama.log" 2>&1 &
    echo $! > "$PID_DIR/ollama.pid"
    for i in $(seq 1 10); do
        if curl -sf "http://127.0.0.1:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
            echo "   Ollama ready"
            break
        fi
        sleep 2
    done
fi
# Ensure model is available
if ! curl -sf "http://127.0.0.1:${OLLAMA_PORT}/api/tags" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if any('qwen2.5:3b' in m['name'] for m in d.get('models',[])) else 1)" 2>/dev/null; then
    echo "   Pulling qwen2.5:3b model..."
    OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" ollama pull qwen2.5:3b 2>&1
fi

# ---- Layer 2: NATS Message Broker ----
echo " [2/6] Starting NATS Message Broker (port $NATS_PORT)..."
if pgrep -x nats-server > /dev/null 2>&1; then
    echo "   NATS already running"
else
    nohup "$NATS_BIN" -p "$NATS_PORT" -js --store_dir /var/lib/agnetic/nats \
        > "$LOG_DIR/nats.log" 2>&1 &
    echo $! > "$PID_DIR/nats.pid"
    sleep 2
    echo "   NATS started"
fi

# ---- Layer 3: GPU Detection & System Telemetry ----
echo " [3/6] Detecting GPU..."
bash "$AGNETIC_ROOT/lib/scripts/detect-gpu.sh" detect > /dev/null 2>&1 || true
echo "   GPU state written to /tmp/agnetic-gpu-state.json"
echo "   Starting Status Bridge..."
if [ -f "$PID_DIR/agnetic-status.pid" ] && kill -0 "$(cat "$PID_DIR/agnetic-status.pid")" 2>/dev/null; then
    echo "   Status Bridge already running"
else
    OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}" \
    NATS_URL="nats://127.0.0.1:${NATS_PORT}" \
    AGNETIC_ROOT="$AGNETIC_ROOT" \
    nohup "$PYTHON" "$AGNETIC_ROOT/lib/tray/agnetic-status.py" \
        > "$LOG_DIR/agnetic-status.log" 2>&1 &
    echo $! > "$PID_DIR/agnetic-status.pid"
    echo "   Status Bridge started"
fi
echo "   Starting System Telemetry Collector..."
if [ -f "$PID_DIR/system-telemetry.pid" ] && kill -0 "$(cat "$PID_DIR/system-telemetry.pid")" 2>/dev/null; then
    echo "   System Telemetry already running"
else
    NATS_URL="nats://127.0.0.1:${NATS_PORT}" \
    nohup "$PYTHON" "$AGNETIC_ROOT/lib/services/system_telemetry.py" \
        > "$LOG_DIR/system-telemetry.log" 2>&1 &
    echo $! > "$PID_DIR/system-telemetry.pid"
    echo "   System Telemetry started"
fi

# ---- Layer 4: Agent Mesh ----
echo " [4/6] Starting Agent Mesh..."
for AGENT in romi proxy ergo system_health knowledge_store orchestrator codex-agent designer-agent; do
    if [ -f "$PID_DIR/agent-$AGENT.pid" ] && kill -0 "$(cat "$PID_DIR/agent-$AGENT.pid")" 2>/dev/null; then
        echo "   $AGENT already running"
        continue
    fi
    echo "   Launching $AGENT..."
    cd "$AGNETIC_ROOT/lib"
    OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}" \
    NATS_URL="nats://127.0.0.1:${NATS_PORT}" \
    AGNETIC_ROOT="$AGNETIC_ROOT" \
    nohup "$PYTHON" agent_daemon.py "$AGENT" \
        > "$LOG_DIR/agent-$AGENT.log" 2>&1 &
    echo $! > "$PID_DIR/agent-$AGENT.pid"
    sleep 1
done
sleep 3

# ---- Layer 5: Web Dashboard ----
echo " [5/6] Starting Web Dashboard (port 8788)..."
if [ -f "$PID_DIR/dashboard.pid" ] && kill -0 "$(cat "$PID_DIR/dashboard.pid")" 2>/dev/null; then
    echo "   Dashboard already running"
else
    OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}" \
    NATS_URL="nats://127.0.0.1:${NATS_PORT}" \
    AGNETIC_ROOT="$AGNETIC_ROOT" \
    DASHBOARD_PORT=8788 \
    AGNETIC_DASHBOARD_PORT=8788 \
    nohup "$PYTHON" "$AGNETIC_ROOT/lib/dashboard/server.py" \
        > "$LOG_DIR/dashboard.log" 2>&1 &
    echo $! > "$PID_DIR/dashboard.pid"
    echo "   Dashboard starting on http://0.0.0.0:8788"
fi

# ---- Layer 6: Startup Validation ----
echo " [6/6] Running Startup Validation..."
"$AGNETIC_ROOT/lib/scripts/starship-startup-validate.sh" || true

echo ""
echo "============================================"
echo " Starship OS Bridge is online."
echo " Dashboard: http://localhost:8788"
echo " NATS:      nats://127.0.0.1:${NATS_PORT}"
echo " Ollama:    http://127.0.0.1:${OLLAMA_PORT}"
echo "============================================"

# Wait for any signal
while true; do
    sleep 30
    # Auto-restart any dead agents
for AGENT in romi proxy ergo system_health knowledge_store orchestrator codex-agent designer-agent; do
        if [ -f "$PID_DIR/agent-$AGENT.pid" ]; then
            if ! kill -0 "$(cat "$PID_DIR/agent-$AGENT.pid")" 2>/dev/null; then
                echo "[$(date -Iseconds)] Agent $AGENT died — restarting..."
                cd "$AGNETIC_ROOT/lib"
                OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}" \
                NATS_URL="nats://127.0.0.1:${NATS_PORT}" \
                AGNETIC_ROOT="$AGNETIC_ROOT" \
                nohup "$PYTHON" agent_daemon.py "$AGENT" \
                    > "$LOG_DIR/agent-$AGENT.log" 2>&1 &
                echo $! > "$PID_DIR/agent-$AGENT.pid"
            fi
        fi
    done
done
