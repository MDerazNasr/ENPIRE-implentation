# Stage 3 Representative Stage-1 Pilot

Status: in progress; the minimum-hardware A10 attempt failed before the first
optimizer step, so no checkpoint was produced.

## A10 minimum-hardware result (2026-08-03)

- Provider instance: `bca80a01ecad44ea99240f0745f7059b` at `$1.29/hour`.
- GPU: NVIDIA A10 with 23,028 MiB reported VRAM (22.07 GiB usable by PyTorch).
- RLinf: clean pinned commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Project commit: `0593b2210683bffed0cbbe65be192d96a6084128`.
- Assets: official pi0.5 base model, all 400 demonstration parquets, and the
  matched `norm_stats.json`.
- Runtime preflight: CUDA and a seeded RGB/GPU ManiSkill reset and step passed
  after installing the provider image's missing matching NVIDIA GL/Vulkan
  userspace package and rebooting once.
- Attempted profile: the preregistered six-step Stage-1 pilot with micro/global
  batch size 8 and a checkpoint scheduled at step 5.

The run failed while `warmup_optimizer_state()` created AdamW state, before a
batch or optimizer step executed. PyTorch reported 20.15 GiB in use, 1.92 GiB
free, and a failed 2.24 GiB allocation. This is not a batch-activation OOM, so
reducing only `actor.micro_batch_size` cannot make the declared Stage-1
objective viable on this 24 GB class GPU. Enabling expert-only training or
changing optimizer/offload semantics would weaken the representative contract
and was deliberately not used as a silent workaround.

The launcher recorded 130.38 seconds and `$0.0467` of subprocess-attributed
GPU cost. Provider spend must be recorded separately because setup and asset
download time are also billable. No `$5` threshold was crossed. W&B evidence
was captured offline because a fresh non-exposed credential was not yet
available; it can be synced after authentication.

Raw evidence is stored under
`results/stage3-a10/stage3-a10-pilot-20260803/`.

## Next action

Resume the same profile on a 40--48 GB NVIDIA GPU. The already-proven A100
40 GB or an A6000 48 GB is the smallest evidence-supported tier. Stage 3
remains incomplete until six steps finish, the step-5 actor checkpoint exists
and reloads, and measured timing/resource data support the longer-run cost
projection.
