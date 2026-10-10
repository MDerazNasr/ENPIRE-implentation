# E1 v8 Stage-Packaging Remediation

Status: offline implementation; **non-authorizing**

## Failure addressed

The one authorized stage-v1 CPU attempt created Modal app
`ap-SU26SRTsJvPFKvBHUTtDKJ` and FunctionCall
`fc-01M4J2384BZ844838JS8QT3C02`, but failed while Modal hydrated the function:
`modal_e1_checkpoint_stage_v1.py` imported `supervisor.e1_staged_checkpoint`
without packaging `supervisor/` into the image. The function body never ran.
No S3 request, checkpoint byte, volume destination, GPU, rollout, or metric was
produced. The authorized attempt is consumed and will not be retried.

## Corrected boundary

- Stage v2 explicitly copies `supervisor/` to `/root/supervisor` in its Modal
  image before function hydration.
- Stage v2 uses a new app name, role-session name, staging directory, and
  terminal-receipt path. It remains CPU-only, create-only, zero-retry, and
  capped by a 30-minute timeout.
- Evaluation v8 reads only the verified stage-v2 artifact. It retains no AWS
  credentials or S3 code, rejects shard 0, and permits only shards 1--3.
- Checkpoint version, size, SHA-256, evaluator contract, reset set, trajectory
  boundaries, horizon, primary metric, and GPU price are unchanged.

## Next gate

The corrected source and a non-authorizing remediation receipt must pass the
offline suite and be pushed before requesting new authority. A future approval
must separately authorize one stage-v2 CPU attempt. GPU shards remain
unauthorized until a valid stage-v2 receipt exists and their existing bounded
authority is explicitly renewed against the v8 source.
