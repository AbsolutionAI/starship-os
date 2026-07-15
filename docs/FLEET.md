# Starship OS — Fleet, Plants, Ops Manager, Red/Blue

**Status:** Alpha 2.1 scaffold  
**Config:** `config/fleet.yaml`  
**Service:** `services/fleet.py`  
**CLI:** `starshipctl fleet …`

## Model

```
Fleet
 ├── Ops Manager (aggregates status on starship.fleet.ops.*)
 ├── Plant Alpha     (production mesh)
 ├── Plant Edge      (thin nodes)
 └── Plant Range     (red/blue exercise, isolated)
       ├── red-team roles
       └── blue-team roles
```

| Concept | Meaning |
|---------|---------|
| **Fleet** | Named multi-plant deployment |
| **Plant** | Site/zone with profile + allowed roles |
| **Ops manager** | Node that publishes fleet summary heartbeats |
| **Red team** | Offensive exercise role (restricted tools) |
| **Blue team** | Defensive exercise role |

Cluster mesh (`services/cluster.py`) remains the low-level node/task router.  
Fleet is the **topology + exercise** control plane on top.

## NATS subjects (dual-publish)

| Subject | Purpose |
|---------|---------|
| `starship.fleet.register` | Node registration |
| `starship.fleet.heartbeat` | Node heartbeat |
| `starship.fleet.status` | Node status snapshot |
| `starship.fleet.ops.status` | Ops manager aggregate |
| `starship.fleet.exercise` | Exercise start/stop events |

Legacy `agnetic.fleet.*` is dual-published for Alpha 2.0 clients.

## CLI

```bash
starshipctl fleet status
starshipctl fleet plants
starshipctl fleet register
starshipctl fleet nodes
starshipctl fleet exercise start
starshipctl fleet exercise stop
starshipctl fleet exercise status

# or directly
python3 services/fleet.py daemon
```

## Node override

`/etc/starship/fleet-node.yaml`:

```yaml
node:
  plant: plant-edge
  roles: [proxy, plant-controller]
  team: ops
  profile: edge
```

## Red/blue policy notes

- Exercises default to `plant-range` (`isolation: true`).
- Red-team never gets unrestricted OpenCode (see `docs/plans/alpha-2.1-addendum.md`).
- Cross-plant red traffic denied by default (enforce in policy engine Phase 2).

## Next

- Wire fleet register into `install-daemon` / firstboot
- Dashboard plant map panel
- Policy engine enforcement for red-team toolsets
