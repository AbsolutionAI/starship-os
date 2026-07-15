# Module Catalog (Alpha 2.1 stub)

Generate full API docs in Phase 0.1. Current inventory:

## Python services (`src/python/services/`)

| Module | Purpose |
|--------|---------|
| `memory.py` | 7-type memory + LanceDB vector search |
| `policy.py` | Hierarchical policy + CommandBlocklist |
| `event_hooks.py` | Lifecycle hooks (exit-code block) |
| `droid_shield.py` | Secret scanning |
| `service_accounts.py` | API key identities |
| `telemetry.py` | OTEL / JSONL export |
| `incident_response.py` | Runbook-as-code |
| `agent_email.py` | SMTP + Mailchain |
| `healer.py` | Self-healing heartbeats |
| `onboarding.py` | First-run wizard |
| `agent_discovery.py` | NATS live agent discovery |
| `governance.py` | Action approval |
| `provider_router.py` | Multi-LLM routing |
| `checkpoint.py` | FS snapshots |
| `browser.py` | Playwright automation |
| `mcp.py` | MCP servers |
| `context_loader.py` | Context file discovery |
| `credential_pool.py` | Credential pools |
| `skills_hub.py` | Skills marketplace |

## Core runtime (`src/python/lib/`)

| Module | Purpose |
|--------|---------|
| `agent_daemon.py` | NATS agent loop + tools + healer hook |
| `tools.py` | 43 tools / 20 toolsets |
| `dashboard/` | Web C2 (port 8788) |
| `plugin_manager.py` | Plugins |
| `scheduler.py` | Cron / schedules |
| `workflows.py` | Multi-agent workflows |

## Native / other

| Path | Purpose |
|------|---------|
| `src/cpp/vector_index.cpp` | Embedding normalize/pool (pybind11) |
| `agneticctl/` | Go CLI |
| `agent/` | Rust StarAgent telemetry |
| `security/apparmor/` | AppArmor profiles |
