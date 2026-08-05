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

## D1 Stage-5B baseline gate — 2026-08-04

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA L40S, 46,068 MiB usable VRAM, `$0.99/hour`
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Evaluation: 256 fixed reset-state IDs, 500-step horizon, seed 2026
- Execution batching: 16 train environments x 4 epochs; 16 evaluation
  environments x 16 epochs

| Run | Policy route | Train success | Eval success | RLT updates | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `stage5b-l40s-batched16-probe-seed2026-20260804` | Scratch residual actor | `0/64` | `1/256` | `0` | Degenerate probe |
| `stage5b-reference-a-l40s-seed2026-20260804-r2` | Frozen Stage-1 reference | `0/64` | `0/256` | Not applicable | Degenerate reference |

The residual probe recorded only 41 replay transitions against the unchanged
10,000-transition warm-up threshold, so neither actor nor critic trained.

**Honest result:** the L40S profile proves reproducible RLinf/RLT execution,
but the reduced-budget Stage-1 checkpoint and one-step scratch-RLT probe do not
provide a meaningful success signal. Stage 6 was not launched.

Artifacts: `results/stage5b-l40s/`.
Reference-A W&B run: [fmfb666c](https://wandb.ai/mderaznasr-n-a/qualia-rlt-d1/runs/fmfb666c).

## D1 Stage-5C checkpoint gate — 2026-08-04

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA RTX PRO 6000 Blackwell Server Edition, `$1.99/hour`
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Stage-1 horizon: 500 optimizer steps, seed 2026
- Evaluation: 256 fixed reset-state IDs, 500-step horizon

| Run | Policy route | Train success | Eval success | RLT updates | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `stage5c-step500-reference-a-seed2026-20260804` | Frozen step-500 reference | `6/64` (`9.38%`) | `33/256` (`12.89%`) | Not applicable | Checkpoint selected |

The run completed in 1,494.47 seconds and cost `$0.8261`; peak sampled VRAM
was 26,286 MiB. Policy switching was disabled and actor/critic update counts
were zero, so this is a clean frozen-reference measurement.

**Honest result:** extending the budget-limited Stage-1 model to 500 steps
produced a non-degenerate but still low `12.89%` fixed-set success rate. This
is sufficient to select the checkpoint for a bounded Stage-2 baseline, but it
is not evidence of Stage-2 RLT improvement and is not equivalent to upstream
2,000-step Stage-1 training.

Detailed evidence: `docs/stage5c-500-checkpoint.md`.
