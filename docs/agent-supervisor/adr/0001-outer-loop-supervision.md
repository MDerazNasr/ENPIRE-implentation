# ADR 0001: Place the Coding Agent Outside the RL Run

- Status: accepted
- Date: 2026-08-04

## Context

The project describes the coding agent as supervising RL. That phrase could be
misread as placing an LLM inside optimizer or environment steps. ENPIRE and the
discussion with Ludvig instead describe a policy-improvement loop that edits
training code/configuration between bounded rollouts and compares branches.

## Decision

The agent supervises only the outer experiment loop. RLinf owns all computation
inside a run. The agent receives completed, normalized evidence and proposes one
next change. A deterministic evaluator decides promotion.

## Consequences

- Training behavior is reproducible without replaying LLM interaction.
- Agent latency cannot stall the fast control loop.
- The agent cannot directly manipulate success labels or gradient updates.
- Online, step-level adaptive control would require a separate future design.

## Alternatives rejected

- Persistent agent monitoring every optimizer step: unnecessary context,
  latency, cost, and a much larger safety surface.
- Agent-authored success decision: conflicts with the requirement that metrics,
  not agreeable agent claims, determine outcomes.
