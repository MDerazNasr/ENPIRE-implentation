# ADR 0005: Retain Isolated Hypotheses and Never Auto-Merge

- Status: accepted
- Date: 2026-08-04

## Context

Long agent explorations can degrade a linear working tree, while deleting a
failed attempt removes useful negative evidence. A candidate also must not
become the stable implementation merely because its own tests pass.

## Decision

Create one deterministic branch and external worktree per proposal from an
explicit incumbent commit. Limit the initial policy to one changed file. Keep
failed worktrees for audit, rediscover them after restart, and fail closed on a
duplicate proposal identity. Candidate preparation may commit only on its own
hypothesis branch. It never merges or moves the stable branch.

Promotion in later milestones updates an explicit incumbent pointer only after
deterministic evaluation. Stable integration remains a human review action.

## Consequences

- Successful and failed explorations cannot contaminate each other.
- Negative attempts remain inspectable and reportable.
- Cleanup is deliberate and may consume local disk until a retention policy is
  approved.
- Expanding beyond one file requires a policy/ADR update and new contamination
  tests.

## Alternatives rejected

- Reuse one mutable agent branch: makes backtracking and attribution ambiguous.
- Delete every failed attempt automatically: loses negative evidence and
  hinders diagnosis.
- Merge after candidate-local tests: trusts unverified code and bypasses the
  external evaluator.
