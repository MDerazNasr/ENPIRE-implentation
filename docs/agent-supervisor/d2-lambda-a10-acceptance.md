# D2 Lambda A10 acceptance

Status: first authorized attempt failed safely on 2026-09-03; retry is
preflight-ready but has not been launched.

## Scope and authority

The user replaced the planned Modal allocation with already-active Lambda Cloud
instance `249956d9699b4e1d8e57754733f7ac09`: one NVIDIA A10 in Virginia at USD
`1.29` per hour. The existing 1,800-second boundary therefore capped incremental
GPU cost at USD `0.645`. Auto-shutdown was not changed. This remained a
non-promotable engineering attachment check with one authorized trial, one
training step, and one fixed evaluation trajectory.

The trained 9.3 GiB actor was initially selected. The local-to-Lambda transfer
held at roughly 0.5--0.7 MB/s and projected beyond four hours, reproducing the
cross-provider bottleneck already recorded in `stage3-pilot.md`. The transfer
was stopped near 71 MB and the verified incomplete remote copy was deleted; the
authoritative 10,015,912,759-byte local actor remains intact. The run instead
used the public pi0.5 base model as the
repository's documented smoke-only feature-model fallback. This weakens no
scientific result because D2 cannot make a policy-performance claim.

## Bound runtime

- Candidate commit: `152cf9028fb8f94a66b352fbcb8f4cc7de2a7bcc`.
- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Resolved config SHA-256:
  `bacc089bb7c510b36c572aaad480000813a9e1220175d28b1f57ba86f1fcfa73`.
- Base-model SHA-256:
  `0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f`.
- Norm-stat SHA-256:
  `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd`.
- GPU UUID: `GPU-57ffc01d-7c74-d8ee-61e4-2c936994fe8a`.
- Runtime: PyTorch `2.6.0+cu124`; CPU PhysX and Mesa llvmpipe Vulkan rendering;
  offline W&B; no checkpoint save.

## Attempt 1 result

The guarded `agent.d1_launcher` started RLinf once. It exited `1` after
`20.0974` seconds and attributed USD `0.00720158` to the subprocess. Hydra
`1.4.0.dev9`, selected by the upstream installer, rejected RLinf's
`version_base='1.1'` before environment creation, rollout, evaluation, or
training. The launcher wrote a terminal failed manifest and log. No evaluator
ran and no incumbent advanced.

The compatibility versions already frozen in `modal_d2_acceptance.py` were then
installed: Hydra `1.3.2`, OmegaConf `2.3.0`, and SAPIEN `3.0.1`. A no-training
Hydra `--cfg job --resolve` check passed; its 8,493-byte output has SHA-256
`60c74a5eecfe1478bfda6e310405da1ccaaf8d13c2b796559a50eedf7958108d`.
This proves the observed blocker is repaired, but it is not permission for a
second paid trial.

Compact evidence and the machine summary are under
`results/provider-acceptance/d2/lambda-a10-attempt-1/`. A retry requires a new
explicit trial approval and remains permanently unable to evaluate or promote.
