# E1 Default Objective Equivalence

Status: passed on 2026-09-03. This gate implemented the E0 attachment and
proved that its default objective is behaviorally identical to pinned RLinf.

## Implementation

`agent/rlt_objective_attachment.py` provides the project-owned live boundary.
It is activated only when `QUALIA_RLT_OBJECTIVE=1` causes `sitecustomize.py` to
call its installer. The installer requires:

- `RLINF_HOME`;
- `QUALIA_RLT_OBJECTIVE_PLUGIN`;
- `QUALIA_RLT_OBJECTIVE_SHA256`;
- `QUALIA_RLT_OBJECTIVE_CONTRACT_VERSION`; and
- optionally `QUALIA_RLT_OBJECTIVE_DISPLAY_PATH`, which otherwise uses the M6
  canonical path.

Before patching it verifies the E0 RLinf commit and three frozen source hashes,
the exact plugin hash, static M6 ABI, contract version, and display path. It
then loads the plugin, replaces only `RLTACLossMixin.forward_actor`, preserves
the upstream timer and all surrounding logic, and emits the complete canonical
attachment record as `QUALIA_RLT_OBJECTIVE_ATTACHMENT=<json>`.

The installation is idempotent only for the identical record. A second,
incompatible attachment fails closed. The live adapter also rejects a return
that is not a rank-0 PyTorch tensor, changes the Q-term dtype/device,
disconnects required autograd, or is non-finite.

Adapter SHA-256 for this gate:
`fb51edc77fe1602405d32f6f219ad499fba209efe78e1b9a8ad5b415071418a1`.
Default objective SHA-256:
`480eafcad7a1fb01fdf12d4bfc4b39b52696942fb0c9bf9ccbdc4e549b97896c`.

## Frozen equivalence rule

Before any code candidate result is viewed, default equivalence requires:

- absolute loss difference exactly `0.0`;
- maximum absolute policy-action gradient difference exactly `0.0`;
- identical rank-0 shape, dtype, and device;
- identical entropy and diagnostic metrics; and
- successful backward after the inherited gradient-accumulation division.

Exact equality is appropriate because the default adapter preserves operand
order and delegates the same two scalar tensor terms without an additional
cast, reduction, or rearrangement. A future implementation change must freeze
new tolerances before examining candidate results.

## PyTorch proof

The tracked `scripts/probe_e1_objective_equivalence.py` loaded the exact
hash-verified worker file from RLinf commit `c90951a0...`, captured its native
decorated method, installed the live overlay, and exercised both methods with
the same model fixture. Only unrelated distributed, Ray, replay, and simulator
imports were replaced by hermetic stubs; the objective method and its helper
methods were the actual pinned source.

PyTorch `2.8.0` on CPU passed four cases:

| Case | Policy shape | Dtype | Q/BC weights | Mask | Accumulation | Loss/value diff/gradient diff |
| --- | --- | --- | --- | --- | --- | --- |
| single | `[1,1,2]` | float32 | `1.0/1.0` | no | 1 | `2.25 / 0 / 0` |
| online | `[3,2,4]` | float64 | `0.45/2.5` | yes | 4 | `1.045604944229126 / 0 / 0` |
| zero weights | `[2,3,7]` | float32 | `0/0` | yes | 3 | `0 / 0 / 0` |
| warmup | `[2,4,7]` | bfloat16 | `0.05/7.0` | no | 2 | `0.08251953125 / 0 / 0` |

Negative controls for disconnected autograd, a non-finite scalar, and a
wrong-shape tensor were all rejected. The canonical record is
`results/agent-supervisor/e1/default-equivalence.json`.

## Device limitation

The user-selected Lambda A10 stopped accepting SSH before the E1 probe could
start. Two connection attempts timed out; no remote Python process, rollout,
training step, or checkpoint was launched. Local MPS was also unavailable.
Consequently this gate proves the live tensor algebra and autograd on a real
CPU PyTorch device, not CUDA execution inside a complete Ray/FSDP worker.

This does not weaken the exact-equivalence result: native and patched methods
executed the same frozen PyTorch source path and exact equality is required.
CUDA, full worker initialization, resource behavior, and runtime compatibility
remain explicit Workstream F qualification obligations before scientific use.

## E1 conclusion

The default overlay is exactly equivalent under the frozen rule, provenance is
emitted at installation, and malformed runtime outputs fail closed. E1 passes.
E2 is next: prove one bounded, non-no-op objective candidate and bind its source
identity through plan, command, manifest, runtime marker, and evidence without
making an improvement claim.
