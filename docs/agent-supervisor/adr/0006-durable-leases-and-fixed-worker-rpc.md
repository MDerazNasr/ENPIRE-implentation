# ADR 0006: Durable Leases and Fixed Worker RPC

- Status: accepted
- Date: 2026-08-04
- Milestone: M7

## Context

Independent GPU hypotheses must survive coordinator restart, worker loss, and
duplicate or late messages. Giving a worker or coding agent direct queue,
evaluation, Git-promotion, or general SSH authority would collapse the trust
boundaries established in M0–M6.

## Decision

The coordinator is the sole lease authority. Every attempt receives one
campaign-bound lease over an immutable run-contract hash, candidate commit,
worker, attempt number, and expiration. Only that active lease can reconcile a
completion. Retry creates a new lease; old results become stale.

Worker RPC is a fixed harness protocol implementing prepare, launch, status,
heartbeat, cancel, and fetch-evidence. SSH endpoints and commands are
harness-owned. Payloads are canonical encoded records, not agent-authored shell
text. Workers return evidence but cannot evaluate or promote it.

Initial scheduling is deterministic and permits one independent trial per
worker. Resource reservations use run-contract maxima and remain charged after
loss, favoring early safe stop over optimistic oversubscription.

## Consequences

- Coordinator restart can reconstruct outstanding authority without duplicate
  launch.
- Worker loss and late completion cannot silently promote stale work.
- The fixed SSH protocol is mockable before D1 and remote infrastructure exist.
- Conservative reservations may underuse the campaign envelope.
- A live remote helper, authentication/deployment, real cancellation, and GPU
  utilization remain required at the D1 integration boundary.
- Scheduler snapshot integrity does not replace hash-chained evidence ledgers
  or their external anchors.
