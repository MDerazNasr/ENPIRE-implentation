# D2 Paid Configuration-Attachment Profile

Status: **implemented; no-launch preflight and explicit paid approval pending**.

This profile defines the smallest useful paid test of the configuration-mode
attachment on the already qualified Modal runtime. It is engineering
acceptance only. It cannot become scientific evidence, enter the D1 evaluator,
or change an incumbent.

The machine-readable design is
[`../../results/provider-acceptance/d2/profile.json`](../../results/provider-acceptance/d2/profile.json).

## Why the existing paid mode cannot be reused

`ExecutionMode.PAID` correctly requires a reviewed, replay-equivalent D1
scientific pack. The current pack readiness record has eleven unresolved
packaging, provenance, approval, and scientific gaps. Weakening that gate for a
non-scientific systems test would violate the program's governing decision.

D2 therefore needs a separate `paid_acceptance` authority with all of the
normal approval, cost, wall-time, hash, process, and evidence checks, plus a
stronger negative permission: evaluation and promotion are forbidden. This is
not an exception to scientific paid mode; it is a distinct terminal engineering
workflow.

## Minimal workload

| Item | Frozen design value |
|---|---|
| Provider/profile | Modal / `deraznasr776` |
| Worker | one Nvidia RTX PRO 6000 |
| CPU / memory | 16 physical cores / 96 GiB |
| Persistent volume | `enpire-workspace` |
| RLinf | `c90951a0c799a750cb5294ed10587c61cc2af8bf` |
| Stage-1 actor | SHA-256 `b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3` |
| Norm statistics | SHA-256 `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd` |
| Seed | `2026` |
| Training | one runner step, one environment, one rollout epoch |
| Evaluation | one fixed-reset trajectory, 20-step horizon |
| Configuration delta | online BC weight `2.5` to `2.25` |
| Tracking | W&B offline; retain and hash the offline bundle |
| Hard wall time | 1,800 seconds |
| Scientific decision | prohibited |
| Incumbent update | prohibited |

The parameter delta exists only to prove that an allowlisted proposal changes
the resolved RLinf command actually executed. No performance inference may be
drawn from one seed, one training step, or one evaluation trajectory.

## Cost envelope

The [Modal pricing page](https://modal.com/pricing) was checked at
`2026-09-02T21:09:03Z` and published these per-second prices:

- RTX PRO 6000 GPU: USD `0.000842`;
- physical CPU core: USD `0.0000131`; and
- memory GiB: USD `0.00000222`.

At the 1,800-second hard limit, the requested runtime resources cost at most:

| Component | Calculation | Maximum USD |
|---|---:|---:|
| GPU | `0.000842 × 1800` | `1.515600` |
| CPU | `0.0000131 × 16 × 1800` | `0.377280` |
| Memory | `0.00000222 × 96 × 1800` | `0.383616` |
| Runtime resources | sum | `2.276496` |
| Build/control reserve | fixed remainder | `0.723504` |
| Total approval ceiling | hard program envelope | **`3.00`** |

The eventual implementation must enforce the wall-time limit independently of
the RLinf process and stop before the approved total can be exceeded. If Modal
pricing changes before approval or launch, the profile must be regenerated and
reapproved.

## Read-only worker preflight

On 2026-09-02:

- local Modal client `1.5.3` authenticated as `deraznasr776`;
- `modal app list --json` returned no running apps;
- `enpire-workspace` existed; and
- the expected Stage-1 actor path was listed at 9.3 GiB.

The directory listing is not a fresh content-hash proof. The paid worker must
rehash the exact actor and norm-stat inputs before RLinf starts and fail without
training if either differs.

## Implemented approval boundary

Commits `50bd6c5`, `9dc0d72`, `b3c772e`, `9cfa154`, and `e922328`
implement:

1. a `paid_acceptance` authorization that binds a dedicated engineering
   approval and rejects scientific-gate attachment;
2. an approval wrapper binding provider, provider profile, profile hash, total
   provider cost, and permanent `promotion_allowed=false`;
3. a coordinator terminal `recorded` path that cannot call the evaluator or
   incumbent store;
4. an immutable Modal request/receipt adapter binding the plan, resolved
   config, candidate source bundle, worker, manifest, log, remote inventory,
   and persistent volume paths by hash;
5. a one-step D1 configuration plus harness-owned config/command checker; and
6. a two-stage runner whose preflight cannot carry approval or acknowledgement
   and whose execution mode cannot run without both.

Focused authority, coordinator, contract, Git replay, configuration, and Modal
request/receipt tests pass. The next action is the no-launch preflight from a
clean commit. It will create the deterministic fixture candidate and emit the
exact campaign, candidate, plan, logical-command, and Modal-request hashes.
Those hashes and this USD `3.00` / 1,800-second ceiling must then receive
explicit user approval. No current instruction authorizes the paid launch.

## Immutable preflight

The no-launch preflight passed from clean implementation commit `e922328`.
It created one isolated fixture candidate, passed both harness-owned checks,
generated the worker-owned resolved configuration, and constructed the exact
Modal request. Stable HEAD, index, and status were identical before and after;
no Modal command, GPU, or paid resource was invoked.

| Identity | SHA-256 / Git object |
|---|---|
| Profile | `7f540dcf3e9a0fd4468a3eed47adf6955ea56efeb6a120637740f8653f815315` |
| Campaign | `7727823354d20ba704fd5fe41d7ab15741f1b0a29bb3652d2e2d819083c128e4` |
| Candidate commit | `152cf9028fb8f94a66b352fbcb8f4cc7de2a7bcc` |
| Candidate tree | `6948f66183ea982fdcbba2980ead6b168f015516` |
| Resolved config | `6d4d1643c0f845bbc9d5297d3e4987e6ef99f1c4700410900e0c6e82eff33e1e` |
| Logical RLinf command | `05e70e5ef9615d376f82ed9242e4d18836b02a0d17efb843ee5e4aec3d2088db` |
| Launch plan | `3be13891068c4f3f8682be6813f8099e19c6a762bc3a8cc4d4fece6d5e811331` |
| Modal request | `93246272d36f9cc864b1aa0da5fe57010838f443f3d902add2e5268c1de91eb8` |
| Candidate source bundle | `e8373fb0400bff33fee888b808a59965d202b345294fd67b11721c34f8f843d9` |

The complete preflight is
[`../../results/provider-acceptance/d2/preflight.json`](../../results/provider-acceptance/d2/preflight.json),
SHA-256
`0933067a6d4edde1da78e21a80782bb6b8873f2cbd0e332e2c5c11243655556b`.
Its `execution_authorized` and `promotion_authorized` fields are both false.

The local system `modal` executable uses its bundled Modal SDK `1.5.3`; the
generic project Python does not include that SDK. The actual invocation is
therefore intentionally performed by the `/opt/homebrew/bin/modal` executable,
whose bundled interpreter successfully imported this application in the
no-call check.

## Result reconciliation

Success or failure must be preserved. The final record must include Modal app
and function-call identity, requested/observed resources, exact start/end and
exit status, provider cost evidence, resolved config and command hashes,
manifest and raw-log hashes, input hashes, offline-W&B bundle status, cleanup
state, and proof that the evaluator/incumbent were never invoked.
