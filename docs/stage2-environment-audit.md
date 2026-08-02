# Stage 2 Environment and Upstream Audit

Status: partially complete; live pod gate blocked because the previous RunPod
container no longer exists. No paid training was launched.

## Connectivity result

- Previous direct endpoint `103.196.86.46:20528`: connection refused.
- Previous RunPod proxy container ID: `container not found`.
- Conclusion: the earlier L40S pod is stopped/deleted or has been replaced. A
  current SSH endpoint is required for GPU, assets, W&B, and upstream smoke
  verification.

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

## Remaining live-pod gate

Before Stage 2 can pass:

1. obtain the current RunPod SSH endpoint and hourly price;
2. verify the NVIDIA GPU has at least 24 GB VRAM;
3. verify the pinned RLinf environment and clean tree;
4. verify the full 400-episode dataset, matched `norm_stats.json`, base model,
   identifiers, and disk use;
5. authenticate W&B directly on the pod;
6. validate CUDA and ManiSkill reset/step;
7. compose/print the six resolved Hydra configurations in the installed
   environment;
8. run only the bounded upstream logging smoke required by Stage 2;
9. record actual provider spend and confirm pod billing state.

