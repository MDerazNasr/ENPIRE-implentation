# G0 Runtime, Cost, and Retention Freeze Candidate

Status: **Lambda H100 PCIe selected as the preferred design and the exact host
passed read-only qualification; exact-image/route qualification, storage,
human protocol acceptance, paid scientific execution, and promotion remain
unauthorized**

Obsidian task: `MI5T8`

This document turns existing engineering evidence into a reviewable G0
proposal. It does not relabel F0/F2 or historical one-seed runs as scientific
evidence, and it does not authorize a provider call, GPU, model transfer,
evaluation, campaign activation, or promotion.

## Runtime candidates

| Option | Evidence | Current disposition |
|---|---|---|
| Modal RTX PRO 6000 | F0 selected a 96 GB matched scientific runtime with the pinned linux/amd64 CUDA image and 16-process CPU-physics adapter | Preserved version-1 candidate; not selected for the current campaign |
| Lambda H100 PCIe | F2 attempt 7 completed the four-run engineering rehearsal and ten resume checks; instance `15c6fcfe...9b688` passed a fresh read-only host qualification on 2026-09-12 | Preferred version-2 design; exact image, source, assets, no-outcome route, durable storage, and sufficient lifetime remain unqualified |

The user selected Lambda H100 PCIe after comparing currently available GPU
prices. The exact host is Lambda instance
`15c6fcfe96f946baa1e440d55ac9b688`, Utah, IP `209.20.157.138`, at the
user-reported `$3.29/hour`. Read-only inspection confirmed Ubuntu 22.04.5,
26 CPUs, 237,490,954,240 bytes RAM, 1,038,689,009,664 bytes free, H100 PCIe
81,559 MiB, driver 570.148.08, Docker/NVIDIA tooling, and zero containers,
GPU processes, or ENPIRE workload processes. This is host qualification only.
A fresh qualification must still bind the exact image, clean source, assets,
no-outcome route, observed rate, durable storage, and terminal idle lifecycle.

Shared candidate identities already available:

- task `PegInsertionSideWideClearance-v1`;
- RLinf `c90951a0c799a750cb5294ed10587c61cc2af8bf`;
- ManiSkill `33967b9e3ead1f841eec57cc9f31d0d8b8cf0907`;
- SAPIEN `3.0.1`;
- base pi0.5 weights SHA-256
  `0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f`;
- dataset identity `rlt-maniskill-PegInsertionSide-v1-400-succ`, revision
  `2b92d5ef3fe274d30219130133f9e34c7ab91ebf`;
- norm statistics SHA-256
  `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd`;
- development reset fingerprint `e5466ff2...e161`; and
- final reset fingerprint `27165db0...fa97`.

Six bindings remain deliberately unresolved:

1. clean scientific project commit;
2. fresh runtime qualification receipt;
3. production evaluator environment SHA-256; and
4. durable off-host checkpoint/evidence storage;
5. Lambda storage and egress pricing; and
6. the E1-selected Stage-1 actor SHA-256 required before E2.

E1 cannot predeclare its selected output actor. Instead, its frozen selection
rule must produce that actor, which must then be independently size/hash
verified and inserted into a separate E2 preflight before any E2 dispatch.

## Current Lambda pricing snapshot

The user-supplied Lambda dashboard listed the selected H100 PCIe instance at
`$3.29/hour` on 2026-09-12. The provider storage and egress prices were not
supplied and are intentionally unresolved. The current 5h59m auto-shutdown
window is insufficient for the proposed 24-hour E1 or 48-hour E2 attempt caps.
It must be extended, or an approved segmented/checkpointed schedule with a
durable off-host store must replace those caps, before scientific execution.

The version-2 compute-only arithmetic is:

| Phase | Original runs | Attempts/run | Timeout/attempt | Cap/attempt | Retry-inclusive compute |
|---|---:|---:|---:|---:|---:|
| E0 | GPU-free | 1 | local | `$0` | `$0` |
| E1 | 1 | 2 | 24 hours | `$78.96` | `$157.92` |
| E2 | 6 | 2 | 48 hours | `$157.92` | `$1,895.04` |

The compute-only ceiling is `$2,052.96`. A total-program ceiling cannot yet
be stated because durable storage and egress pricing are unresolved.

## Preserved Modal version-1 snapshot

The official Modal pricing page was checked read-only on 2026-09-11. It lists:

| Resource | Rate |
|---|---:|
| RTX PRO 6000 | `$0.000842/GPU-second` |
| Physical CPU core | `$0.0000131/core-second` |
| Memory | `$0.00000222/GiB-second` |
| Volume storage | `$0.09/GiB-month` |

For the F0 request of one GPU, 16 physical cores, and 96 GiB memory, the exact
requested-resource arithmetic is `$4.552992/hour`. Pricing must be rechecked
immediately before any paid approval. Source:
[Modal pricing](https://modal.com/pricing).

No current Lambda price is used. The prior `$3.29/hour` is retained only as
historical F2 evidence and cannot support a new approval.

## Preserved version-1 worst-case envelope

| Phase | Original runs | Attempts/run | Timeout/attempt | Cap/attempt | Retry-inclusive compute |
|---|---:|---:|---:|---:|---:|
| E0 | GPU-free | 1 | local | `$0` | `$0` |
| E1 | 1 | 2 | 24 hours | `$110` | `$220` |
| E2 | 6 | 2 | 48 hours | `$220` | `$2,640` |

Additional proposed ceilings:

- maximum concurrency: `3`;
- total wall-clock window: `864,000` seconds (10 days);
- compute ceiling: `$2,860`;
- storage ceiling: `500 GiB` for one budgeted month, `$45`;
- total compute-plus-one-month-storage ceiling: `$2,905` (Modal version 1 only); and
- notifications at 25%, 50%, 75%, and 90%, with dispatch blocked at either
  the time or compute cap.

The envelope is deliberately retry-inclusive. A second attempt is permitted
only for a preregistered infrastructure/transport failure before a usable
policy outcome. Numerical failure, invalid evidence, timeout after workload
start, and underperformance are not retryable by default. Unused retry budget
does not become authority for extra trials.

Sizing evidence is heterogeneous and must not be overinterpreted:

- a 250-step Stage-1 H100 run took 5,257.78 seconds and cost about `$4.81`;
- the historical segmented 100-step Modal Candidate took 109,669 seconds and
  had a `$92.31` launcher estimate, but was scientifically inconclusive; and
- F2 attempt 7 cost `$3.70829`, but exercised only bounded engineering routes.

These observations justify conservative review caps, not expected cost or
scientific comparability. A fresh no-outcome qualification must demonstrate
that the selected cap can contain the frozen route before paid authorization.

## Retention proposal

- Compact manifests, metrics, logs, costs, hashes, failures, decisions, and
  lineage remain indefinitely in Git.
- Failed, interrupted, reverted, retried, and inconclusive evidence is retained.
- Private models and large replay/checkpoint artifacts never enter Git.
- Large artifacts remain for at least 30 days after terminal reconciliation.
- Large deletion is never automatic; it requires verified export, manifest
  reconciliation, and separate human approval.
- Hash-bound evaluator evidence is authoritative. W&B or object storage may
  mirror it but cannot replace it.

## Machine-readable candidates

- [`../../results/agent-supervisor/g0/runtime-identities-candidate-v1.json`](../../results/agent-supervisor/g0/runtime-identities-candidate-v1.json)
- [`../../results/agent-supervisor/g0/cost-envelope-candidate-v1.json`](../../results/agent-supervisor/g0/cost-envelope-candidate-v1.json)
- [`../../results/agent-supervisor/g0/runtime-identities-candidate-v2.json`](../../results/agent-supervisor/g0/runtime-identities-candidate-v2.json)
- [`../../results/agent-supervisor/g0/cost-envelope-candidate-v2.json`](../../results/agent-supervisor/g0/cost-envelope-candidate-v2.json)
- [`../../results/runtime-qualification/g0/lambda-h100-pcie-instance-1-host.json`](../../results/runtime-qualification/g0/lambda-h100-pcie-instance-1-host.json)

The strict validator is `supervisor/g0_protocol_inputs.py`; the create-only
builder is `scripts/build_g0_runtime_cost_candidates.py`. The candidates retain
false authority fields and do not occupy the canonical readiness paths
`runtime-identities.json` or `cost-envelope.json`.

## Human decisions required

The reviewer must accept or amend the preferred runtime, timeouts, per-attempt
caps, retry-inclusive total, concurrency, storage ceiling, minimum retention,
and deletion policy. Acceptance still does not authorize a paid run: fresh
qualification and a later fingerprinted activation envelope remain mandatory.
