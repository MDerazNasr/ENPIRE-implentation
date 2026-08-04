# ADR 0007: Preregistered Arm Isolation and Paired Confirmation

- Status: accepted
- Date: 2026-08-04
- Milestone: M8

## Context

The first deliverable must compare a transparent rule controller, a
configuration-only coding agent, and a narrowly code-enabled coding agent.
Adaptive allocation, cross-arm sharing, post-result metric changes, or choosing
only successful trials would make the comparison impossible to audit.

## Decision

Freeze and hash the exact three arms, common scientific identity, equal worker
caps, three discovery slots per arm, selection order, and paired confirmation
seeds before results are accepted. Each arm owns an independent incumbent and
may advance only through an external deterministic `KEEP`. Invalid, failed,
inconclusive, and null records consume their slot.

Select the best valid candidate mechanically within each arm after all nine
slots. Confirm only that frozen commit against the common baseline on the exact
three paired seeds. If an arm has no valid candidate, report the absence rather
than borrowing from another arm.

## Consequences

- The comparison is fixed before outcomes and negative results remain visible.
- Agent prose cannot select, evaluate, or promote a candidate.
- Iterative discoveries can advance inside one arm without contaminating the
  other arms.
- A full valid study can require 36 seed-level worker runs, even though it has
  nine discovery opportunities and three confirmation records.
- Three seeds support only the frozen paired engineering decision, not broad
  statistical superiority claims.
- Synthetic rehearsal can validate every control-plane boundary before D1;
  live activation still requires a ready D1 evidence gate.
