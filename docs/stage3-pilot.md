# Stage 3 Representative Stage-1 Pilot

Status: complete. The unchanged representative profile completed on an H100
80 GB PCIe, produced step-5 and step-6 checkpoints, and reloaded the final
checkpoint through RLinf's native resume path.

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

## A100 40 GB boundary result

The same full-precision profile was then tested on an A100 40 GB SXM4. Batch
size 8 passed optimizer initialization but failed in the first forward pass at
approximately 39.44 GiB allocated. The preregistered fallback kept global
batch size 8 and reduced only the micro batch to 1; it passed the forward pass
but failed during backward while requesting another 2.24 GiB with about 1.30
GiB free. Retrying that fallback with PyTorch expandable segments produced the
same material result. No precision, objective, optimizer, or offload semantics
were silently changed. Raw evidence is under `results/stage3-a100/`.

This establishes that 40 GB is below the requirement for the unchanged
full-precision profile. It does not establish that all 48 GB cards will work;
48 GB remains an untested boundary.

## H100 80 GB successful result (2026-08-03)

- Provider instance: `ce090b02782b431eb0a2442421a2eff8` at `$3.29/hour`.
- GPU: NVIDIA H100 PCIe with 81,559 MiB reported VRAM.
- RLinf: pinned commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Assets: official pi0.5 weights (14,467,165,872 bytes), all 400 episode
  parquets, and the matched normalization statistics.
- Training profile: unchanged micro/global batch size 8, FP32 execution,
  six optimizer steps, save interval 5, seed 2026.
- Outcome: exit code 0. All six steps logged total, RLT, and VLA loss. Final
  total loss was 4.36189; six steps are a systems validation, not evidence of
  convergence or policy improvement.
- Peak sampled GPU memory: 42,195 MiB. Peak inferred system-memory use was
  49.95 GiB.
- Steady-state training time: approximately 0.947 seconds per step (steps
  2--4, excluding checkpoint saves). The first step took 74.9 seconds because
  of data-worker/JIT warmup. Each full checkpoint save added about 59 seconds.
- Checkpoints: both step 5 and final step 6 are approximately 40.07 GB each
  (about 37.32 GiB). RLinf's native `runner.resume_dir` path loaded the complete
  final actor/optimizer/scheduler checkpoint, restored global step 6, and
  exited cleanly at 6/6 without an additional optimizer step.
- Launcher-attributed run time/cost: 331.62 seconds and `$0.3031`. This excludes
  billable installation/download/reload time; the provider's final spend must
  be recorded separately. No `$5` reporting threshold was crossed.
- W&B logged offline because the previously shared credential is considered
  exposed and was not reused.

Compact evidence is stored under `results/stage3-h100/`. The 75 GB checkpoint
payload remains on the provider volume; the repository retains the file sizes
and SHA-256 hashes instead of duplicating it.

## Longer-run cost projection

Using the measured 0.947-second steady-state step time, about 135.6 seconds of
one-time startup, a 59-second save, and the H100 price of `$3.29/hour`:

| Steps | One final checkpoint | Checkpoint every 5 steps |
| ---: | ---: | ---: |
| 250 | about 7.2 min / `$0.39` | about 55.4 min / `$3.04` |
| 500 | about 11.1 min / `$0.61` | about 108.5 min / `$5.95` |
| 1,000 | about 19.0 min / `$1.04` | about 214.7 min / `$11.77` |
| 2,000 | about 34.8 min / `$1.91` | about 427.2 min / `$23.42` |

These are engineering projections, not provider invoices. Frequent saves are
both time- and storage-dominant: saving every five steps would create roughly
8 TB per 1,000 steps if every checkpoint were retained. A longer experiment
should therefore use a scientifically justified, much wider checkpoint
interval and retention policy.

## Stage gate

Stage 3 is complete. Stage 4 must not start without explicit approval. The
next decision is whether to test the 48 GB boundary or accept the H100 as the
known-working tier, then define the first meaningful baseline horizon and
checkpoint cadence within the cost cap.

## External RunPod checkpoint preservation (2026-08-03)

A second bounded upstream Stage-1 run completed for five optimizer steps on an
external H100 80 GB pod. It used the same FP32 micro/global batch-size-8
contract and seed 2026, but stopped at step 5 so one complete checkpoint and
the official assets would fit in the pod's 88 GB RAM-backed workspace. Final
logged losses were `train/loss=4.22`, `train/rlt_loss=4.14808`, and
`train/vla_loss=0.07191`.

The inference actor weights were copied to persistent storage at
`/workspace/qualia-checkpoints/stage1-step5/actor/model_state_dict/full_weights.pt`.
The persisted file is 10,015,912,759 bytes and its SHA-256 is
`6b57b89beeaa4a6d5ee30f1a94caa7fc7cacbf9a7c8f9ef6c6043eeab302a7cf`,
exactly matching the source artifact. Compact verification evidence is in
`results/stage1-runpod-20260803/checkpoint-verification.txt`. The attempted
cross-provider copy to the A10 was cancelled after roughly 1 GB because the
route was too slow; its partial file was deleted. No Stage-4 rollout was
started.
