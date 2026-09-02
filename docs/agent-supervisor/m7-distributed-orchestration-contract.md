# M7 Distributed Orchestration Contract

Status: durable two-worker synthetic implementation complete. Live SSH/GPU
acceptance remains part of the D1 compatibility handoff.

M7 schedules independent hypotheses across independent workers. It does not
distribute one training run across several GPUs, change the M6 edit boundary,
or grant workers evaluation or promotion authority.

## Durable authority

The campaign-bound scheduler stores a hash-checked, atomically replaced state
containing:

- immutable run contracts and queue requirements;
- worker capabilities, readiness, heartbeats, and active lease pointers;
- every lease attempt and conservative resource reservation;
- completion evidence, errors, retry count, and terminal state.

The state is locked across processes, fsynced before replacement, validated on
every load, and bound to the exact campaign fingerprint. A restarted
coordinator reconstructs active assignments from this file instead of issuing
new ones.

This snapshot detects accidental or partial corruption. It is not a substitute
for the existing hash-chained trial/evidence ledgers or an externally anchored
audit record; a privileged actor able to rewrite both payload and hash remains
outside its threat model.

## Deterministic scheduling

Queued work is ordered by descending priority, enqueue time, and trial ID.
Eligible workers are ordered by worker ID. An assignment is allowed only when:

- campaign concurrency has a free slot;
- the worker supports the required execution mode;
- declared GPU memory satisfies the trial requirement;
- the worker has no other active trial;
- conservative trial, wall-time, and GPU-cost reservations fit the campaign.

M7 deliberately permits one independent trial per worker. Reservations are
charged at the immutable run-contract maximum and remain counted after loss or
cancellation. This is conservative: it may stop early but cannot silently
schedule beyond the approved envelope.

## Lease protocol

One active lease is the sole execution authority for a trial. It binds:

- lease, trial, worker, and attempt identities;
- exact run-contract hash and candidate commit;
- issue and expiration timestamps;
- maximum wall time and GPU cost;
- an authorization token derived only from immutable lease fields.

Only the matching active lease can reconcile a completion. Duplicate delivery
of the same accepted completion is idempotent. A completion from an expired,
cancelled, lost, or replaced lease is rejected as stale even when it claims
better metrics.

## Heartbeat, restart, and loss recovery

Workers may renew a live lease before expiration. After coordinator restart,
`recover_active_assignments` polls every durable assignment:

- `prepared` or `running` work receives a heartbeat and lease renewal;
- valid terminal work is normalized and reconciled;
- unavailable, malformed, or identity-mismatched transport becomes `lost`;
- lost/expired work is requeued only below the fixed attempt cap;
- the failed worker is marked offline and cannot receive new work until a new
  registered heartbeat.

Retries receive a new attempt-specific lease. Results from the old attempt no
longer have authority.

## Completion and cancellation

The scheduler independently checks worker, trial, contract, commit, seed,
reset set, evaluator, command, configuration, terminal status, and evidence
hashes. Workers return evidence; they cannot call the evaluator or update an
incumbent.

Cancellation first revokes the durable lease, then issues a best-effort worker
cancel request. Any completion racing after revocation is stale. The local M5
D1 worker cannot yet interrupt a running synchronous process and falls back to
its immutable wall-time/process-group termination. A deployed remote helper
must implement active cancellation before live acceptance.

## SSH boundary

`SshExperimentWorker` implements the existing provider-neutral worker
interface over a fixed remote RPC helper. The agent supplies no host, command,
or shell text. The harness supplies:

- validated endpoint and executable;
- fixed action name;
- URL-safe base64 canonical JSON payload;
- batch mode and bounded connect/RPC timeouts;
- strict capped JSON response parsing.

The exact `RunContract`, including candidate and RLinf commits, is sent during
prepare and verified in every returned snapshot/evidence record. M7 tests this
client with a mock executor. No SSH connection was made and no remote helper
was deployed in this milestone.

## Synthetic demonstration

`scripts/run_m7_scheduler_demo.py` queues two three-seed arms on two workers.
The first batch overlaps in two real Python threads. One worker is lost; its
trial is recovered on a replacement worker with a second lease. A late result
from the lost lease is rejected. Complete arm evidence is then passed to the
existing frozen evaluator, producing one synthetic `KEEP` and one synthetic
`REVERT`. Only those evaluator decisions update their named incumbent pointers.

The demo is orchestration evidence, not RLT performance evidence.

## Live D1 handoff

Live acceptance requires the separately owned D1 workstream to provide:

- ready, non-degenerate Stage-7 evidence and exact live objective attachment;
- deployed remote helper and environment/bootstrap contract;
- worker-side detached process identity and restart/status behavior;
- real cancellation, artifact retrieval, and GPU utilization fields;
- two authorized GPU endpoints suitable for the pinned RLT workload.

None of these gaps weakens the synthetic scheduler result, but all block claims
about real GPU scaling, utilization, reliability, or RLT improvement.
