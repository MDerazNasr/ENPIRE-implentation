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

D1 baseline work now lives on `experiment/d1-rlt-baseline`. Its Stage-0
scientific contract and Stage-1 no-GPU infrastructure define separate
pilot/reference/control/candidate profiles, fixed-ID evaluation, immutable
provenance, cumulative cost gates, and an explicitly acknowledged launch path.
No D1 paid run or performance baseline has started yet.

## Three-phase plan

1. **Phase 1 — rule-based (current):** bounded RLinf runs, text metric
   normalization, one transparent tuning rule, and keep/revert.
2. **Phase 2 — coding-agent-driven:** an agent proposes config or code changes,
   with structured multi-run and branch comparison.
3. **Phase 3 — real hardware:** hardware rollout, reset, and verification after
   simulation results justify transfer.

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
