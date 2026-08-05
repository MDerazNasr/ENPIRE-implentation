# Stage 5A Reduced-Budget Stage-1 Checkpoint

Status: complete on 2026-08-04. This is a 250-step discovery checkpoint, not
the upstream-complete 2,000-step Stage-1 training contract.

## Contract

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Task data: all 400 official successful ManiSkill episodes, 28,681 frames.
- Frozen base model: official pi0.5, 14,467,165,872 bytes.
- Seed: 2026.
- Hardware: NVIDIA L40S, 46,068 MiB usable VRAM, `$0.99/hour`.
- Micro/global batch: 2/256, or 128 micro-batches per optimizer step. This
  recovery deviation preserved the effective global batch and objective.
- Optimizer steps: 250; one final checkpoint at step 250.
- Learning rate: `2.5e-5`; upstream FP32 objective and data semantics retained.
- W&B ran offline; its final summary is retained in the raw run log.

## Result

RLinf completed all 250 optimizer steps and exited zero.

| Signal | Final/observed value |
| --- | ---: |
| Total training loss | 1.07697 |
| RLT loss | 1.04738 |
| VLA loss | 0.02959 |
| Gradient norm | 0.277 |
| Elapsed launcher time | 16,892.41 seconds (4.69 hours) |
| Launcher-attributed cost | `$4.6454` at `$0.99/hour` |
| Peak sampled VRAM | 45,521 MiB |

Loss decreased over this bounded training run, but loss alone is not policy
success evidence. The subsequent Reference-A evaluation was `0/256`, confirming
that this checkpoint does not provide a non-degenerate task-success baseline.

## Checkpoint preservation

The complete checkpoint was first saved in RAM-backed storage. Its inference
actor was then copied to persistent storage and verified byte-for-byte:

- Path:
  `/workspace/qualia-checkpoints/stage5a-step250/actor/model_state_dict/full_weights.pt`
- Size: 10,015,912,759 bytes.
- SHA-256:
  `0a13b97b264d78fbecb959653c5462a25fc2f0f18c4eecb932029fd0dade60df`.

The full distributed checkpoint was created in RAM-backed storage. Its
10,015,912,759-byte inference actor was copied to persistent storage and hashed
before the reinstallable optimizer/checkpoint data was reclaimed.

Compact command, manifest, resource samples, full run log, and preservation
record are under
`results/stage5a-l40s/stage5a-full/`.

## Stage gate

Stage 5A is complete. The later Stage-5B resource probe and Reference A also
completed, but the baseline was degenerate. Do not start Stage 6 until an
explicitly revised protocol produces a trained, non-degenerate Control B.
