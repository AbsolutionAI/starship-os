# Flamingo Fleet

Deploy, orchestrate and manage Flamingo micro-agents across remote hosts / fleet.

## Capabilities
- Deploy Flamingo-stack agents to target machines (SSH or preauth)
- Manage remote fleets: status, update, task dispatch
- Non-sluggish control: use lightweight commands + NATS bridge
- Failover and scaling of micro-agent pods
- Skills for cluster ops, backup, monitoring on remote nodes

## Usage
- "deploy flamingo to host 192.168.1.50"
- "flamingo fleet status"
- "orchestrate remote backup via flamingo"

## Dependencies
- Flamingo binaries / installers (opt-in)
- SSH / remote exec (sandbox aware)
- NATS for cross-host comms
- LanceDB for fleet state
