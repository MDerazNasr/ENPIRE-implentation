# Stage 5B A10 Resource Probe

Status: complete with a hardware-feasibility failure. This is resource evidence,
not policy-performance evidence.

## Purpose

Stage 4 proved that one train/eval environment could load the Stage-1 actor and
exercise rollout, replay, actor/critic updates, weight synchronization, and
fixed-ID evaluation. It did not measure the upstream Stage-2 environment scale.

This probe kept the intended representative settings for one runner step:

- 64 training environments;
- 256 fixed-ID evaluation environments;
- 500-step train/evaluation horizons;
- the upstream BC/Q schedule (`7.0/2.5` BC and `0.05/0.45` Q);
- expert takeover disabled and no expert model;
- seed 2026 and the reduced-budget Stage-1 step-250 actor.

It was intentionally not allowed to reduce environment counts, camera size, or
shader memory after launch. Any such change would require a separate profile and
would answer a different feasibility question.

## Environment and preflight

- Hardware: NVIDIA A10, 23,028 MiB VRAM, `$1.29/hour`.
- Host: `150-136-104-39`.
- RLinf: clean commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Harness: commit `eb909aefe2178b1ff1144dfe62008ed5d3655702`.
- PyTorch: `2.6.0+cu124`; NVIDIA driver `570.195.03`.
- Checkpoint: 10,015,912,759-byte actor with SHA-256
  `26995a81d44f2c035e4da40ccdbbeab65552d390d402f0594fa746e975d4b018`.
- Normalization: official dataset `norm_stats.json`, 2,149 bytes, SHA-256
  `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd`.
- A CUDA tensor operation and an exact seeded RGB/GPU custom-task reset and
  step both passed before launch.
- All 27 dependency-free harness tests passed on the pod.

## Result

The run failed during creation of the parallel evaluation camera group, before
rollout or evaluation metrics could be produced.

| Field | Result |
| --- | ---: |
| Manifest status | `failed` |
| Exit code | `255` |
| Elapsed time | 50.27 seconds |
| Peak sampled VRAM | 22,598 MiB / 23,028 MiB (98.1%) |
| Launcher-attributed cost | `$0.0180` |

ManiSkill raised `RuntimeError: cannot create buffer`, followed by its explicit
diagnostic that the GPU-parallel camera group could not be created with the
current camera/environment load. GPU memory returned to idle after RLinf
terminated, and no worker remained.

The eight retained D1 manifests sum to `$5.7241` of launcher-attributed GPU
time, so this checkpoint crosses the required `$5` notification threshold.
Provider setup, download, transfer, and idle billing are not represented in
that sum; reconcile the provider dashboards before approving the next GPU.

## Interpretation and next gate

An A10/24 GB GPU is not viable for the unchanged representative 64-train,
256-eval RGB configuration. This does not show that RLT training fails or that
the Stage-1 actor is ineffective; the run ended before a rollout.

The next unchanged-contract resource test should use an A100 40 GB or larger.
If cost pressure requires retaining the A10, first preregister a distinct
reduced-parallelism profile and document how its timing and evaluation protocol
will be extrapolated. Do not silently reduce environment counts or image memory
inside Control B.

Reference A and Control B remain unrun. Stage 6 remains blocked.

Evidence: `results/stage5b-a10/stage5b-a10-probe-20260804/`.
