# Stage 5B Stage-2 Resource Probes

Status: the unchanged 256-parallel-eval contract failed on A10 and triggered a
Vulkan device loss on H100. A clean A10 then passed the one-environment RGB/GPU
preflight but the 64-parallel x 4-epoch probe still exhausted its camera-buffer
capacity. A separate A100 40 GB was rejected because it exposed CUDA but no
usable Vulkan render device. A final A10 profile with 32 parallel evaluation
environments across eight epochs failed at the same camera-allocation boundary
while retaining all 64 training environments. The next valid hardware target
is a graphics-capable 48 GB GPU. This is resource evidence, not
policy-performance evidence.

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

## A10 result

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

## H100 unchanged-contract result

The exact same 64-train/256-eval/500-horizon profile was then run on an NVIDIA
H100 80 GB HBM3 at `$3.29/hour`, using project commit `a6a68b5`, the same pinned
RLinf commit, matched norm stats, and the verified step-250 actor.

| Field | Result |
| --- | ---: |
| Manifest status | `failed` |
| Exit code | `255` |
| Elapsed time | 105.79 seconds |
| Peak sampled VRAM | 2,725 MiB / 81,559 MiB |
| Launcher-attributed cost | `$0.0967` |

This failure also occurred before rollout. Vulkan reported
`vk::Device::waitForFences: ErrorDeviceLost`, after which ManiSkill raised its
parallel-camera-group diagnostic. Host memory remained above 1.28 TiB
available and the GPU returned to idle. The low sampled VRAM peak means the
H100 failure cannot be explained as ordinary capacity exhaustion.

The retained D1 manifests through this unchanged-contract run sum to
approximately `$5.8208` of
launcher-attributed GPU time, so the required `$5` notification remains active.
Provider setup, download, transfer, and idle billing are not represented in
that sum; reconcile the provider dashboards before approving later long runs.

## Interpretation and next gate

An A10/24 GB GPU is not viable for the unchanged representative 64-train,
256-parallel-eval RGB configuration. The H100 result shows that merely adding
VRAM does not make that monolithic camera group reliable on the current stack.
Neither result shows that RLT training fails or that the Stage-1 actor is
ineffective; both runs ended before rollout.

RLinf supports sequential evaluation epochs and advances its deterministic
reset-ID generator after each epoch. The next explicit profile therefore uses
64 parallel evaluation environments for four epochs. It still evaluates 256
fixed-ID trajectories, and the same batching is now declared for Reference A,
Control B, and Candidate C. A config validator rejects profiles where parallel
environments x rollout epochs does not equal the declared trajectory count.
This is an operational batching adaptation, not a policy hyperparameter.

## Invalid pre-restart H100 batched attempt

The committed 64-parallel x 4-epoch profile was launched at project commit
`7bcf0c9`, but it encountered the same `ErrorDeviceLost` before rollout:

| Field | Result |
| --- | ---: |
| Manifest status | `failed` |
| Exit code | `255` |
| Elapsed time | 95.83 seconds |
| Peak sampled VRAM | 2,725 MiB / 81,559 MiB |
| Launcher-attributed cost | `$0.0876` |

This attempt is excluded from the profile's feasibility decision. Immediately
afterward, a one-environment 384 x 384 RGB/GPU constructor also failed with
`vk::Device::waitForFences: ErrorDeviceLost`; the earlier Stage-4 run had
successfully executed that one-environment path. `nvidia-smi --gpu-reset` is
unsupported on this pod. Therefore the current device context is invalid and a
provider-level pod restart is required before repeating the batched probe.

The retained D1 manifests now sum to approximately `$5.9084` in
launcher-attributed runtime. Provider billing remains higher because setup,
installation, transfer, restart, and idle time are outside these manifests.

## A100 renderer incompatibility

Lambda instance `480a114573c7494c99afad2f166097b9` provided an A100 SXM4
40 GB at `$1.99/hour`. CUDA passed, and aligned NVIDIA 570.195.03 userspace and
kernel packages were tested with both the provider's open module and the
proprietary module. In both cases the NVIDIA Vulkan ICD returned
`ERROR_INCOMPATIBLE_DRIVER`. Mesa llvmpipe exposed a CPU Vulkan device, but
SAPIEN rejected it with `Failed to find a supported physical device "cpu"`.
No RLinf run was launched. This instance class is unsuitable for the required
RGB ManiSkill renderer even though its CUDA and VRAM capacity are adequate.

## Clean A10 64 x 4 result

The 64-parallel x 4-epoch profile was repeated on the clean A10 after all 29
harness tests and an exact one-environment RGB/GPU reset and step passed. The
actor checksum again matched
`26995a81d44f2c035e4da40ccdbbeab65552d390d402f0594fa746e975d4b018`.
The run failed during construction of the evaluation camera group, before
rollout or a policy metric:

| Field | Result |
| --- | ---: |
| Manifest status | `failed` |
| Exit code | `255` |
| Elapsed time | 35.19 seconds |
| Peak sampled VRAM | 21,979 MiB / 23,028 MiB (95.4%) |
| Launcher-attributed cost | `$0.0126` |

The GPU returned to idle and no RLinf/Ray worker remained. This clean failure
shows that 64 evaluation environments are still too large alongside the 64
resident training environments on a 24 GB A10; it is not evidence about the
RLT actor.

## Clean A10 32 x 8 result

A separately committed resource profile kept all 64 training environments and
all 256 deterministic reset IDs, but reduced each evaluation camera group to
32 environments and ran eight sequential epochs. It failed at the same camera
allocation boundary before rollout:

| Field | Result |
| --- | ---: |
| Manifest status | `failed` |
| Exit code | `255` |
| Elapsed time | 30.46 seconds |
| Peak sampled VRAM | 21,977 MiB / 23,028 MiB (95.4%) |
| Launcher-attributed cost | `$0.0109` |

The repeated near-capacity peak shows that the A10 cannot host the upstream 64
training environments, a representative RGB evaluation group, and the Stage-2
runtime. Further reducing training environments would change the scientific
training contract and is not authorized as an infrastructure-only adaptation.
The next target must combine at least 48 GB VRAM with a working graphics/Vulkan
stack: prefer A6000 48 GB, then L40/L40S 48 GB or RTX 6000 Ada 48 GB. A100 and
H100 are not substitutes on providers where their compute-only Vulkan path is
missing or unstable. Reference A, Control B, and Candidate C remain unchanged
until that hardware reaches rollout.

Reference A and Control B remain unrun. Stage 6 remains blocked.

Evidence:

- `results/stage5b-a10/stage5b-a10-probe-20260804/`
- `results/stage5b-h100/stage5b-h100-probe-20260804/`
- `results/stage5b-h100-batched/stage5b-h100-batched-probe-20260804/`
- `results/stage5b-a10-batched/stage5b-a10-batched-probe-20260804/`
- `results/stage5b-a10-batched32/stage5b-a10-batched32-probe-20260804/`
