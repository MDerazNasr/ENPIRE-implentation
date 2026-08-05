# Stage 5C 500-Step Checkpoint Gate

Status: complete on 2026-08-04. The 500-step Stage-1 checkpoint produced a
non-zero fixed-set Reference-A result and is selected for the next bounded
Stage-2 baseline. It remains a budget-limited discovery checkpoint, not the
upstream-complete 2,000-step Stage-1 model.

## Training contract

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Task data: all 400 official successful ManiSkill episodes.
- Frozen base model: official pi0.5, 14,467,165,872 bytes.
- Seed: 2026.
- Hardware: NVIDIA RTX PRO 6000 Blackwell Server Edition, 97,887 MiB visible
  VRAM, `$1.99/hour`.
- Optimizer steps: 500; final complete checkpoint at step 500.
- Learning rate: `2.5e-5`.
- W&B mode: offline; local logs are the authoritative evidence.

## Training result

| Signal | Final/observed value |
| --- | ---: |
| Total training loss | 0.557 |
| RLT loss | 0.540 |
| VLA loss | 0.0173 |
| Elapsed launcher time | 13,939.57 seconds (3.87 hours) |
| Launcher-attributed cost | `$7.7055` |

The loss values show that the supervised objective continued to optimize, but
the checkpoint was selected on task-success evidence rather than loss alone.

## Checkpoint verification

- Persistent actor path:
  `/workspace/qualia/ENPIRE/results/d1/stage5c-500-seed2026-20260804/maniskill_rlt_stage1_sft_openpi_pi05/checkpoints/global_step_500/actor`
- Full actor size: 10,015,912,662 bytes.
- Distributed checkpoint shard size: 30,052,399,740 bytes.
- Actor SHA-256:
  `c7796339ad8d82c287d6f2f7ae9e7790ff25a5d50f49012dbd7673d2f0250468`.

## Reference-A evaluation

The checkpoint was loaded by unmodified RLinf Stage 2 with residual policy
switching disabled. The run first executed 64 separate training-route
trajectories, then evaluated the frozen reference on the preregistered 256
fixed reset-state IDs.

| Split | Success | Mean episode length | Mean reward |
| --- | ---: | ---: | ---: |
| Training route | `6/64` (`9.375%`) | 460.516 | 0.001317 |
| Fixed evaluation | `33/256` (`12.890625%`) | 447.289 | 0.001580 |

Evaluation run:
`stage5c-step500-reference-a-seed2026-20260804`.

- Exit code: 0.
- Elapsed time: 1,494.47 seconds (24.91 minutes).
- Launcher-attributed cost: `$0.8261`.
- Peak sampled VRAM: 26,286 MiB (25.67 GiB).
- Actor and critic updates: zero, as required for Reference A.
- Replay transitions recorded: zero, as required with policy switching off.
- Stage-5C cumulative launcher ledger after evaluation: approximately
  `$8.77`; the `$10` threshold was not crossed.

The measured 25.67 GiB allocation means this exact 16-environment Stage-2
profile does not fit a strict 24 GB device without an additional memory-saving
change. This is a measured configuration constraint, not a claim that VLA
inference alone requires more than 24 GB.

## Gate decision

Select the step-500 checkpoint and do not extend Stage 1 to 1,000 steps yet.
The fixed evaluation is non-degenerate and therefore answers the checkpoint
viability question. The next cheaper, decision-relevant experiment is a
bounded Stage-2 Control-B readiness run using this checkpoint.

This decision does not claim that 12.89% is good task performance, nor that the
checkpoint matches the upstream 2,000-step training contract. It only confirms
that the checkpoint can support a measurable Stage-2 baseline.

Stage 6 remains blocked until Control B actually crosses its unchanged replay
warm-up, performs actor and critic updates, and produces matched fixed-set
evidence. A one-step plumbing smoke with zero updates is not sufficient.
