# D2 Coding-Agent Supervisor Contract

Status: Milestone 0 contract. No coding-agent or paid experiment has been
implemented or launched from this branch.

This directory freezes the requirements and architecture for the
ENPIRE-inspired coding-agent supervisor that will wrap the reproducible
RLinf/RLT improvement loop. The supervisor is an **outer-loop research
orchestrator**: it proposes bounded changes between complete RL training runs.
It does not control gradients, robot actions, simulator resets, or evaluation
labels inside a run.

## Documents

- [`requirements-traceability.md`](requirements-traceability.md) maps each
  source requirement to a future component, verification, and demo evidence.
- [`architecture-contract.md`](architecture-contract.md) defines system
  boundaries, data flow, lifecycle, and baseline dependencies.
- [`artifact-policy.md`](artifact-policy.md) defines the durable evidence and
  documentation contract.
- [`contracts.md`](contracts.md) documents the implemented version-1 wire
  contracts and lifecycle split.
- [`adr/`](adr/) records decisions that future implementation must not silently
  reverse.

## Source hierarchy

When sources differ, use this order:

1. The approved D1 scientific protocol and its eventual known-good evidence
   commit.
2. The pinned RLinf implementation and official RLT guide.
3. The ENPIRE paper/project design.
4. The implementation requirements agreed with Ludvig in the July 2026
   meetings and Discord discussion.
5. Convenience behavior in the existing Phase-1 smoke harness.

The Phase-1 smoke result is orchestration evidence only. It is not a scientific
baseline and must not be used to claim RLT improvement.

## Milestone labels

- M0: requirements, isolation, and research contract (this milestone).
- M1: schemas, state machine, approval, budgets, and evidence ledger.
- M2: Claude-first structured proposal backend and context builder.
- M3: proposal validation and Git worktree lifecycle.
- M4: fake workers, evaluator/report integration, and objective overlay.
- Integration gate: replay against the completed D1 Stage-7 evidence pack.
- M5: live configuration-only loop.
- M6: live code-enabled loop.
- M7: two-worker multi-GPU orchestration.
- M8: preregistered three-arm study.
- M9: Ludvig demo and final research deliverable.

## Milestone gate

Milestone 0 is complete only when:

- the active D1 worktree remains untouched;
- every captured requirement has an owner and verification method;
- immutable and editable boundaries are explicit;
- real agent trials are blocked on the D1 Stage-7 evidence gate; and
- another engineer can understand the planned system without the private
  meeting transcripts.
