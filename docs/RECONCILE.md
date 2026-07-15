# Reconcile notes — Alpha 2.1 monorepo

## Sources merged

1. **agnetic-os** (Alpha 2.0) — packaging, ISO, systemd, agneticctl, AppArmor, Proxy/Romi/Ergo, StarAgent
2. **WSL `/opt/agnetic`** (Alpha 2.1) — services under `src/python/services`, lib/dashboard under `src/python/lib`, cpp, plans, runbooks
3. **starship-os** — empty scaffold + CI; becomes canonical home

## Dual paths (temporary)

| Concern | 2.0 path | 2.1 path | Resolution |
|---------|----------|----------|------------|
| Dashboard | `dashboard/` :8899 | `src/python/lib/dashboard/` :8788 | Unify on 8788 in Phase 1 |
| Agents code | `agents/` | `src/python/lib/agent_daemon.py` | Prefer `src/python` as runtime; keep YAML in `agents/` |
| CLI name | `agneticctl` | `starshipctl` (planned) | Rename in Phase 1 |
| Install prefix | `/opt/agnetic` | `/opt/starship` | Symlink in 2.1 transitional |

## Not yet done (Phase 0.1+)

- [ ] Full `starship` branding rename in code
- [ ] NATS subject dual-publish `agnetic.*` / `starship.*`
- [ ] Vendor OpenCode + oh-my-opencode-slim pins
- [ ] Archive notice PR on agnetic-os README
