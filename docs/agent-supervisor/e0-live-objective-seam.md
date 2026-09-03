# E0 Live Actor-Objective Seam Freeze

Status: complete on 2026-09-03. This is a source and ABI gate; it did not
launch training or consume another paid-run authorization.

## Frozen upstream identity

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- RLT worker: `rlinf/workers/actor/fsdp_rlt_ac_policy_worker.py`, SHA-256
  `b2d5032400a63c2592b6175d524cac936c282f5a287e448dbcc5da7ad42d1fc2`.
- Inherited SAC update loop:
  `rlinf/workers/actor/fsdp_sac_policy_worker.py`, SHA-256
  `190165b7bac7c934a3d80eb69ebf65f218925c810c91ae29c22e8b8dea267765`.
- Stage-2 configuration:
  `examples/embodiment/config/maniskill_rlt_stage2_ac_mlp.yaml`, SHA-256
  `bb5c01c0db25fcd962b5fa21d2fe60505ed73ed86bb8875e19167378d6456457`.
- Seam contract: `rlinf-rlt-actor-objective-seam-v1`.

The tracked `scripts/audit_e0_rlinf_seam.py` check independently verifies the
commit, all three file hashes, and the critical source statements. Any upstream
or local drift fails closed before attachment.

## Exact live path

The synchronous Stage-2 entrypoint selects `RLTACFSDPPolicy`. Its method
resolution order takes `forward_actor` from `RLTACLossMixin`. Within that
method, pinned RLinf:

1. obtains policy actions `pi` from the SAC forward pass;
2. obtains all critic heads for `pi` and selects Q1 as `all_qf_pi[..., 0:1]`;
3. reduces Q1 with `qf_pi.mean()`;
4. reshapes policy, replay, and reference actions to
   `[batch, num_action_chunks, action_dim]`;
5. computes squared BC error, reduces the action dimension, then takes a global
   mean to produce `bc_loss`;
6. resolves Python-float `bc_weight` and `q_weight` values from the fixed or
   scheduled configuration; and
7. executes the exact combination
   `-q_weight * qf_pi.mean() + bc_weight * bc_loss`.

The inherited `EmbodiedSACFSDPPolicy.update_one_epoch` receives that scalar,
divides it by `gradient_accumulation`, calls `backward()`, clips actor gradients,
and steps the actor optimizer.

## Live tensor ABI

| Value | Shape and reduction | Dtype and device | Autograd expectation |
| --- | --- | --- | --- |
| `qf_pi` | Q1 slice, normally `[micro_batch, 1]`; global mean becomes a rank-0 tensor | model output floating dtype on the worker device | connected to the policy action and differentiable Q path |
| `bc_loss` | policy/action/reference chunks are `[micro_batch, chunks, action_dim]`; MSE is averaged over `action_dim`, then globally averaged to rank 0 | inherited from policy-action arithmetic on the same worker device | connected to policy action; targets and masks do not require gradients |
| `q_weight`, `bc_weight` | Python scalar floats | promoted by PyTorch during tensor multiplication | deliberately non-trainable |
| combined objective | rank-0 scalar; no extra reduction in the overlay | PyTorch-promoted compatible floating dtype on the same device | must retain both input paths and support `backward()` |

There is no explicit autocast block around this method. FSDP strategy/model
configuration owns parameter precision; when `torch_dtype` is unset, the SAC
worker derives it from the wrapped model. The overlay must not cast, detach,
move, clone, call `.item()`, or independently divide the objective. Existing
metric calls detach only their diagnostic copies.

The source inspection establishes the structural ABI. E1 must confirm exact
runtime shapes, dtypes, devices, values, and gradients using real PyTorch
tensors before a live code candidate can run.

## Attachment decision

Use the established project-root `sitecustomize.py` boundary with a new,
explicit opt-in environment flag. Its installer will:

1. run the E0 seam audit against `RLINF_HOME`;
2. load and hash the validated M6 objective plugin;
3. replace only `RLTACLossMixin.forward_actor` with a harness-owned frozen
   adapter implementation;
4. preserve all upstream policy, critic, replay, schedule, optimizer, FSDP,
   and entrypoint behavior around the single objective delegation; and
5. emit a machine-readable installation marker before training.

The adapter passes `-q_weight * qf_pi.mean()` as the M6 `actor_loss` argument,
plus the live `bc_loss` and `bc_weight`. Therefore the existing
`m6-actor-objective-v1` default remains exactly the upstream expression without
an ABI change. Both synchronous and asynchronous classes inherit the patched
mixin method. No file in the RLinf checkout is edited.

The installer must be idempotent and fail closed for a missing opt-in, wrong
commit, wrong source hash, wrong plugin hash, unsupported contract, duplicate
incompatible patch, or invalid plugin. Implementation and equivalence proof are
E1, not E0.

## Required manifest proof

A code-enabled live run is not valid unless its plan, launcher manifest,
runtime installation marker, and normalized evidence agree on this record:

```json
{
  "attachment_mode": "sitecustomize-rlt-loss-mixin-v1",
  "seam_contract_version": "rlinf-rlt-actor-objective-seam-v1",
  "objective_contract_version": "m6-actor-objective-v1",
  "objective_relative_path": "supervisor/objectives/actor_objective.py",
  "objective_sha256": "<exact candidate source hash>",
  "adapter_sha256": "<exact harness adapter source hash>",
  "rlinf_commit": "c90951a0c799a750cb5294ed10587c61cc2af8bf",
  "rlinf_worker_sha256": "b2d5032400a63c2592b6175d524cac936c282f5a287e448dbcc5da7ad42d1fc2",
  "installed_target": "RLTACLossMixin.forward_actor"
}
```

E2 owns launcher/manifest enforcement. Merely placing the project on
`PYTHONPATH` or validating the plugin in a separate process is not proof that
the training worker loaded it.

## E0 conclusion

The live ABI is explicit and reviewable, the pinned upstream inputs are
machine-frozen, the v1 plugin contract remains valid, and the chosen attachment
does not modify canonical RLinf. E0 passes. The next gate is E1: implement the
opt-in adapter and prove default forward/gradient equivalence in real PyTorch.
