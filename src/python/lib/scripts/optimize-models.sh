#!/bin/bash
# Starship OS — Model Optimizer
# Detects hardware, polls available Ollama models, calculates best fit,
# asks user before pulling, and assigns to agents.
set -euo pipefail

AGNETIC_ROOT="${AGNETIC_ROOT:-/opt/agnetic}"
CONFIG_YAML="$AGNETIC_ROOT/lib/config.yaml"
CONNECTIONS_YAML="$AGNETIC_ROOT/lib/connections.yaml"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11435}"
PYTHON="${PYTHON:-python3}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[MODEL]${NC} $*"; }
warn() { echo -e "${YELLOW}[MODEL]${NC} $*"; }
err()  { echo -e "${RED}[MODEL]${NC} $*" >&2; }
info() { echo -e "${CYAN}[MODEL]${NC} $*"; }

echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Starship OS — Model Optimizer       ║${NC}"
echo -e "${BLUE}║  $(date -Iseconds)                   ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ─── Step 1: Detect Hardware ──────────────────────────────────────────
log "Step 1: Detecting hardware..."

GPU_VENDOR="unknown"
GPU_VRAM_MB=0
GPU_NAME=""
TOTAL_RAM_MB=0

if [ -f /tmp/agnetic-gpu-state.json ]; then
    GPU_VENDOR=$($PYTHON -c "import json; d=json.load(open('/tmp/agnetic-gpu-state.json')); print(d.get('vendor','unknown'))")
    GPU_VRAM_MB=$($PYTHON -c "import json; d=json.load(open('/tmp/agnetic-gpu-state.json')); print(int(d.get('vram','0').split()[0]) if d.get('vram','0').split()[0].isdigit() else 0)")
    GPU_NAME=$($PYTHON -c "import json; d=json.load(open('/tmp/agnetic-gpu-state.json')); print(d.get('name','unknown'))")
fi

TOTAL_RAM_MB=$(grep MemTotal /proc/meminfo | awk '{print int($2/1024)}')
TOTAL_RAM_GB=$((TOTAL_RAM_MB / 1024))

info "GPU: $GPU_NAME ($GPU_VENDOR, ${GPU_VRAM_MB}MB VRAM)"
info "System RAM: ${TOTAL_RAM_MB}MB (${TOTAL_RAM_GB}GB)"

# ─── Step 2: Check Available Models ────────────────────────────────────
log "Step 2: Checking available models on Ollama..."

AVAILABLE_MODELS=""
if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    AVAILABLE_MODELS=$(curl -sf "$OLLAMA_URL/api/tags" | $PYTHON -c "
import json, sys
d = json.load(sys.stdin)
for m in d.get('models', []):
    name = m['name']
    size_mb = m.get('size', 0) // (1024*1024)
    print(f'{name}  ({size_mb}MB)')
")
fi

if [ -z "$AVAILABLE_MODELS" ]; then
    warn "No models found on Ollama (is it running on $OLLAMA_URL?)"
    AVAILABLE_MODELS="(none)"
fi
echo "$AVAILABLE_MODELS"

# ─── Step 3: Calculate Best Fit ────────────────────────────────────────
log "Step 3: Calculating best model fit..."

# Strategy for 6GB VRAM: keep qwen2.5:3b for light agents, add qwen2.5:7b for heavy
RECOMMEND_PRIMARY="qwen2.5:7b"
RECOMMEND_SECONDARY="qwen2.5:3b"
RECOMMEND_EXTERNAL="openrouter (gpt-4o-mini, claude-3.5-haiku, gemini-2.0-flash)"

if [ "$GPU_VENDOR" = "none" ] || [ "$GPU_VRAM_MB" -lt 4000 ]; then
    RECOMMEND_PRIMARY="qwen2.5:3b"
    warn "Less than 4GB VRAM — recommending 3B models only"
elif [ "$GPU_VRAM_MB" -ge 8000 ]; then
    RECOMMEND_PRIMARY="qwen2.5:7b"
    info "8GB+ VRAM detected — can run 7B models with room for context"
elif [ "$GPU_VRAM_MB" -ge 12000 ]; then
    RECOMMEND_PRIMARY="qwen2.5:7b"
    info "12GB+ VRAM detected — can run 7B models and potentially larger"
fi

info "Recommended local setup: $RECOMMEND_PRIMARY (primary) + $RECOMMEND_SECONDARY (secondary)"
info "Recommended cloud fallback: $RECOMMEND_EXTERNAL"
echo ""

# ─── Step 4: Pull Missing Models (with user prompt) ────────────────────
log "Step 4: Checking if recommended models are available..."

pull_if_missing() {
    local model="$1"
    local label="$2"
    if echo "$AVAILABLE_MODELS" | grep -q "$model"; then
        info "  $model already available — skipping pull"
        return 0
    fi
    echo ""
    warn "  $label ($model) is not yet pulled."
    warn "  Size: varies (typically 2-5 GB download)"
    read -p "  Pull $model now? [y/N] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "  Pulling $model..."
        OLLAMA_HOST="127.0.0.1:11435" ollama pull "$model" 2>&1
        log "  $model pulled successfully"
    else
        warn "  Skipping $model"
    fi
}

pull_if_missing "$RECOMMEND_PRIMARY" "Primary model"
pull_if_missing "$RECOMMEND_SECONDARY" "Secondary model"

# ─── Step 5: Check OpenRouter API Key ──────────────────────────────────
log "Step 5: Checking OpenRouter configuration..."

OPENROUTER_KEY=""
if [ -f "$CONNECTIONS_YAML" ]; then
    OPENROUTER_KEY=$($PYTHON -c "
import yaml
d = yaml.safe_load(open('$CONNECTIONS_YAML'))
prov = d.get('providers',{}).get('openrouter',{})
key = prov.get('api_key','')
if key:
    print('configured')
else:
    print('')
" 2>/dev/null || echo "")
fi

if [ -z "$OPENROUTER_KEY" ]; then
    warn "  No OpenRouter API key configured."
    echo "  To enable cloud model fallback, add your key to:"
    echo "    $CONNECTIONS_YAML"
    echo "  under providers.openrouter.api_key"
    echo "  Get a key at: https://openrouter.ai/keys"
    echo ""
    read -p "  Enter OpenRouter API key (or leave blank to skip): " -r USER_KEY
    if [ -n "$USER_KEY" ]; then
        $PYTHON -c "
import yaml
d = yaml.safe_load(open('$CONNECTIONS_YAML'))
d.setdefault('providers',{}).setdefault('openrouter',{})['api_key'] = '$USER_KEY'
with open('$CONNECTIONS_YAML','w') as f:
    yaml.dump(d, f, default_flow_style=False)
print('Key saved to $CONNECTIONS_YAML')
"
        log "  OpenRouter API key saved"
    fi
else
    info "  OpenRouter API key is configured"
fi

# ─── Step 6: Assign Models to Agents ───────────────────────────────────
log "Step 6: Assigning models to agents..."

$PYTHON -c "
import yaml
cfg = yaml.safe_load(open('$CONFIG_YAML'))

if 'agents' not in cfg:
    cfg['agents'] = {}

gpu_vram = $GPU_VRAM_MB

for name, agent in cfg['agents'].items():
    role = agent.get('role', '')
    if name in ('orchestrator', 'proxy') and gpu_vram >= 4000:
        agent['model'] = '$RECOMMEND_PRIMARY'
        agent['provider'] = 'ollama'
    elif name in ('system_health', 'knowledge_store'):
        agent['model'] = '$RECOMMEND_SECONDARY'
        agent['provider'] = 'ollama'
    else:
        agent['model'] = '$RECOMMEND_SECONDARY'
        agent['provider'] = 'ollama'

with open('$CONFIG_YAML', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)

print('Models assigned')
"

log "  Agent model assignments updated in $CONFIG_YAML"
echo ""

# ─── Summary ───────────────────────────────────────────────────────────
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Model Optimization Complete         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""
info "To apply changes, restart relevant agents:"
info "  systemctl restart starship-agent@<agent>  (if using systemd)"
info "  or: pkill -f agent_daemon.py; starship-start.sh"
echo ""
info "To configure cloud providers, edit: $CONNECTIONS_YAML"
info "Available OpenRouter models listed in each agent's YAML config."
echo ""
