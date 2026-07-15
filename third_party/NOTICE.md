# Third-party components (Starship OS)

## Planned / integrated OSS

| Component | License | Use |
|-----------|---------|-----|
| [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) | MIT | OpenCode multi-agent suite (shipped) |
| OpenCode | See upstream | Coding agent CLI |
| [Slermes](https://github.com/waefrebeorn/slermes) | See upstream | Architecture inspiration (C11 agent) — not vendored |
| Ollama | MIT | Local inference |
| NATS | Apache-2.0 | Message bus |
| Eve-V2-Unleashed (Ollama model) | Upstream model card | Default reasoning weights |

Pin exact versions in `third_party/pins.json` when packaging.

## Attribution

Starship OS builds on community open source. Full license texts to be collected under `third_party/licenses/` at package freeze.
