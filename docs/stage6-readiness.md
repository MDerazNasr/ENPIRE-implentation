# Stage 6 Candidate-C Readiness Audit

Status on 2026-08-15: the Candidate command, assets, simulator, and one-rollout
capacity gate pass on the replacement RTX PRO 6000. Paid execution is
authorized with tracked spend and no automatic cap. The Blackwell-compatible
Torch 2.8 runtime differs from Control B's Torch 2.6 runtime, so a full result
from this pod is provisional rather than a strict one-factor estimate.

## Scientific boundary

Candidate C is an independent Stage-2 run. Both Control B and Candidate C
load the same verified Stage-1 step-500 actor through
`rollout.rlt_feature_model.model_path=${STAGE1_CHECKPOINT}`. Candidate C does
not set `runner.resume_dir`, `runner.ckpt_path`, `actor.model.model_path`, or
`rollout.model.model_path`, so it cannot inherit the trained Control-B
actor/critic.

The complete Hydra-override comparison has exactly two differences:

| Field | Control B | Candidate C |
| --- | ---: | ---: |
| `algorithm.actor_weight_schedule.warmup_bc_weight` | `7.0` | `5.6` |
| `algorithm.actor_weight_schedule.online_bc_weight` | `2.5` | `2.0` |

Everything else is matched: pinned RLinf commit, seed 2026, upstream replay
and update schedules, Q weights, 100 runner steps, 64 train trajectories per
step, 256 fixed-ID evaluation trajectories, 500-step horizon, disabled expert
takeover, disabled actor offload, and CPU weight transport. This is the
preregistered 0.8x BC-schedule intervention; it is not a coding-agent change.

The upstream RLT guide supports this boundary: Stage 2 freezes the Stage-1
feature model and trains the compact actor/critic, while a scratch Stage-2 run
keeps its Stage-2 model path null and points `rollout.rlt_feature_model` at the
Stage-1 actor.

## Preserved inputs

The local Stage-1 input was reverified during this audit:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| Stage-1 step-500 `full_weights.pt` | `10,015,912,759` | `b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3` |
| Official dataset `norm_stats.json` | `2,149` | `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd` |

The normalization statistics were restored from the official RLinf
`rlt-maniskill-PegInsertionSide-v1-400-succ` dataset at pinned dataset commit
`2b92d5ef3fe274d30219130133f9e34c7ab91ebf`; their hash matches the asset used
by the completed chain. The unrelated reconstructed file
`tmp/norm_stats_reconstructed.json` is not canonical and must not be used.

## Dry-run result

The exact Candidate-C profile dry-resolved with seed 2026, the local Stage-1
actor, 100 training steps, and 256 fixed evaluations. The launcher exited zero,
printed `DRY RUN ONLY`, and created no run directory. A paid launch still
requires both `--execute` and `--acknowledge-paid-run`, plus valid paths and an
exact pinned RLinf checkout.

The resolved Candidate config SHA-256 was
`33e5e4a020961b27ee211cc6c784dab47af18f2dfc13d7936322f86916bec500` at
project commit `32cbfb2fe65931668663b60bbece314767e5fbae`. This hash describes
the pre-authorization profile with the safe `$150` cap and will change if its
operational budget fields are explicitly updated.

## Launch authorization and cost tracking

The preserved append-only ledger totals `$189.824932`. Mohamed subsequently
authorized continuation without an automatic cumulative cap while retaining
cost tracking. Candidate C therefore uses `max_cost_usd: null` and reports
cumulative thresholds every `$5` from `$190` through `$300`. This is an
operational-only change; no scientific field changed. The matched Control B
required `27.96` hours and `$91.9730` on an H100 PCIe at `$3.29/hour`; provider
uptime/setup may add cost not attributed by the launcher.

Before a paid launch:

1. Provision a graphics-capable GPU workspace, restore and hash-check the two
   inputs above, pin RLinf to `c90951a0c799a750cb5294ed10587c61cc2af8bf`,
   and pass the live Vulkan/ManiSkill preflight.
2. Restore the `$189.824932` ledger, dry-run again, and launch exactly one
   seed-2026 Candidate run.
3. After completion, download and hash the Candidate policy and full compact
   evidence before releasing the workspace.

Seed 2026 can provide a matched provisional comparison with Control B. It
cannot produce the preregistered three-seed keep/revert conclusion by itself;
that result must remain `INCONCLUSIVE` until the approved seed set exists.

## Modal provider audit — 2026-08-13

Modal was tested before transferring weights or installing RLinf. One H100
80 GB HBM3 and one L40S 48 GB container each passed CUDA discovery, but both
failed the required NVIDIA Vulkan gate. After installing `libvulkan1` and
`vulkan-tools`, supplying the matching NVIDIA ICD, and testing supported API
versions, `vulkaninfo` returned `VK_ERROR_INCOMPATIBLE_DRIVER`. The containers
exposed CUDA devices and NVIDIA user-space libraries but no usable NVIDIA
Vulkan device/ICD.

This blocks ManiSkill's RGB rendering path independently of VRAM or GPU model.
Both containers were stopped, no Stage-1 asset was uploaded, and Candidate C
was not launched. Exploratory compute stayed below the `$5` reporting
threshold. Modal is therefore rejected for this experiment unless its GPU
runtime changes and the Vulkan gate is rerun successfully. The next provider
must expose NVIDIA Vulkan and allow one uninterrupted 30-plus-hour job with
persistent storage; a single L40S remains the lowest-cost configuration already
shown to run the representative Stage-2 route.

## RunPod RTX PRO 6000 preflight — 2026-08-14

The replacement RunPod endpoint was reachable and exposed one NVIDIA RTX PRO
6000 Blackwell Server Edition with 97,887 MiB VRAM, driver `580.159.03`, a
large `/workspace` mount, and the expected NVIDIA and DRI device nodes. CUDA
discovery passed. The unmodified image initially lacked GLVND/EGL packages;
after installing the Vulkan tools and required loader packages, the NVIDIA ICD
could create a Vulkan instance but could not create a logical device.

System-call tracing identified the actual blocker: opening
`/dev/dri/renderD133` is denied with `EACCES`, and NVIDIA modeset ioctls are
denied with `EPERM`. Those denials persist for root and the device-node group;
the container is also prohibited from changing the device permissions. This is
a container-runtime device-cgroup problem, not an RLinf, ManiSkill, CUDA,
storage, VRAM, or checkpoint problem. No weights were transferred and no
Candidate training was launched.

Do not spend setup time on this incarnation of the container. Recreate or
restart it with `NVIDIA_DRIVER_CAPABILITIES=all` (or at minimum
`compute,utility,graphics`) applied at container creation, then rerun
`vulkaninfo --summary` before installing RLinf. Continue only if Vulkan creates
a device successfully. The GPU model and available capacity are otherwise
sufficient.

## Replacement RunPod RTX PRO 6000 execution gate — 2026-08-15

The replacement pod at `213.173.102.104:45805` fixed the prior container
device-cgroup failure. It exposes one RTX PRO 6000 Blackwell with 97,887 MiB
VRAM, a 50 GB container disk, and a 100 GB persistent volume at `/workspace`.
The NVIDIA ICD creates a Vulkan logical device, and the exact custom RGB
PegInsertionSide environment completed a GPU reset and step.

RLinf's documented Torch 2.6/CUDA 12.4 environment can discover this GPU but
cannot execute an `sm_120` kernel. RLinf's own supported `--torch 2.8.0`
installer path with `UV_TORCH_BACKEND=cu128` produced Torch 2.8.0+cu128, and a
CUDA tensor then executed successfully. The pinned RLinf source remains clean
at `c90951a0c799a750cb5294ed10587c61cc2af8bf`; Hydra 1.3.2 and OmegaConf
2.3.0 remain pinned. This runtime differs from Control B's Torch 2.6.0+cu124
runtime. Any Candidate result from this pod is therefore provisional and must
not be described as a strict one-factor estimate, even though the RLinf source,
seed, assets, and Hydra command are otherwise matched.

The non-scientific capacity run
`stage6-candidate-rtxpro6000-capacity-seed2026-20260815` completed with exit
code zero. It ran all 64 training trajectories, recorded 17.1875% train-route
success and 275 replay transitions, and correctly performed no learner update
below the unchanged 10,000-transition gate. The representative rollout took
310.8 seconds; peak sampled GPU use was 20,374 MiB and 100% utilization. Total
launcher time including network-volume startup was 1,272.4 seconds, tracked
cost was `$0.7422`, and the cumulative ledger became `$190.5672`.

`stage2_6_candidate_rtxpro6000_torch28.yaml` preserves the exact Candidate-C
Hydra command and scientific values while recording the runtime difference in
its manifest. At the measured rollout rate, 100 steps plus learner and fixed
evaluation overhead project to roughly 9--10 hours and `$19--21` of additional
launcher-attributed compute at `$2.10/hour`. The full run remains one-seed,
provisional evidence.
