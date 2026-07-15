# Starship OS Architecture Overview (Alpha 2.1)

## What this is

Starship OS is an **AI agent-first operating system layer** on **Ubuntu 24.04 LTS**.  
It is not a forked Linux kernel. It is a system-level agent mesh + packaging + optional ISO.

## High-level stack

```
Operator UI:  Web C2 dashboard · starshipctl · optional GNOME Ops Console · OpenCode
     │
Agent mesh:   NATS/JetStream bus · agent daemons · skills/souls · workflows
     │
Services:     policy · hooks · shield · accounts · memory · telemetry · healer · email · incidents
     │
Inference:    Ollama (Eve-V2-Unleashed default) · optional multi-model pack
     │
OS:           Ubuntu 24.04 · systemd · AppArmor · cgroups
```

## Runtime paths (target)

| Path | Purpose |
|------|---------|
| `/opt/starship` | Application install |
| `/etc/starship` | Config (policy, models, hooks) |
| `/var/lib/starship` | State (memory, accounts, healer) |
| `/var/log/starship` | Logs |

Alpha 2.1 WSL may still use `/opt/agnetic` — compat symlink planned.

## Source layout (this monorepo)

| Path | Content |
|------|---------|
| `src/python/services/` | 2.1 service modules (policy, memory, …) |
| `src/python/lib/` | agent_daemon, tools, dashboard |
| `src/cpp/` | vector_index C++ module |
| `src/c/` | Future C11 runtime (skeleton) |
| `agents/` `skills/` `souls/` | Declarative agent definitions |
| `agneticctl/` | CLI (rename target: starshipctl) |
| `agent/` | StarAgent Rust telemetry |
| `packaging/` `debian/` `iso/` `systemd/` | Install & ISO |
| `docs/` | Architecture, plans, guides |
| `config/` | models.yaml, hooks |

## Ports (default)

| Service | Port |
|---------|------|
| NATS | 4222 |
| Ollama | 11434 / 11435 (WSL) |
| Dashboard (2.1 C2) | 8788 |
| Dashboard (2.0 legacy) | 8899 |

Unify on **8788** in 2.1 final packaging.

## Security boundary

Tool exec → sandbox + policy + PreToolUse hooks + Droid Shield redaction.  
Service accounts for agent identity. Red-team toolset lab-only.
