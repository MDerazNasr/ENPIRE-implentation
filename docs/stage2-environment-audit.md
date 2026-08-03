# Stage 2 Environment and Upstream Audit

Status: acceptance evidence complete except W&B authentication and final
provider-spend capture. No Stage-3 checkpoint pilot was launched.

## Connectivity result

- Previous direct endpoint `103.196.86.46:20528`: connection refused.
- Previous RunPod proxy container ID: `container not found`.
- Conclusion: the earlier L40S pod is stopped/deleted or has been replaced. A
  current SSH endpoint is required for GPU, assets, W&B, and upstream smoke
  verification.

Replacement pod verified on 2026-08-02:

- direct SSH endpoint: `213.173.102.13:40946`;
- GPU: NVIDIA RTX PRO 4000 Blackwell, 24,467 MiB VRAM;
- system RAM: 125 GiB total;
- CPU: 48 logical CPUs;
- root filesystem: 20 GiB;
- `/workspace`: network-mounted storage whose global `df` capacity does not
  expose the pod's smaller write quota.

Final Stage-2 instance verified on 2026-08-03:

- SSH user/endpoint: `ubuntu@193.122.155.40:22`;
- GPU: NVIDIA A100 SXM4, 40,960 MiB VRAM;
- system RAM: 216 GiB;
- CPU: 30 logical CPUs;
- local filesystem: 497 GiB, with 422 GiB free after installation and assets;
- provider price: `$1.99/hour`; provider UI reported `$0.45` spent when Stage 2
  resumed.

## Pinned source audit

A fresh read-only RLinf checkout was inspected at
`c90951a0c799a750cb5294ed10587c61cc2af8bf`.

Verified launch boundaries:

| Stage | Entrypoint | Config directory | Config |
| --- | --- | --- | --- |
| Stage 1 | `examples/sft/train_vla_sft.py` | `examples/sft/config` | `maniskill_rlt_stage1_sft_openpi_pi05` |
| Stage 2 | `examples/embodiment/train_embodied_agent.py` | `examples/embodiment/config` | `maniskill_rlt_stage2_ac_mlp` |

The Stage-1/Stage-2 distinction exposed and fixed a launcher defect: the first
Stage-1 profile incorrectly inherited the embodiment entrypoint/config path.
Profiles now declare the entrypoint, config directory, and runtime environment
explicitly; actual execution validates all three files plus the pinned commit.

## Override audit

Every Hydra override key in all six profiles was checked against the matching
pinned upstream YAML tree.

- Stage-1 dataset/model/norm-stat, batching, runner, optimizer, and logger keys
  exist in the SFT profile.
- Stage-2 schedule, fixed-eval, expert, actor, environment, and runner keys exist
  in the embodiment profile.
- Stage 2 does not predeclare
  `rollout.rlt_feature_model.openpi_data.norm_stats_path`; profiles now use the
  required Hydra addition syntax:
  `+rollout.rlt_feature_model.openpi_data.norm_stats_path=...`.
- Expert takeover is explicitly disabled in training and evaluation, and the
  placeholder expert model is set to `null`.

## Reference-A source verification

Pinned source initializes no RLT switch state when
`rlt_policy_switch.enable=false`. The simulator route treats an absent switch
flag as `false` and selects the VLA `ref_chunk`, so the Reference-A override is
consistent with reference-only execution. Stage 4 must still confirm this from
runtime routing metrics before the scientific reference is accepted.

## Fixed evaluation verification

The Stage-2 upstream config uses:

- task `PegInsertionSideWideClearance-v1`;
- evaluation seed `2026`;
- `use_fixed_reset_state_ids=true`;
- 256 evaluation environments;
- 500-step episodes.

RLinf generates reset episode IDs from a Torch generator seeded by the eval
seed and reuses them when fixed IDs are enabled. Control and Candidate profiles
retain these values.

## Contract-smoke correction

The Stage-2 smoke profile now explicitly uses one environment, a 20-step
episode, critical-phase/always-on routing, one-transition replay thresholds,
batch size one, one update, and disables the weight schedule. These are labeled
contract-smoke deviations required to exercise actor routing/update; they are
not used by Reference A, Control B, or Candidate C and cannot become scientific
evidence.

## Resource evidence

Resource snapshots now include Linux `/proc/meminfo` total/available system RAM
in addition to GPU, VRAM, utilization, disk, and cumulative cost. A portable
fallback records total RAM when `/proc` is unavailable.

## Final live installation and simulator verification

RLinf was installed with the repository's official custom-environment command
at commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`, using PyTorch
`2.6.0+cu124`. After the installer completed, the checkout was clean and its
temporary manifest backup was removed.

Verified runtime evidence:

- CUDA 12.4 recognizes the A100 SXM4;
- a CUDA tensor operation completed successfully;
- `rlinf` and ManiSkill import successfully;
- RLinf's custom `PegInsertionSideWideClearance-v1` task registered;
- one RGB, GPU-backend environment reset with seed 2026 succeeded;
- one sampled `pd_joint_delta_pos` step succeeded and the environment closed
  with exit code zero.

The provider image initially exposed only the NVIDIA compute libraries. The
matching `libnvidia-gl-570-server` userspace package was installed and the
instance rebooted once, producing an aligned 570.195.03 kernel/userspace driver.
`vulkaninfo` then identified the A100 through the NVIDIA proprietary driver and
the ManiSkill RGB smoke passed. No RLinf source was modified.

## Asset verification

The official RLT guide confirms this aligned asset set:

- base model: `lerobot/pi05_base`;
- demonstrations: `RLinf/rlt-maniskill-PegInsertionSide-v1-400-succ`;
- OpenPI dataconfig: `pi05_rlt_maniskill_joint`;
- normalization: the `norm_stats.json` shipped/computed for that same dataset.

The assets were downloaded under `/home/ubuntu/qualia/assets` and verified:

- π0.5 directory: 14 GiB; `model.safetensors` is 14,467,165,872 bytes;
- dataset directory: 9.2 GiB;
- 400 episode parquet files, 28,681 frames, Panda robot, 10 Hz;
- matched `norm_stats.json` present and loaded by the upstream smoke;
- installed RLinf virtual environment: 13 GiB.

All six D1 Hydra profiles composed with `--cfg job --resolve`; the resolved
files are stored under `results/stage2-a100/resolved-configs/`.

## Bounded upstream logging smoke

The unmodified upstream Stage-1 entrypoint ran for one optimizer step with the
official model, full dataset, and matched norm stats. Smoke-only runtime
overrides used batch size one, disabled checkpointing/W&B output, and enabled
the supported `train_expert_only`/`use_orig_params` memory path. This is logging
evidence, not a representative timing or performance result.

Visible metrics:

- `train/loss=4.12`;
- `train/rlt_loss=4.11`;
- `train/vla_loss=0.00979`;
- `train/grad_norm=2.22`;
- `time/step=87.3s`;
- observed VRAM during loading/training: approximately 19.1 GiB.

The optimizer step completed before DataLoader shared-memory cleanup warnings.
After exit, no RLinf/Ray training process remained and the GPU was idle. The
raw log is stored at `results/stage2-a100/run.log`.

## Remaining live-pod gate

Before Stage 2 can be closed:

1. authenticate W&B directly on the instance without placing the API key in
   chat or repository files;
2. record the provider UI's final spend immediately before shutdown.
