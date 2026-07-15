# Starship OS — Ubuntu autoinstall profiles

Cloud-init **autoinstall** user-data for unattended Ubuntu 24.04 installs.
Profiles match `config/profiles.yaml`: **edge**, **server**, **ops**.

## Usage

```bash
# Serve user-data during netboot / virt-install, or embed in ISO
# Example (qemu + cloud-init seed):
cloud-localds seed.img meta-data user-data.server.yaml
```

| File | Profile | Intent |
|------|---------|--------|
| `user-data.edge.yaml` | edge | Thin node, small models, minimal services |
| `user-data.server.yaml` | server | Default mesh + Eve-V2 |
| `user-data.ops.yaml` | ops | Full mesh + coding models, larger disk |

## Post-install / firstboot

Late-commands write `/etc/starship/firstboot.env` + `profile.yaml`, then invoke:

```bash
STARSHIP_PROFILE=<edge|server|ops> /opt/starship/bin/starship-firstboot.sh
```

| Profile | NATS (firstboot) | Notes |
|---------|------------------|-------|
| edge | agent-bus | thin node |
| server | agent-bus | default mesh |
| ops | multi-tenant accounts | optional `STARSHIP_NATS_TLS=1` |

Static smoke (no QEMU): `bash scripts/iso-firstboot-smoke.sh`  
Full ISO: `scripts/test-iso.sh` / `scripts/build-iso.sh`

`starship-firstboot.sh` selects profile, fleet register, NATS mode, enables mesh.
