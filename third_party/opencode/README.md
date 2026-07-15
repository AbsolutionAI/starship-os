# OpenCode (vendored pins)

Starship OS ships **OpenCode** + **oh-my-opencode-slim** for coding/feature work.
This is separate from the NATS mesh agents (Proxy/Romi/Ergo).

## Pins

See `../pins.json` for exact versions.

| Component | Version | Role |
|-----------|---------|------|
| opencode-ai | 1.18.2 | CLI coding agent |
| oh-my-opencode-slim | 2.2.2 | Multi-agent pantheon |

## Vendor offline packages

```bash
# From repo root (requires network + npm)
bash scripts/vendor-opencode.sh

# Produces:
#   third_party/opencode/opencode-ai-*.tgz
#   third_party/oh-my-opencode-slim/oh-my-opencode-slim-*.tgz
#   third_party/opencode/VERSION
```

## Install

```bash
# Prefer vendored tarballs (offline / ISO)
bash scripts/install-opencode.sh

# Or online
npm install -g opencode-ai@1.18.2 oh-my-opencode-slim@2.2.2
```

## Starship preset

Config: `config/opencode/oh-my-opencode-slim.starship.json`

Install target: `/etc/starship/opencode/oh-my-opencode-slim.json`

Default models (local Ollama only):
- Orchestrator / Oracle → `Eve-V2-Unleashed`
- Explorer / Librarian / Designer / Fixer → `qwen2.5:7b`
