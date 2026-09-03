# F0 Matched Scientific Runtime

Status: **selected and verified; not deployed** on 2026-09-03.

The machine-readable authority is
[`../../results/runtime-qualification/f0/runtime-contract.json`](../../results/runtime-qualification/f0/runtime-contract.json).
F0 selects the runtime. It does not launch a provider job, authorize spend,
rerun a policy, or make a scientific claim.

## Decision

Control and every Candidate arm must use `enpire-matched-scientific-runtime-v1`:

| Layer | Frozen value |
|---|---|
| Provider worker | Modal; one `RTX-PRO-6000`; 16 physical CPU cores; 96 GiB RAM |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition; at least 96,000,000,000 bytes |
| Container | Linux amd64; Ubuntu 22.04; `nvidia/cuda:12.8.1-devel-ubuntu22.04` amd64 digest `sha256:6617a...fd7` |
| Python / compute | Python 3.11.14; Torch 2.8.0+cu128; CUDA toolkit 12.8.1 |
| RLinf / simulator | RLinf `c90951a...af8bf`; ManiSkill `v3.0.0b22` / `33967b9...0907`; SAPIEN 3.0.1 |
| Physics / renderer | CPU PhysX, one environment per child; Mesa llvmpipe 23.2.1 via Vulkan 1.3.204 |
| Batching | spawn-based 16-process adapter; train 16×4; fixed evaluation 16×16 |
| Transfers | actor offload disabled; weight transport on CPU |
| Resume | native RLinf checkpoint plus mandatory fail-closed schedule/replay sidecar |

NVIDIA specifies 96 GB GDDR7 for this GPU class, while Modal exposes the
exact `RTX-PRO-6000` request type. The selection therefore has ample margin
over the approximately 25.2 GiB measured operating footprint and the 26.3 GiB
Stage-2 reference peak. It is selected for matchedness and demonstrated route
coverage, not because F0 claims it is the fastest possible worker.

## Why this runtime

The native L40S probe was the least-expensive route to complete a representative
rollout/evaluation path, but it did not establish the later full 100-step route
or repaired segmented-resume behavior. A10 failed the representative camera
groups near device capacity, the tested A100 40 GB lacked the required native
graphics compatibility, and an H100 encountered a device-loss failure. In
contrast, the Modal RTX PRO 6000 runtime completed Candidate r3 and later passed
the bounded r4 schedule/replay resume gate. Re-running both arms there removes
the previous Control/Candidate runtime split.

The renderer remains the already demonstrated CPU PhysX plus Mesa llvmpipe
path. Requiring NVIDIA Vulkan would reintroduce the provider failure that the
multiprocess adapter was built to avoid. GPU compute still uses the specified
Blackwell device.

## Immutable identities

The NVIDIA image tag resolved on 2026-09-03 to index digest
`sha256:a99a...e97` and linux/amd64 digest `sha256:6617...fd7`. F1 must deploy
the platform digest, not merely the mutable tag. Provider-managed host kernel
and NVIDIA driver patch versions cannot be frozen by the project; the worker
must capture them and reject incompatible CUDA/GPU/smoke results.

The contract also binds:

- official pi0.5 base weights: 14,467,165,872 bytes, SHA-256 `0eb11ca...b0f`;
- canonical Stage-1 actor: 10,015,912,759 bytes, SHA-256 `b5bf938...3f3`;
- dataset revision: `2b92d5e...ebf`; and
- tracked normalization statistics: 2,149 bytes, SHA-256 `d5d6a96...dbd`.

The validator rehashes the tracked norm file and the runtime adapter, resume
patch, site customization, and scientific profile. F1 must add the exact RPC
source bundle; each paid worker must freshly rehash the large remote inputs
before rollout or training.

## Resume and matchedness boundary

Every resumed run must load both the native RLinf checkpoint and the strict
project sidecar. A missing or invalid sidecar fails before rollout or update.
The sidecar restores RLT update/transition counters and the replay buffer's
dedicated Torch generator state. It does not claim bitwise simulator identity
across processes. F2 will decide whether the definitive runs may be segmented;
it may not weaken this resume rule.

Control and Candidate must carry the same contract ID and all values above.
Only a preregistered intervention may differ. A worker receipt with a different
GPU class, image digest, stack version, simulator/renderer, batching, offload,
transport, or resume behavior is invalid scientific evidence.

## Storage and billing lifecycle

The authenticated read-only inventory on 2026-09-03 confirmed that the named
`enpire-workspace` volume still exists; no GPU was allocated. Modal says
Volumes are persistent, storage is measured by a daily snapshot, and deleted
data may remain billable for up to four days. The current public price is
$0.09/GiB/month. Compute is billed per second without a reservation: the
published RTX PRO 6000, CPU-core, and memory rates make this 16-core/96-GiB
request **$4.552992/hour** before any other applicable charge.

The volume must use `create_if_missing=false`. Compute is stopped or cancelled
on every terminal path. The volume remains retained until canonical inputs and
evidence are exported and deletion is separately approved. Prices must be
re-read and rebound into each paid approval immediately before launch.

Current provider and hardware facts were checked against the official
[Modal pricing](https://modal.com/pricing),
[Modal GPU](https://modal.com/docs/guide/gpu),
[Modal Volume](https://modal.com/docs/guide/volumes),
[Modal billing](https://modal.com/docs/guide/billing), and
[NVIDIA RTX PRO 6000](https://www.nvidia.com/en-us/data-center/rtx-pro-6000-blackwell-server-edition/)
pages. Ubuntu publishes the selected
[Mesa Vulkan package](https://packages.ubuntu.com/jammy/mesa-vulkan-drivers)
and [Vulkan loader](https://packages.ubuntu.com/jammy/libvulkan1) versions.

## Verification and next action

Run:

```bash
python3 scripts/check_f0_runtime_contract.py
python3 -m pytest -q tests/test_f0_runtime_contract.py
```

The validator is fail-closed for runtime drift, input-hash drift, a weakened
resume policy, paid authorization, or different Control/Candidate contracts.
Gate F0 passes when it returns `passed=true`. The next phase is F1: deploy and
adversarially test the fixed worker RPC against this contract without granting
general shell authority to the agent.
