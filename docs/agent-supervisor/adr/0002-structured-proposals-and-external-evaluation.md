# ADR 0002: Tool-Free Structured Proposals and External Evaluation

- Status: accepted
- Date: 2026-08-04

## Context

Long autonomous coding sessions can drift, expand scope, or claim progress that
is not supported by simulator metrics. Giving Claude an unrestricted coding
shell would also mix proposal generation with enforcement and execution.

## Decision

Use short, non-persistent Claude sessions behind a provider-neutral interface.
Claude receives curated, hashed context and returns schema-constrained JSON
containing a hypothesis and config/diff. It receives no direct tools. The
supervisor validates and applies the proposal in an isolated worktree. A
versioned deterministic evaluator makes the terminal decision.

## Consequences

- Proposals can be replayed and tested without calling Claude.
- Scope, budget, and safety enforcement remain ordinary code.
- Context handoff is deliberate and compact.
- Claude cannot investigate freely during a proposal; missing information must
  be supplied through a later, explicitly bounded request.

## Alternatives rejected

- Unrestricted Claude Code in the repository: violates least authority and
  makes branch/evidence boundaries harder to guarantee.
- One persistent conversation for an entire campaign: increases drift and
  makes proposal provenance dependent on hidden conversation state.
