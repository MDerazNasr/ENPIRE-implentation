# D2 Paid Configuration-Attachment Profile

Status: **designed; implementation and explicit paid approval pending**.

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

## Required implementation before approval

1. Add a `paid_acceptance` authorization that binds an exact campaign and
   approval but cannot accept a scientific gate or promotion permission.
2. Add a coordinator terminal path that retains normalized evidence without
   calling the evaluator or incumbent store.
3. Add a Modal adapter that consumes the immutable supervisor plan, verifies
   candidate source/config identity remotely, and returns manifest, log,
   resource, cost, and offline-W&B artifacts.
4. Add adversarial tests for missing approval, missing acknowledgement,
   changed plan/config, input-hash mismatch, timeout, cost overrun, missing
   artifacts, and any attempted evaluator/incumbent access.
5. Run the complete no-call suite and commit the implementation. Only that
   clean commit may be used to derive the final campaign, approval, plan, and
   command hashes.
6. Present those hashes and this USD `3.00` / 1,800-second ceiling for explicit
   user approval. No current instruction authorizes the paid launch.

## Result reconciliation

Success or failure must be preserved. The final record must include Modal app
and function-call identity, requested/observed resources, exact start/end and
exit status, provider cost evidence, resolved config and command hashes,
manifest and raw-log hashes, input hashes, offline-W&B bundle status, cleanup
state, and proof that the evaluator/incumbent were never invoked.
