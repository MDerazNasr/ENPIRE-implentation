# D2 Coding-Agent Supervisor Contract

Status: Milestone 9 offline-first delivery, live F1 fixed-worker acceptance,
and the matched H100 PCIe F2 execution/resume rehearsal are complete. The
paired-seed scientific baseline and live agent study remain unexecuted and
unauthorized. No RLT improvement, agent-superiority, evaluation, or promotion
claim follows from F2.

Current integration note (2026-09-11): the B1 builder still refuses strict D1
publication because the canonical matched paired-seed evidence pack is absent.
F2 removed the runtime/resume engineering blocker by completing four fixed runs
and all ten resume checks on one H100 PCIe runtime. G0 experiment design is now
documented; exact seeds, evaluator/reset hashes, conditions, run matrix, and
budget must be preregistered before paid scientific execution. Historical
milestone reports retain their dated observations rather than rewriting past
evidence.

This directory freezes the requirements and architecture for the
ENPIRE-inspired coding-agent supervisor that will wrap the reproducible
RLinf/RLT improvement loop. The supervisor is an **outer-loop research
orchestrator**: it proposes bounded changes between complete RL training runs.
It does not control gradients, robot actions, simulator resets, or evaluation
labels inside a run.

## Documents

- [`harness-product-and-operations-guide.md`](harness-product-and-operations-guide.md)
  is the canonical product entry point: architecture, authority, components,
  local demos, real-campaign workflow, workers, evidence, current status,
  limitations, troubleshooting, and documentation protocol.

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
- [`c0-provider-contract.md`](c0-provider-contract.md) freezes the locally
  verified Claude CLI/model, least-authority environment, invocation, budget,
  and size/attempt limits for live-provider acceptance.
- [`c1-provider-acceptance.md`](c1-provider-acceptance.md) records the curated
  D1 provider input, mutation audit, paid-call gate, and fail-safe live result.
- [`d0-dry-run-acceptance.md`](d0-dry-run-acceptance.md) records the isolated
  fixture proposal, harness checks, worker-owned seed plan, exact command
  hashes, and proof that no process or GPU could launch.
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
- [`g0-scientific-experiment-test-program.md`](g0-scientific-experiment-test-program.md)
  specifies the evaluator, baseline-horizon, BC-theory, evolutionary-search,
  agent-value, scheduling, and task-quality experiments that follow F2. It is
  a draft protocol and grants no GPU execution authority.
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
- [`d1-evidence-schema-mapping.md`](d1-evidence-schema-mapping.md) inventories
  current D1 source evidence and maps all seven required artifact roles.
- [`d1-pack-builder.md`](d1-pack-builder.md) documents the deterministic
  readiness report, reviewed source format, and fail-closed publisher.
- [`d1-pack-gate-compatibility.md`](d1-pack-gate-compatibility.md) records the
  B2 builder-to-gate fixture, exact evaluator equivalence, and current blocked
  live diagnostic.
- [`d1-d2-reconciliation.md`](d1-d2-reconciliation.md) records the exact source
  heads, preservation policy, merge result, status corrections, and passed A3
  verification.
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
- Integration gate: implementation complete; live replay remains blocked until
  the reconciled D1 evidence is packaged in the strict schema with the approved
  matched seed set.
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
