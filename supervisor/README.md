# Coding-Agent Supervisor

This dependency-light package implements the audited, bounded outer loop around
RLT experiments. Milestones 1–4 are complete on this branch. M4 execution is
strictly synthetic: it calls no paid model, GPU, SSH worker, W&B API, or RLinf
training process.

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
- `reporting.py`: canonical JSON, CSV, Markdown, and static HTML reports.

Run the complete offline demonstration from the repository root:

```bash
demo_dir="$(mktemp -d /tmp/enpire-m4-demo.XXXXXX)"
python3 scripts/run_m4_offline_demo.py --output "$demo_dir"
```

Every report is prominently marked **SYNTHETIC OFFLINE DEMONSTRATION — NOT
RESEARCH EVIDENCE**. The D1 replay gate, real RLinf objective wiring, paid-agent
execution, W&B reconciliation, SSH/GPU workers, and scientific comparisons
remain later milestones.
