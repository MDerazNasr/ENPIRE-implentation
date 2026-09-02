# ADR 0003: Use a Project-Owned RLT Actor-Objective Overlay

- Status: accepted
- Date: 2026-08-04

## Context

The pinned RLinf RLT Stage-2 implementation combines Q and behavior-cloning
terms inside its worker and does not expose a stable external objective hook.
The D1 contract requires the pinned upstream tree to remain unmodified, while
the coding-agent requirement includes genuine training-code changes.

## Decision

Implement a narrow project-owned adapter and actor-objective plugin. The
adapter handles the fixed worker plumbing; the plugin owns only the
differentiable objective combination and named diagnostics. The default plugin
must match the pinned upstream implementation numerically and in gradients on
fixed fixtures. Code-enabled proposals may edit only the plugin and its local
configuration/tests.

## Consequences

- Canonical RLinf and the base VLA stay clean and pinned.
- Algorithmic changes have small, reviewable diffs.
- Upstream changes require an explicit compatibility/equivalence update.
- The first code-study scope excludes critic, replay, rollout, simulator, and
  model-architecture rewrites.

## Alternatives rejected

- Patch canonical RLinf in place: weakens provenance and conflicts with D1.
- Configuration-only forever: does not satisfy the coding-agent policy-
  improvement goal discussed with Ludvig.
- Copy the complete RLT worker into each candidate: creates large diffs and
  exposes unrelated infrastructure to agent edits.
