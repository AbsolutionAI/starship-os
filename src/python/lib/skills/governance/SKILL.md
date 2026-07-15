# Governance

Central oversight layer for agent actions, approvals, safety and fleet.

## Capabilities
- Pre-execution checks using evaluator, hitl, kill-switch
- Log decisions to long-term memory
- Approve/reject Flamingo deploys and high-risk ops
- Status reporting for bridge officers

## Usage
- "governance status"
- High risk commands auto route through gov

## Dependencies
- services/governance.py
- hitl, evaluator, kill_switch, memory
