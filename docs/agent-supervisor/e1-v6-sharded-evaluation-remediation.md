# E1 v6 Sharded Evaluation Remediation

Status: offline implementation; **non-authorizing**

## Problem

The checkpoint-2000 v5 evaluation completed 5 of 16 rollout epochs before an
unattributed `SIGTERM`. Because RLinf emitted the aggregate metric only after
all 256 trajectories, the completed work could not be accepted or resumed.
The failure does not establish a model or evaluator defect, but it shows that
one long all-or-nothing process is fragile on preemptible infrastructure.

## Frozen v6 design

The same ordered 256-reset development artifact is partitioned before launch
into four contiguous, non-overlapping shards:

| Shard | Reset positions | Environments | Epochs | Outcomes |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0–63 | 16 | 4 | 64 |
| 1 | 64–127 | 16 | 4 | 64 |
| 2 | 128–191 | 16 | 4 | 64 |
| 3 | 192–255 | 16 | 4 | 64 |

Each shard has a separate create-only run directory and terminal receipt. A
shard uses the exact checkpoint-2000 object identity, direct OpenPI policy,
500-step horizon, development reset fingerprint, and evaluator contract hash.
It cannot retry, aggregate, select, access final resets, or promote a policy.

The offline aggregator accepts exactly one valid receipt for every index. It
rejects missing, duplicate, failed, authorizing, boundary-drifted, checkpoint-
drifted, reset-drifted, or evaluator-drifted receipts. Only then does it compute
the weighted 256-trajectory metric and produce a canonical non-authorizing
envelope.

## Runtime and budget boundary

- GPU: one Modal L40S per shard.
- Function timeout: 3,600 seconds per shard.
- Modal retries: zero.
- Maximum GPU runtime estimate: `$1.9512` per shard and `$7.8048` for four.
- Prior estimated D1 total: `$10.004226119647857`.
- Maximum projected D1 total: `$17.809026119647857`, below the existing `$18`
  aggregate ceiling.
- Shards may run sequentially. Parallel launch is not implied or authorized.
- A failed shard remains failed; any replacement requires a new explicit
  authorization and a new create-only identity.

## Claim boundary

Sharding changes failure isolation, not the policy, reset set, episode horizon,
primary endpoint, or total trajectory count. It is nevertheless a protocol
amendment and must receive explicit review before paid execution. Partial shard
sets and partial shard logs are not a checkpoint score.

## Offline verification

Run:

```bash
python3 -m unittest tests.test_e1_sharded_evaluation tests.test_modal_adapter tests.test_d1 -v
```

No Modal app, function call, GPU, checkpoint download, simulator rollout, or
paid work is performed by this gate.
