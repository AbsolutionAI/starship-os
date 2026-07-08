# Starship OS Architecture

A native AI operating system for complex system control. AI agents are first-class system services communicating via a NATS/JetStream message bus.

## Philosophy

- **Agent-Native**: AI agents are first-class citizens of the OS
- **Specialization**: Each subsystem has a dedicated agent with focused capabilities
- **Learning**: Agents improve through experience, creating and refining skills autonomously
- **Local-First**: All intelligence runs locally via Ollama; cloud providers optional
- **Bus-Oriented**: Agents communicate asynchronously via NATS/JetStream subjects

## Architecture

```
User/Opencode
    │
    ▼
┌─────────────────────────────────────┐
│         Hermes Orchestrator         │
│   (central coordinator, routing)    │
└──────────┬──────────┬───────────────┘
           │          │
    ┌──────▼──┐  ┌────▼──────┐
    │  Proxy  │  │   Romi    │
    │ (tech)  │  │ (client)  │
    └──────┬──┘  └────┬──────┘
           │          │
    ┌──────▼──────────▼──────┐
    │    NATS/JetStream Bus   │
    │  starship.agent.*.*     │
    │  starship.telemetry.*   │
    └──────┬──────────┬──────┘
           │          │
    ┌──────▼──┐  ┌────▼──────┐
    │ StarAgent│  │   Ergo    │
    │ (Rust)   │  │ (auto)    │
    └─────────┘  └───────────┘
```

## Agents

### Proxy (Tech Agent)
- System diagnostics, troubleshooting, log analysis
- Resource monitoring and alerting
- File system and process queries
- Model: qwen2.5:7b

### Romi (Client Agent)
- User-facing natural language interface
- Task explanation and status reporting
- Preference management and user modeling
- Model: qwen2.5:7b

### Ergo (Automation Agent)
- Scheduled tasks and cron workflows
- Event-triggered automations
- Backup and maintenance routines
- Model: Eve-V2 (3.4B)

### StarAgent (Rust)
- Cross-platform system metric collection
- Reports to NATS: cpu, mem, disk, net telemetry
- Low-level system monitoring daemon

## Communication

### NATS Subjects
- `starship.agent.proxy.command.<cmd>` — Proxy directives
- `starship.agent.proxy.event.<event>` — Proxy events
- `starship.agent.proxy.status` — Proxy health status
- `starship.agent.romi.command.<cmd>` — Romi directives
- `starship.agent.romi.event.<event>` — Romi events
- `starship.agent.romi.status` — Romi health status
- `starship.agent.ergo.command.<cmd>` — Ergo directives
- `starship.agent.ergo.event.<event>` — Ergo events
- `starship.agent.ergo.status` — Ergo health status
- `starship.telemetry.cpu` — CPU metrics
- `starship.telemetry.mem` — Memory metrics
- `starship.telemetry.disk` — Disk metrics
- `starship.telemetry.net` — Network metrics

## Tech Stack

- **Hermes Agent v0.18.2** — Agent framework with self-improvement loop
- **Ollama v0.31.1** — Local LLM inference (CUDA, RTX 4050 5.6 GB VRAM)
- **Qwen2.5:7b** — Primary local model (4.7 GB)
- **Eve-V2 (3.4B)** — Secondary local model for automation (3.4 GB)
- **NATS v2.10.7** — Agent communication bus
- **Go 1.22** — Starship CLI
- **Rust 1.96** — StarAgent system monitor
- **Opencode** — Development interface

## Directory Structure

```
starship-os/
├── cli/                    # Starship CLI (Go/Cobra)
├── agent/                  # StarAgent (Rust)
├── agents/                 # Hermes Agent YAML configs
├── skills/                 # Hermes Agent skills
├── nats/                   # NATS/JetStream configuration
├── docs/                   # Documentation
├── CLAUDE.md               # AI tool configuration
└── README.md
```

## Development Roadmap

1. [x] Foundation: Hermes Agent + Ollama installed
2. [x] Skills: System Health, Knowledge Store
3. [x] Models: qwen2.5:7b + Eve-V2 pulled
4. [x] Hermes configured for local Ollama
5. [x] Dev toolchain: NATS, Go, Rust installed
6. [ ] NATS agent bus: wired and tested
7. [ ] Proxy/Romi/Ergo agents: configured and connected
8. [ ] Starship CLI: Go/Cobra bootstrap commands
9. [ ] StarAgent: Rust system monitor
10. [ ] Distribution: Build as custom Linux ISO
