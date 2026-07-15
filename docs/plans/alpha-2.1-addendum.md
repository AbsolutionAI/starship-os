# Alpha 2.1 Addendum — OpenCode, Models, GitHub

## OpenCode + oh-my-opencode-slim

**Upstream:** https://github.com/alvinunreal/oh-my-opencode-slim  
**Ship:** OpenCode CLI + slim plugin vendored/pinned under `third_party/` for offline ISO.

### Pantheon (dev / feature integration)

| Agent | Starship local model (default) |
|-------|--------------------------------|
| Orchestrator | Eve-V2-Unleashed |
| Fixer / Explorer | qwen2.5:7b or granite4.1-3b |
| Oracle | qwen35-claude-coder (if VRAM) else Eve |
| Librarian | granite4.1-3b / fast |
| Math tasks | qwen2-math:7b |

Config path: `/etc/starship/opencode/oh-my-opencode-slim.json`  
Policy: only coding/ops agents; red-team never unrestricted OpenCode.

**Separation of concerns:** OpenCode pantheon ≠ NATS mesh agents. Mesh = control plane; OpenCode = feature review / coding.

## Eve-V2-Unleashed

| Item | Value |
|------|-------|
| Alias | `Eve-V2-Unleashed` |
| Upstream | `jeffgreen311/Eve-V2-Unleashed-Qwen3.5-8B-Liberated-4K-4B-Merged:latest` |
| Server `num_ctx` | **16384** |
| Edge | 8192 |
| Ops (VRAM+) | 32768 |
| Size | ~3.4 GB |

Create: `ollama create Eve-V2-Unleashed -f config/models/Eve-V2-Unleashed.Modelfile`

Security: abliterated model — mandatory policy + sandbox + Droid Shield.

## Optional model pack

See `config/models.yaml`. Required: nomic-embed-text + Eve (server). Others hardware-gated.

## GitHub workflow

- Canonical: `andromi-hash/starship-os`
- Legacy archive: `andromi-hash/agnetic-os` (README points here)
- Tags: `v2.1.0-alpha.1`, …
- Auth: `gh auth login` only; never commit tokens
