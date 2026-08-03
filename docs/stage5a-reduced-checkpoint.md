# Stage 5A Reduced-Budget Stage-1 Checkpoint

Status: complete on 2026-08-03. This is a 250-step discovery checkpoint, not
the upstream-complete 2,000-step Stage-1 training contract.

## Contract

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Task data: all 400 official successful ManiSkill episodes, 28,681 frames.
- Frozen base model: official pi0.5, 14,467,165,872 bytes.
- Seed: 2026.
- Micro/global batch: 8/256, or 32 micro-batches per optimizer step.
- Optimizer steps: 250; one final checkpoint at step 250.
- Learning rate: `2.5e-5`; upstream FP32 objective and data semantics retained.
- W&B ran offline; local run ID `cchhttcn`.

## Result

RLinf completed all 250 optimizer steps and exited zero.

| Signal | Final/observed value |
| --- | ---: |
| Total training loss | 1.08 |
| RLT loss | 1.05 |
| VLA loss | 0.0298 |
| Gradient norm | 0.287 |
| Elapsed launcher time | 5,257.78 seconds (87.63 minutes) |
| Launcher-attributed cost | `$4.8050` at `$3.29/hour` |
| Peak sampled VRAM | 55,439 MiB |
| Peak inferred host RAM | 168.12 GiB |

Loss decreased over this bounded training run, but loss alone is not policy
success evidence. Reference-A and Control-B fixed-ID evaluations are still
required before any performance or improvement claim.

## Checkpoint preservation

The complete checkpoint was first saved in RAM-backed storage. Its inference
actor was then copied to persistent storage and verified byte-for-byte:

- Path:
  `/workspace/qualia-checkpoints/stage1-step250/actor/model_state_dict/full_weights.pt`
- Size: 10,015,912,759 bytes.
- SHA-256:
  `26995a81d44f2c035e4da40ccdbbeab65552d390d402f0594fa746e975d4b018`.

The pod's 19 GB persistent volume could not hold both RLinf's environment and
the actor. After training completed and the RAM source was hashed, the
reinstallable remote `.venv` was removed to preserve the trained actor. RLinf
source and its pinned commit remain recorded, but the environment must be
reinstalled if this pod is reused.

Compact command, manifest, resource samples, full run log, and preservation
record are under
`results/stage5a-h100/stage5a-stage1-250-seed2026-20260803/`.

## Stage gate

Stage 5A is complete. Stage 5 is not yet complete: next run a representative
Stage-2 resource/cost probe, then evaluate Reference A and train/evaluate
Control B on the identical fixed reset IDs. Do not start Stage 6 until that
baseline is non-degenerate and comparable.
