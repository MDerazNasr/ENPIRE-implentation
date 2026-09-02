# ADR 0004: Separate Campaign and Trial Lifecycles

- Status: accepted
- Date: 2026-08-04

## Context

The Milestone 0 diagram placed approval, proposal execution, and keep/revert in
one linear state machine. The planned study gives one approved campaign three
discovery trials per arm. If `KEEP`, `REVERT`, or `INCONCLUSIVE` terminated the
campaign itself, the second proposal could not run without creating a new
approval envelope.

## Decision

Use a campaign lifecycle for specification validation, approval, activation,
completion, failure, and cancellation. Use an independent lifecycle for every
proposal/trial from proposing through its terminal evaluator decision. Both
event types use the same strict hash-chained ledger format and remain bound to
the campaign ID.

## Consequences

- One approval can govern multiple bounded trials without conflating their
  outcomes.
- Each hypothesis has an independently replayable decision history.
- The coordinator must later derive campaign completion from trial counts,
  budget state, and the registered study protocol.
- Cross-ledger invariants require integration tests when the coordinator is
  implemented.

## Alternative rejected

- Reset a terminal campaign state back to `proposing`: terminal states would no
  longer be terminal, and event interpretation would become ambiguous.
