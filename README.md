# Qualia Residual RL

Phase 1 checkpoint for improving a frozen pi0.5 VLA through RLT inside
unmodified RLinf-VLA, wrapped by a small ENPIRE-inspired Policy Improvement
loop.

## Status

Phase 1 is complete and was exercised on an NVIDIA L40S against RLinf commit
`c90951a0c799a750cb5294ed10587c61cc2af8bf`. The loop launched a baseline,
read its logged loss and evaluation success, reduced RLT reference
regularization, launched an adjusted run, and reverted the change because
success did not improve.

This is an integration smoke result, not evidence about RLT performance. Both
20-step evaluations had `success_once=0.0`; lowering `bc_weight` from `1.0` to
`0.8` produced no meaningful difference.

D1 baseline work now lives on `experiment/d1-rlt-baseline`. Stages 0–4 and the
reduced-budget Stage-5A checkpoint are complete. The Stage-5B representative
A10 probe reached 22,598/23,028 MiB VRAM and failed while allocating the
256-environment camera group, before rollout; this is hardware-feasibility
evidence, not a policy result. Reference A and Control B remain unrun, and
Stage 6 is blocked until they provide comparable fixed-ID evidence.

## Three-phase plan

1. **Phase 1 — rule-based (current):** bounded RLinf runs, text metric
   normalization, one transparent tuning rule, and keep/revert.
2. **Phase 2 — coding-agent-driven:** an agent proposes config or code changes,
   with structured multi-run and branch comparison.
3. **Phase 3 — real hardware:** hardware rollout, reset, and verification after
   simulation results justify transfer.

The Phase-2 supervisor has now reached M5 engineering integration on branch
`feature/d2-agent-supervisor`: its guarded configuration-only backend can run
the full coordinator through real local subprocesses and normalize D1-shaped
artifacts. Those demonstrations are explicitly synthetic. Paid/live D1 runs
remain blocked until the reviewed Stage-7 evidence gate is ready.

M6 adds the code-enabled arm: an agent may change only a versioned
project-owned actor-objective function, and the harness requires a measurable
finite value/gradient change before execution. The three-seed subprocess demo
is synthetic; the exact PyTorch/RLinf attachment will be reconciled with the
separately owned D1 workstream.

M7 adds durable scheduling for independent hypotheses across independent
workers: capability filtering, conservative reservations, attempt leases,
heartbeat/restart recovery, cancellation, stale-result rejection, and a fixed
mockable SSH RPC client. Its two-worker demo is synthetic and makes no GPU or
RLT scaling claim.

M8 adds the frozen three-arm study: three discovery candidate experiments each
for a fixed rule, Claude configuration proposals, and Claude actor-objective
proposals; isolated per-arm incumbents; deterministic best-valid selection;
independent paired-seed confirmation; and reconciled static reports. Its
one-command rehearsal is synthetic. A live study and any arm-performance claim
remain blocked on the separately owned D1 Stage-7 evidence gate.

M9 packages M4, M7, and M8 into one offline-first Ludvig demo with a static
presentation, architecture visual, optional read-only D1 replay, stable-commit
proof, semantic delivery fingerprint, and independently verified artifact
manifest. Run it from a clean checkout:

```bash
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-ludvig-demo
python3 scripts/verify_m9_bundle.py \
  /tmp/enpire-m9-ludvig-demo
```

The final bundle is intentionally synthetic and permits no RLT-performance or
agent-superiority claim. See
[`docs/agent-supervisor/ludvig-demo-runbook.md`](docs/agent-supervisor/ludvig-demo-runbook.md)
for the meeting flow and fallback.

For a nontechnical audience, the companion real-policy demo trains a small
residual reacher on the CPU and runs its recorded one-setting proposal through
the same enforcement, Git isolation, worker evidence, and frozen evaluator
boundaries:

```bash
python3 scripts/run_real_policy_demo.py \
  --output /tmp/enpire-real-policy-demo
python3 scripts/verify_real_policy_demo.py \
  /tmp/enpire-real-policy-demo
```

This produces a visible, real improvement on the toy task only; it remains
explicitly non-RLT evidence. See
[`docs/agent-supervisor/real-policy-demo-presenter-guide.md`](docs/agent-supervisor/real-policy-demo-presenter-guide.md).

Phase 1 is deliberately a planned stand-in for ENPIRE's coding-agent Policy
Improvement module. It does not claim to reproduce that module.

## Repository layout

```text
qualia-residual-rl/
├── README.md
├── .gitignore
├── configs/
│   └── phase1_overrides.yaml
├── agent/
│   ├── rules.py
│   ├── metrics.py
│   └── policy_improvement.py
├── scripts/
│   └── run_phase1_loop.sh
├── results/
│   └── phase1_runs.jsonl
└── docs/
```

Additional files under `results/` preserve raw checkpoint evidence, and
`tests/` verifies the wrapper without requiring RLinf or a GPU.

## Phase 1 boundaries

[`configs/phase1_overrides.yaml`](configs/phase1_overrides.yaml) contains
exactly four documented experiment fields:

- `learning_rate` maps to RLinf `actor.optim.lr`.
- `regularization_strength` maps to `algorithm.bc_weight`.
- `training_iterations` bounds each RLinf run.
- `episode_steps` bounds the train/evaluation episode.

The current rule changes only learning rate or regularization, and only one at
a time. Low evaluation success relaxes regularization by 20%. A non-finite or
plateaued loss halves learning rate. The adjusted run is kept only if evaluation
success improves; otherwise the loop reverts to the baseline.

The Python modules have no RLinf imports. RLinf is launched as an external
process with Hydra overrides and remains unmodified.

## Setup and run

First install RLinf using its upstream embodied, OpenPI, and ManiSkill options.
Provide the checkout, model, and RLT-compatible dataset paths:

```bash
export RLINF_HOME=/workspace/qualia/RLinf
export MODEL_PATH=/root/qualia-assets/pi05_base
export DATASET_PATH=/workspace/qualia/assets/maniskill_smoke
scripts/run_phase1_loop.sh
```

`run_phase1_loop.sh` fails immediately if `RLINF_HOME` is missing. `MODEL_PATH`
and `DATASET_PATH` are also required. Optional variables are `RESULTS_ROOT`,
`SESSION_ID`, `PYTHON_BIN`, `RLINF_CONFIG_NAME`, and `RUN_TIMEOUT_SECONDS`.
`RLINF_CONFIG_NAME` keeps the launch boundary configurable while the checkpoint
uses the upstream ManiSkill example.

Each run retains its resolved command, raw log, normalized metrics, and summary.
The compact cross-run ledger is appended to
[`results/phase1_runs.jsonl`](results/phase1_runs.jsonl).

Run the dependency-free tests with:

```bash
python3 -m unittest discover -s tests -v
```

See [`docs/upstream-integration.md`](docs/upstream-integration.md) for the
validated upstream installation and smoke commands.

## Checkpoint result

| Run | `bc_weight` | Actor LR | Eval success | Actor loss | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Baseline | 1.0 | 1e-4 | 0.0 | -0.119 | Selected |
| Adjusted | 0.8 | 1e-4 | 0.0 | -0.109 | Reverted |

Honest conclusion: the adjustment produced no meaningful improvement in this
one-transition smoke. It validates the orchestration path only.

## Honestly flagged TODOs

- Save and use a trained Stage-1 RLT checkpoint; the smoke currently uses base
  pi0.5 as the feature-model input.
- Train longer and evaluate multiple episodes/seeds before interpreting a
  hyperparameter comparison.
- Replace the fallback text-log parser in `agent/metrics.py` with RLinf's stable
  structured metric artifact once its emitted path and schema are pinned.
- Confirm the long-term simulator with Qualia; ManiSkill is only the current
  upstream example, not a permanent architectural choice.
