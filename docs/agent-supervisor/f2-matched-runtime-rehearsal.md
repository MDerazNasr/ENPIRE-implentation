# F2 Matched-Runtime Rehearsal

Status: **historical preflight/runbook from 2026-09-06; superseded by the
passed H100 PCIe attempt-7 amendment and terminal evidence**

Current result: F2 passed on 2026-09-10. See
[`f2-h100-pcie-instance-7-amendment.md`](f2-h100-pcie-instance-7-amendment.md)
and
[`../../results/runtime-qualification/f2/h100-pcie-attempt-7/terminal.json`](../../results/runtime-qualification/f2/h100-pcie-attempt-7/terminal.json).
The preflight and launch instructions below are retained as historical process
evidence and do not authorize a rerun.

F2 is an engineering qualification. It cannot supply policy-quality evidence,
change the D1 decision, or promote a Candidate. The fixed application runs no
evaluation and accepts no caller-selected command, profile, target, arm, run
ID, or concurrency.

## Frozen live sequence

One serialized Modal function on the F0 runtime performs:

1. a Control-shaped one-step rehearsal with 16 train environments, four
   rollout epochs, 64 trajectories, horizon 500, and a step-1 checkpoint;
2. a Candidate-shaped rehearsal with the identical execution shape and only
   the registered BC-weight intervention;
3. the existing two-process micro-gate that checkpoints after update one and
   resumes at update one before completing update two.

The two full-shape profiles are
[`../../configs/d1/f2_control_rehearsal.yaml`](../../configs/d1/f2_control_rehearsal.yaml)
and
[`../../configs/d1/f2_candidate_rehearsal.yaml`](../../configs/d1/f2_candidate_rehearsal.yaml).
Their only scientific differences are:

| Field | Control | Candidate |
|---|---:|---:|
| `warmup_bc_weight` | `7.0` | `5.6` |
| `online_bc_weight` | `2.5` | `2.0` |

Both arms use seed 2026 only to exercise the route. Their outputs are marked
`calibration_only`, fixed evaluation is disabled, and neither result enters a
paired evaluator.

## Runtime and resume boundary

The fixed function requests one Modal `RTX-PRO-6000`, 16 physical CPU cores,
and 96 GiB RAM. It uses the F0 platform image digest, Python 3.11.14, Torch
2.8.0+cu128, CUDA 12.8, pinned RLinf commit, CPU PhysX, Mesa llvmpipe, the
16-process adapter, actor offload disabled, CPU weight transport, and the
canonical Stage-1 actor and normalization-stat hashes.

Before either arm starts, the worker rechecks the runtime, Vulkan route, RLinf
commit, GPU memory, and large input hashes. Each full-shape step must leave the
native checkpoint inventory and strict project sidecar. The resume micro-gate
then requires:

- the same schedule fingerprint in both processes;
- `update_step=1` at the source checkpoint and `update_step=2` after resume;
- no regression in cumulative transition count;
- replay-generator state in the sidecar;
- the explicit restore marker; and
- warm-up metrics before the boundary and online metrics afterward.

Passing those checks permits only predeclared segmentation at completed runner
step boundaries, with the same segment schedule for paired arms. Every
continuation must restore both the native checkpoint and strict sidecar. The
project still does not claim bitwise-identical simulator state across
processes. A failed live gate leaves uninterrupted execution as required until
the failure is resolved.

## Spend envelope

Pricing was rechecked on 2026-09-06. Modal lists RTX PRO 6000 at
`$0.000842/GPU-second`, physical CPU at `$0.0000131/core-second`, and memory at
`$0.00000222/GiB-second`. The frozen 16-core/96-GiB request is therefore
`$4.552992/hour`. Modal documents per-second billing based on resources used or
requested, with no reservation or minimum increment.

The function hard-stops at 9,000 seconds. Its exact maximum runtime-resource
charge is `$11.382480`; the explicit approval envelope rounds the maximum total
provider charge to **$12.00**. The historical 64-trajectory capacity rehearsal
took 1,272.4 seconds, but F2 will replace historical extrapolation with the
measured end-to-end Control, Candidate, resume-chain, and provider-billing
records. Deployment alone must scale to zero and does not authorize the GPU
call.

Authoritative current pricing and billing behavior:

- [Modal pricing](https://modal.com/pricing)
- [Modal billing](https://modal.com/docs/guide/billing)
- [Modal CPU and memory resources](https://modal.com/docs/guide/resources)

## Least-authority boundary

[`../../modal_f2_rehearsal.py`](../../modal_f2_rehearsal.py) is a fixed
human-approved qualification launcher, not a general agent tool. The agentic
harness continues to use the `ExperimentWorker` interface and the fixed Modal
RPC transport proven in F1. F2 does not add shell authority or let an agent
select infrastructure, commands, profiles, budgets, or evidence semantics.
The definitive worker activation remains gated on F2 and the G0 preregistration.

## Local verification and launch boundary

No-launch validation:

```bash
python3 scripts/run_f2_rehearsal.py
python3 -m pytest -q
```

After the implementation is committed, generate the immutable preflight from
a clean worktree:

```bash
python3 scripts/run_f2_rehearsal.py --write-preflight
```

Only a separate approval that names the clean source commit, source-bundle
hash, fixed sequence, 9,000-second cap, and `$12.00` ceiling may authorize:

```bash
modal deploy --strategy recreate modal_f2_rehearsal.py
modal run modal_f2_rehearsal.py
```

The operator was required to preserve the attempt record and tagged billing,
verify that the app had zero running tasks, and then update the F2 checklist
and cost projection. Attempt 7 supplied that evidence and closed Gate F2. Any
new rehearsal or scientific run requires a new frozen protocol and approval.
