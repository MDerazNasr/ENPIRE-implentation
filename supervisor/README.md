# Coding-Agent Supervisor

This dependency-light package implements the audited, bounded outer loop around
RLT experiments. Milestones M0-M9 and the companion real CPU policy demo are
complete. Exact live objective and SSH/GPU attachment remain D1 compatibility
work; the supervisor implementation has not yet launched a paid model, GPU,
SSH connection, W&B API, or RLinf training process.

## Implemented layers

- `canonical.py`, `contracts.py`, `state.py`, `ledger.py`, and `budget.py`:
  versioned records, deterministic hashes, lifecycle enforcement, and budgets.
- `context.py`, `proposals.py`, `providers.py`, and `attempts.py`: compact agent
  context, tool-free structured proposals, and one bounded repair.
- `enforcement.py` and `git_manager.py`: independent policy checks and an
  isolated branch/worktree for each hypothesis.
- `workers.py`: provider-neutral immutable run contracts and an idempotent fake
  worker.
- `evaluation.py`: the frozen D1 numerical decision adapter and atomic per-arm
  incumbent pointers.
- `coordinator.py`: offline composition from accepted proposal through terminal
  evidence and `KEEP`, `REVERT`, `INCONCLUSIVE`, or `FAILED`.
- `objective_adapter.py` and `objectives/actor_objective.py`: a project-owned,
  narrowly editable actor-objective boundary with default-equivalence tests.
- `objective_validation.py`: the versioned M6 objective ABI, strict source
  contract, isolated value/gradient proof, and no-op rejection.
- `scheduler.py`: M7 worker capabilities, durable queue, conservative budgets,
  leases, heartbeat/recovery, concurrent dispatch, cancellation, and strict
  completion reconciliation.
- `ssh_worker.py`: fixed, mockable SSH RPC client implementing the existing
  worker interface without accepting agent-controlled commands.
- `reporting.py`: canonical JSON, CSV, Markdown, and static HTML reports.
- `d1_gate.py`: strict Stage-7 pack, read-only repository audit, evidence
  normalization, and legacy-versus-supervisor decision replay.
- `d1_pack_builder.py`: deterministic readiness reporting and fail-closed
  publication with computed hashes for all seven Stage-7 artifact roles.
- `d1_backend.py`: authorization-gated config planning, local D1 subprocess
  execution, manifest/log normalization, and the coordinator worker adapter.

Run the complete offline demonstration from the repository root:

```bash
demo_dir="$(mktemp -d /tmp/enpire-m4-demo.XXXXXX)"
python3 scripts/run_m4_offline_demo.py --output "$demo_dir"
```

Every report is prominently marked **SYNTHETIC OFFLINE DEMONSTRATION — NOT
RESEARCH EVIDENCE**. M5/M6 also exercise D1-shaped artifacts and a genuine
objective-code delta through real local fixture subprocesses. Live D1
execution, real RLinf objective wiring, SSH/GPU workers, and scientific
comparisons remain integration/later work.

Run the M7 synthetic two-worker loss/retry demo outside the repository:

```bash
demo_dir="$(mktemp -d)/m7-demo"
python3 scripts/run_m7_scheduler_demo.py --output "$demo_dir"
```

Its JSON artifact is explicitly labeled synthetic and includes concurrency,
retry, stale-result, evaluator, incumbent, and stable-HEAD evidence.

Audit the live D1 gate without modifying the baseline worktree:

```bash
python3 scripts/check_d1_integration_gate.py --d1-repository /path/to/d1-repo
```

Exit code `0` means the exact pack and replay are ready. Exit code `2` means
blocked or invalid; the JSON output contains every reason. On 2026-09-02 the
current D1 worktree returned `blocked` because it was dirty and the canonical
`results/d1-stage7/evidence_pack.json` was absent. D1's newer Stage-7 directory
and one-seed result do not yet satisfy the matched three-seed pack contract.
