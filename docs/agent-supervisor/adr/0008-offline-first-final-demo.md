# ADR 0008: Offline-First Final Demo with Read-Only D1 Replay

- Status: accepted
- Date: 2026-08-04
- Milestone: M9

## Context

The Ludvig meeting needs a reliable demonstration even if the separately owned
D1 baseline, remote GPUs, provider credentials, or network are unavailable.
Pretending synthetic evidence is a live result would undermine the primary
research deliverable. Launching a paid run during a presentation would also
mix demonstration reliability with scientific and infrastructure risk.

## Decision

Make the final demo offline-first and compose the already verified M4, M7, and
M8 fixture paths. Require a clean supervisor commit, output outside the
repository, unchanged HEAD, explicit synthetic labels, and a reconciled
artifact manifest.

Offer D1 only as an optional read-only audit/replay. Default mode continues
with an honest fallback when D1 is blocked. Strict mode fails before component
execution. Do not add a shortcut around M5 approval, gate, paid
acknowledgement, or worker contracts.

## Consequences

- The complete control plane can always be presented and reproduced locally.
- A pre-generated verified bundle is a trustworthy meeting fallback.
- Ready D1 evidence can be shown without risking a new training run.
- The final bundle cannot support an RLT-improvement or agent-superiority claim.
- A real three-arm study remains follow-on execution under the frozen M8
  protocol after D1 and compute are ready.
