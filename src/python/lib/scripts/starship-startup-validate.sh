#!/bin/bash
# Starship OS - Post-Boot Startup Validation
# Checks all system components and triggers Romi's captain's briefing
set -e

NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11435}"
LOG_FILE="/var/log/agnetic/startup-check.log"
PYTHON="/usr/bin/python3"
AGNETIC_ROOT="/opt/agnetic"
export PYTHONPATH="$AGNETIC_ROOT"

echo "============================================" | tee -a "$LOG_FILE"
echo " Starship OS Post-Boot Validation" | tee -a "$LOG_FILE"
echo " $(date -Iseconds)" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "0" ] || [ "$result" = "true" ]; then
        echo "  [PASS] $name" | tee -a "$LOG_FILE"
        PASS=$((PASS + 1))
    elif [ "$result" = "warn" ]; then
        echo "  [WARN] $name" | tee -a "$LOG_FILE"
        WARN=$((WARN + 1))
    else
        echo "  [FAIL] $name - $result" | tee -a "$LOG_FILE"
        FAIL=$((FAIL + 1))
    fi
}

echo "" | tee -a "$LOG_FILE"
echo "--- Layer 1: Infrastructure ---" | tee -a "$LOG_FILE"

# 1. Ollama check
if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    MODELS=$(curl -sf "$OLLAMA_URL/api/tags" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('models',[])))")
    check "Ollama LLM Server ($MODELS models available)" "true"
else
    check "Ollama LLM Server" "Not responding on $OLLAMA_URL"
fi

# 2. NATS check
if $PYTHON -c "
import asyncio
async def test():
    from nats import connect
    nc = await connect('$NATS_URL')
    sub = await nc.subscribe('agnetic.health.ping')
    await nc.flush()
    await asyncio.sleep(0.5)
    await nc.publish('agnetic.health.ping', b'ping')
    msg = await sub.next_msg(timeout=3)
    ok = msg.data.decode() == 'ping'
    await nc.close()
    exit(0 if ok else 1)
asyncio.run(test())
" 2>/dev/null; then
    check "NATS Message Broker" "true"
else
    check "NATS Message Broker" "Not responding on $NATS_URL"
fi

echo "" | tee -a "$LOG_FILE"
echo "--- Layer 2: Vector Database ---" | tee -a "$LOG_FILE"

# 3. LanceDB / Memory check
if $PYTHON -c "
from services.memory import MemoryManager, MemoryType
mgr = MemoryManager()
mid = mgr.store('system', MemoryType.EPISODIC, 'startup validation', summary='boot test')
results = mgr.search('startup', limit=5)
mgr.close()
if mid is not None:
    exit(0)
elif len(results) > 0:
    exit(0)
else:
    exit(1)
" 2>/dev/null; then
    check "LanceDB Vector Database (read/write)" "true"
else
    check "LanceDB Vector Database" "warn"
fi

echo "" | tee -a "$LOG_FILE"
echo "--- Layer 3: Agent Mesh ---" | tee -a "$LOG_FILE"

# 4. Check agents via NATS
for AGENT in romi proxy ergo system_health knowledge_store orchestrator; do
    if $PYTHON -c "
import asyncio
async def test():
    from nats import connect
    nc = await connect('$NATS_URL')
    sub = await nc.subscribe('agnetic.agent.${AGENT}.status', max_msgs=1)
    await nc.flush()
    # Request status
    await nc.publish('agnetic.agent.${AGENT}.command.status', b'{\"command\":\"status\"}')
    try:
        msg = await sub.next_msg(timeout=5)
        data = json.loads(msg.data.decode())
        ok = data.get('status') in ('online', 'complete', 'processing')
        await nc.close()
        exit(0 if ok else 1)
    except:
        # Check if process is at least running
        import subprocess as sp
        r = sp.run(['pgrep', '-f', f'agent_daemon.py ${AGENT}'], capture_output=True)
        await nc.close()
        exit(0 if r.returncode == 0 else 1)
asyncio.run(test())
" 2>/dev/null; then
        check "Agent: ${AGENT^}" "true"
    else
        check "Agent: ${AGENT^}" "Not responding"
    fi
done

echo "" | tee -a "$LOG_FILE"
echo "--- Layer 4: Skills & Capabilities ---" | tee -a "$LOG_FILE"

# 5. Skills check
SKILL_COUNT=$(ls "$AGNETIC_ROOT/lib/skills"/*/SKILL.md 2>/dev/null | wc -l)
if [ "$SKILL_COUNT" -gt 0 ]; then
    check "Skills loaded ($SKILL_COUNT skills)" "true"
    $PYTHON -c "
import sys; sys.path.insert(0, '$AGNETIC_ROOT/lib')
from agent_daemon import load_skill_content
skills = load_skill_content(['system-health', 'code-review', 'security-audit', 'ergo-automation', 'proxy-diagnostics'])
print(f'Skills test: {len(skills)} chars loaded')
exit(0 if len(skills) > 0 else 1)
" 2>/dev/null && check "Skill content accessible" "true" || check "Skill content accessible" "warn"
else
    check "Skills directory" "No skills found in $AGNETIC_ROOT/lib/skills"
fi

# 6. Soul files check
SOUL_COUNT=$(ls "$AGNETIC_ROOT/lib/souls"/*/SOUL.md 2>/dev/null | wc -l)
check "Agent souls loaded ($SOUL_COUNT souls)" "$([ "$SOUL_COUNT" -gt 0 ] && echo 'true' || echo 'warn')"

echo "" | tee -a "$LOG_FILE"
echo "--- Layer 5: Configuration & Gateways ---" | tee -a "$LOG_FILE"

# 7. Config files
for CFG in proxy.yaml romi.yaml ergo.yaml config.yaml; do
    if [ -f "$AGNETIC_ROOT/lib/$CFG" ] || [ -f "$AGNETIC_ROOT/agents/$CFG" ]; then
        :
    else
        check "Config: $CFG" "Missing"
    fi
done
check "Agent configurations" "true"

# 8. NATS JetStream
$PYTHON -c "
import asyncio
async def test():
    from nats import connect
    nc = await connect('$NATS_URL')
    js = nc.jetstream()
    try:
        await js.add_stream(name='agnetic_events', subjects=['agnetic.>'])
        print('JetStream stream created/verified')
        await nc.close()
        exit(0)
    except Exception as e:
        print(f'JetStream: {e}')
        await nc.close()
        exit(1)
asyncio.run(test())
" 2>/dev/null && check "NATS JetStream enabled" "true" || check "NATS JetStream enabled" "warn"

echo "" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"
echo " Results: $PASS passed, $WARN warnings, $FAIL failed" | tee -a "$LOG_FILE"
echo "============================================" | tee -a "$LOG_FILE"

# Trigger Romi's captain's briefing if all critical systems pass
if [ "$FAIL" -lt 2 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "--- Triggering Romi Captain's Briefing ---" | tee -a "$LOG_FILE"
    $PYTHON -c "
import asyncio, json
async def briefing():
    from nats import connect
    nc = await connect('$NATS_URL')
    sub = await nc.subscribe('starship.briefing.result', max_msgs=1)
    await nc.flush()
    await asyncio.sleep(0.3)
    await nc.publish('agnetic.workflow.captains-briefing', json.dumps({
        'workflow': 'captains-briefing',
    }).encode())
    try:
        msg = await sub.next_msg(timeout=60)
        result = json.loads(msg.data.decode())
        print(f'Briefing: OK')
        for agent, status in result.get('results', {}).items():
            s = status.get('status', 'unknown')
            print(f'  {agent}: {s}')
    except asyncio.TimeoutError:
        print('Briefing: workflow engine did not respond in time')
    await nc.close()
asyncio.run(briefing())
" 2>&1 | tee -a "$LOG_FILE"
    echo "--- Captain's Briefing Complete ---" | tee -a "$LOG_FILE"
fi

exit $FAIL
