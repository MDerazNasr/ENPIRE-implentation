# D2 Coding-Agent Supervisor Contract

Status: Milestone 9 final offline-first supervisor delivery complete;
exact live RLinf/SSH/GPU acceptance remains a compatibility handoff with the
separately owned D1 workstream. No paid agent, RLinf training, GPU, SSH
connection, W&B API, or scientific experiment has been launched from this
branch.

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
- [`proposal-context-contract.md`](proposal-context-contract.md) documents the
  Milestone 2 context, structured proposal, provider, and repair contracts.
- [`enforcement-git-contract.md`](enforcement-git-contract.md) documents the
  Milestone 3 independent policy, materialization, worktree, and ledger gates.
- [`offline-loop-contract.md`](offline-loop-contract.md) documents the M4 fake
  worker, deterministic evaluator, per-arm pointers, reports, and demo.
- [`m5-live-backend-contract.md`](m5-live-backend-contract.md) documents the
  guarded D1 subprocess adapter, authorization modes, evidence normalization,
  and coordinator seam.
- [`m6-code-objective-contract.md`](m6-code-objective-contract.md) documents
  the versioned objective ABI, mandatory behavioral proof, provenance, and live
  compatibility boundary.
- [`m7-distributed-orchestration-contract.md`](m7-distributed-orchestration-contract.md)
  documents worker capabilities, leases, restart/loss recovery, conservative
  budgets, cancellation, and the fixed SSH RPC boundary.
- [`m8-three-arm-study-contract.md`](m8-three-arm-study-contract.md) documents
  preregistration, equal allocation, arm isolation, selection, paired
  confirmation, reporting, and the live claim boundary.
- [`m9-delivery-contract.md`](m9-delivery-contract.md) documents the unified
  demo, optional read-only D1 replay, semantic fingerprint, presentation, and
  artifact verification boundary.
- [`real-policy-demo.md`](real-policy-demo.md) documents the companion real CPU
  learning task, one-command runner, evidence, and non-RLT boundary.
- [`real-policy-demo-presenter-guide.md`](real-policy-demo-presenter-guide.md)
  provides the nontechnical talk track, commands, questions, and fallback.
- [`real-policy-demo-verification.md`](real-policy-demo-verification.md)
  records its learning, isolation, evidence, integrity, and visual checks.
- [`ludvig-demo-runbook.md`](ludvig-demo-runbook.md) provides the rehearsed
  10–15 minute talk track, commands, expected questions, and fallback.
- [`final-research-handoff.md`](final-research-handoff.md) summarizes the final
  system, demonstrated evidence, D1 seam, limitations, and recommended study.
- [`d1-integration-gate.md`](d1-integration-gate.md) defines the strict Stage-7
  pack, Git binding, evidence normalization, and replay equivalence gate.
- [`milestone-2-verification.md`](milestone-2-verification.md) records the M2
  implementation, tests, boundaries, and remaining limitations.
- [`milestone-3-verification.md`](milestone-3-verification.md) records the M3
  enforcement, real-Git isolation tests, limitations, and M4 handoff.
- [`milestone-4-verification.md`](milestone-4-verification.md) records the M4
  offline end-to-end verification and D1 integration gate.
- [`milestone-5-verification.md`](milestone-5-verification.md) records the M5
  implementation, subprocess fixture, live blocker, and honest demo boundary.
- [`milestone-6-verification.md`](milestone-6-verification.md) records the M6
  code-enabled tests, subprocess demonstration, and remaining live attachment.
- [`milestone-7-verification.md`](milestone-7-verification.md) records the M7
  two-worker, restart, retry, stale-result, SSH-client, and evaluator evidence.
- [`milestone-8-verification.md`](milestone-8-verification.md) records the M8
  three-arm protocol, synthetic study, adverse-outcome retention, report
  reconciliation, and D1 handoff.
- [`milestone-9-verification.md`](milestone-9-verification.md) records the final
  unified demo, fallback, determinism, manifest, and acceptance evidence.
- [`d1-integration-gate-verification.md`](d1-integration-gate-verification.md)
  records the implemented gate and the current honest `blocked` result.
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
- M2: Claude-first structured proposal backend and context builder (complete).
- M3: proposal validation and Git worktree lifecycle (complete).
- M4: fake workers, evaluator/report integration, and objective overlay
  (complete).
- Integration gate: implementation complete; live replay blocked because D1
  Stage 7 and its non-degenerate evidence pack do not yet exist.
- M5: configuration-only D1 adapter complete; live acceptance blocked.
- M6: synthetic code-enabled loop complete; live attachment is a D1 handoff.
- M7: durable two-worker synthetic orchestration complete; live GPU/SSH gated.
- M8: preregistered three-arm study (synthetic implementation complete; live
  study D1-gated).
- M9: Ludvig demo and final research deliverable (offline-first implementation
  complete; real/scientific execution remains D1-gated).
- Post-M9 companion: real CPU toy-policy demonstration complete; this improves
  presentation clarity but creates no RLinf/RLT evidence.

## Milestone gate

Milestone 0 is complete only when:

- the active D1 worktree remains untouched;
- every captured requirement has an owner and verification method;
- immutable and editable boundaries are explicit;
- real agent trials are blocked on the D1 Stage-7 evidence gate; and
- another engineer can understand the planned system without the private
  meeting transcripts.
