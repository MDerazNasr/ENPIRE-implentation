# Benchmark log

## Phase 1 checkpoint — 2026-07-16

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA L40S, 46 GB usable VRAM
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Budget per run: one 20-step training episode, one actor/critic update, and one
  20-step evaluation episode
- Primary comparison metric: evaluation `success_once`

| Run | Config | Success | Actor loss | BC loss | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `run_000_baseline` | LR `1e-4`, `bc_weight=1.0` | 0.0 | -0.119 | 0.064 | Selected |
| `run_001_adjusted` | LR `1e-4`, `bc_weight=0.8` | 0.0 | -0.109 | 0.067 | Reverted |

The wrapper triggered because baseline success was below the `0.85` target and
reduced reference regularization by 20%. The adjusted run did not improve
success, so the keep-or-revert rule restored the baseline configuration.

**Honest result:** reducing `bc_weight` from `1.0` to `0.8` produced no
meaningful difference in this one-transition smoke test; both evaluations had
zero success.

The actor losses are recorded for observability but are not used to break the
success tie because changing `bc_weight` changes the actor objective itself.
These runs validate orchestration and logging only; they are not a performance
claim.

Artifacts: `results/checkpoint-20260716c/`.
