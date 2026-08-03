# Stage 4 Stage-2 Contract Smoke

Status: complete on 2026-08-03. This is integration evidence only and makes no
policy-performance claim.

## Execution placement

The intended A10 was connected and idle, but its cross-provider checkpoint
copy was only 1,109,622,784 bytes rather than the verified 10,015,912,759-byte
actor weights. Loading that file would have been invalid. Because the measured
transfer route would have billed both machines for hours, the bounded smoke
was run beside the verified checkpoint on the still-running external H100.
The incomplete A10 file was deleted afterward.

## Contract and provenance

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Stage-1 actor: `global_step_5`, actor-weight SHA-256
  `6b57b89beeaa4a6d5ee30f1a94caa7fc7cacbf9a7c8f9ef6c6043eeab302a7cf`.
- Task: `PegInsertionSideWideClearance-v1`, GPU simulation, seed 2026.
- One training environment, one fixed-ID evaluation environment, one 20-step
  trajectory each, one actor update, one critic update, and no checkpoint save.
- Expert takeover disabled; actor/reference switching forced on for the
  integration path; schedule disabled as declared by the smoke profile.
- W&B ran offline. The local run ID is `e8vaj71i`.

## Result

RLinf exited zero after completing rollout, replay insertion, actor/critic
training, weight synchronization, and fixed-ID evaluation.

| Signal | Value |
| --- | ---: |
| Train `success_once` | 0.0 |
| Eval `success_once` | 0.0 |
| Episode length | 20 |
| Actor updates | 1 |
| Critic updates | 1 |
| Actor loss | 0.310 |
| Critic loss | 0.0050 |
| BC loss | 0.055 |
| Actor gradient norm | 11.117 |
| Peak sampled VRAM | 15,838 MiB |
| Peak inferred host RAM | 167.92 GiB |
| Launcher elapsed time | 190.60 seconds |
| Launcher-attributed cost | `$0.1742` at `$3.29/hour` |

The zero success is expected for a single 20-step smoke trajectory and is not
evidence that RLT succeeded or failed. Peak sampled VRAM indicates the Stage-2
runtime itself should fit a 24 GB A10 once a complete checkpoint is locally
available; this run did not validate A10 execution because it ran on H100.

## Evidence and stage gate

The resolved command, manifest, resource samples, metrics, and full log are in
`results/stage4-h100/stage4-h100-contract-smoke-20260803/`. No RLinf source was
modified. No training or Ray process remains active on either GPU.

Stage 4 is complete. Stage 5 is a paid scientific baseline and must not begin
without explicit protocol and cost approval.
