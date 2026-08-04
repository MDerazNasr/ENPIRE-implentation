# Milestone 7 Verification Report

Date: 2026-08-04

Branch: `feature/d2-agent-supervisor`

Outcome: M7 durable multi-worker orchestration and synthetic demonstration
complete; live SSH/GPU acceptance deferred to the D1 compatibility handoff.

## Implemented

- exact-campaign durable scheduler state with atomic locking/fsync/hash checks;
- deterministic capability-aware, one-trial-per-worker scheduling;
- conservative trial, wall-time, and GPU-cost reservations;
- attempt-specific leases with immutable authorization tokens;
- real concurrent assignment execution using separate worker threads;
- worker heartbeat, lease renewal, expiry, loss, retry, and attempt caps;
- coordinator-restart polling of active durable assignments;
- idempotent duplicate completion and stale/late completion rejection;
- durable cancellation-before-best-effort-transport cancellation;
- strict evidence/contract/worker reconciliation before evaluation;
- fixed, mockable SSH RPC client with bounded canonical payloads;
- two-arm, three-seed synthetic demo composed with the frozen evaluator and
  per-arm incumbent store.

## Verification evidence

| Check | Result |
| --- | --- |
| Complete repository suite after M7 | 176 passed, 98 subtests passed |
| First demo batch | two worker threads overlapped (`maximum=2`) |
| Worker failure | one assigned worker returned `lost` |
| Retry | replacement worker accepted attempt 2 |
| Late old result | rejected as stale |
| Frozen decisions | config arm `KEEP`; code arm `REVERT` |
| Incumbent scope | only evaluator decisions changed named arm pointers |
| Stable branch moved | no |
| SSH/GPU/RLinf/provider/W&B/paid calls | none |

## Failure coverage

- duplicate dispatch after coordinator restart;
- incompatible GPU/mode and campaign concurrency;
- exhausted conservative trial budget;
- lease expiration and offline worker handling;
- worker capability identity rebinding;
- missing worker transport and lost execution;
- old completion after loss/retry or cancellation;
- cross-trial candidate/evidence contamination;
- scheduler snapshot hash tampering;
- malformed SSH hosts/helpers, remote failures, invalid JSON, identity spoofing,
  and contract-hash tampering.

## Demonstration boundary

The demo uses real threads, durable files, leases, retries, evidence contracts,
the frozen numerical evaluator, and incumbent updates. Worker results and
success metrics are deterministic fixtures. The `KEEP` and `REVERT` outcomes
prove orchestration behavior only and must not be reported as RLT results.

## Honest limitations

- The SSH client was exercised through a mock executor; no remote helper or GPU
  worker was contacted.
- Scheduler snapshots are atomic and hash-checked but require the existing
  external/ledger evidence layer for tamper-evident scientific audit.
- The synchronous local D1 worker cannot interrupt an already running process;
  its wall-time process-group termination remains the fallback.
- Real GPU utilization, detached remote restart, artifact transfer, and active
  cancellation require the D1/remote-worker compatibility handoff.
- M8 study execution and any agent-versus-rule or RLT performance conclusion
  remain unstarted.
