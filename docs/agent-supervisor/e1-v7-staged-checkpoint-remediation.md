# E1 v7 Staged-Checkpoint Remediation

Status: offline implementation; **non-authorizing**

## Failure addressed

V6 shard 1 waited about 24 minutes for L40S capacity. The static temporary AWS
credentials supplied when the call was submitted were then rejected by S3 at
the first `HeadObject`, before checkpoint download, run-directory creation,
rollout, or metric production. The HTTP 400 is consistent with credential
expiry, although S3 did not return a more specific cause. Because download
preceded the v6 receipt boundary, the remote attempt also emitted no receipt.

## V7 boundary

V7 separates data transport from GPU evaluation:

1. A create-only CPU function receives a newly minted one-hour verifier-role
   session only when at least 3,500 seconds remain.
2. It downloads the exact versioned checkpoint once into a unique Modal Volume
   staging path, verifies the 10,015,912,662-byte size and frozen SHA-256, then
   atomically exposes the final path.
3. It emits a create-only terminal receipt on both success and ordinary Python
   failure. Provider exceptions are reduced to bounded text before re-raising.
4. The v7 GPU evaluator has no AWS secret, boto3 import, or S3 download path.
   Every shard independently reloads the stage receipt and rehashes the staged
   10 GB checkpoint before constructing RLinf.
5. V7 refuses shard 0 because its v6 receipt is already valid. It permits only
   replacement shard 1 followed sequentially by shards 2 and 3.
6. Every v7 evaluation failure occurring inside the function writes a bounded,
   non-authorizing terminal receipt. Modal infrastructure termination can still
   prevent `finally` from running and remains an explicit limitation.

The frozen policy, checkpoint identity, evaluator source hash, reset artifact,
64-trajectory shard boundaries, 500-step horizon, and primary endpoint do not
change. The existing v6 shard-0 receipt and future valid v7 shard receipts can
therefore enter the same strict offline four-shard aggregator.

## Budget boundary

- Staging: CPU only, 2 CPUs, 4 GiB memory, 30-minute timeout, zero retries,
  proposed absolute authorization cap `$1.00`.
- Remaining GPU work: three L40S shards, one hour each, zero retries, maximum
  GPU-runtime estimate `$5.8536`.
- Recorded cumulative D1 after shard 0: `$10.741454814583118`.
- Proposed maximum including staging cap and remaining GPU estimates:
  `$17.595054814583118`, below the existing `$18` ceiling.
- Queue time, source upload, checkpoint access, staging, and replacement shard
  execution remain unauthorized by this document.

## Required next authorization

After source review and read-only empty-destination checks, a new approval must
name: one CPU checkpoint-stage attempt, exact checkpoint identity, `$1` stage
cap, replacement shard 1 then shards 2 and 3 sequentially, zero retries,
`$5.8536` remaining GPU-runtime estimate, and the `$18` cumulative ceiling.
It must not authorize shard 0, final resets, E2, selection, or promotion.

## Offline verification

```bash
python3 -m unittest \
  tests.test_e1_sharded_evaluation \
  tests.test_modal_adapter \
  tests.test_d1 -v
```

The staging wrapper defaults to a no-cloud dry run. No Modal app, function,
checkpoint access, volume mutation, GPU, simulator, or paid work is performed
by this remediation gate.
