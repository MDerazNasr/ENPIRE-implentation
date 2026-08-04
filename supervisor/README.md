# Supervisor Foundation

This dependency-free package implements the version-1 contracts established in
Milestone 1. It does not call Claude, Git, SSH, W&B, RLinf, or GPUs.

## Modules

- `canonical.py`: deterministic JSON, hashing, timestamps, decimals, IDs, and
  safe relative paths.
- `contracts.py`: campaign, approval, artifact, trial-evidence, and decision
  records.
- `state.py`: separate campaign and trial transition tables.
- `ledger.py`: locked, fsynced, hash-chained JSONL events and replay.
- `budget.py`: decimal-safe preflight and actual-usage accounting.

The public wire contract is documented in
[`../docs/agent-supervisor/contracts.md`](../docs/agent-supervisor/contracts.md).
The fixture under `examples/supervisor/` is deliberately non-executable.

All loaders reject unknown fields and unsupported schema versions. Later
milestones should extend contracts by adding a new version, not by silently
changing version 1.
