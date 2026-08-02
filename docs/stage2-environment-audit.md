# Stage 2 Environment and Upstream Audit

Status: partially complete; the replacement pod passes the source, CUDA, and
ManiSkill runtime checks. The asset gate is currently blocked by the pod's
storage quota. No paid training was launched.

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

## Live installation and simulator verification

RLinf was installed with the repository's official custom-environment command
at commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`, using PyTorch
`2.8.0+cu128`. After the installer completed, the checkout was clean and its
temporary `pyproject.toml` backup was removed.

Verified runtime evidence:

- CUDA 12.8 recognizes the RTX PRO 4000 Blackwell and advertises `sm_120`;
- a CUDA tensor operation completed successfully;
- `rlinf` and ManiSkill import successfully;
- RLinf's custom `PegInsertionSideWideClearance-v1` task registered;
- one RGB, GPU-backend environment reset with seed 2026 succeeded;
- one sampled `pd_joint_delta_pos` step succeeded and the environment closed
  with exit code zero.

SAPIEN required the NVIDIA Vulkan ICD to be selected explicitly with
`VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json`. The file was installed by
the official installer; no RLinf source was modified.

## Asset verification blocker

The official RLT guide confirms this aligned asset set:

- base model: `lerobot/pi05_base`;
- demonstrations: `RLinf/rlt-maniskill-PegInsertionSide-v1-400-succ`;
- OpenPI dataconfig: `pi05_rlt_maniskill_joint`;
- normalization: the `norm_stats.json` shipped/computed for that same dataset.

Parallel resumable downloads were started under `/workspace/qualia/assets`.
The model reached a 2.8 GiB partial weight and the dataset reached 24 of 400
episode parquet files before Hugging Face failed with `Disk quota exceeded`.
The incomplete files are intentionally retained for resume. The RunPod UI's
configured volume size must be obtained and enlarged if necessary before asset
verification can pass.

## Remaining live-pod gate

Before Stage 2 can pass:

1. obtain the current RunPod hourly price and configured volume size;
2. enlarge the volume if needed and resume the base-model/dataset downloads;
3. verify the full 400-episode dataset, matched `norm_stats.json`, base model,
   identifiers, and disk use;
4. authenticate W&B directly on the pod;
5. compose/print the six resolved Hydra configurations in the installed
   environment;
6. run only the bounded upstream logging smoke required by Stage 2;
7. record actual provider spend and confirm pod billing state.
