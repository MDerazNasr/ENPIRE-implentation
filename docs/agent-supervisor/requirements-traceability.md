# Coding-Agent Supervisor Requirements Traceability

Status: requirements frozen; implementation coverage updated through Milestone
4. Future scope changes require an ADR and matrix update before implementation.

## Sources

- **D1** — [`../baseline_protocol.md`](../baseline_protocol.md),
  [`../execution_checklist.md`](../execution_checklist.md), and the pinned
  repository implementation.
- **RLT** — [official RLinf RLT + ManiSkill guide](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/rlt.html)
  and pinned RLinf commit
  `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- **ENPIRE** — [official ENPIRE project page](https://research.nvidia.com/labs/gear/enpire/)
  and the supplied ENPIRE paper.
- **Ludvig** — private meetings on 2026-07-01 and 2026-07-16 plus the Discord
  discussion from 2026-07-09 through 2026-07-30. Raw transcripts contain
  personal and operational details and are intentionally not committed.
- **Approved plan** — the stage-gated implementation and three-arm study plan
  reviewed by Mohamed on 2026-08-04.

## Requirement matrix

| ID | Requirement and rationale | Source | Planned owner | Verification/evidence | Stage |
| --- | --- | --- | --- | --- | --- |
| R-001 | Supervise the **outer RL improvement loop**: inspect completed evidence, propose a change, run, evaluate, and keep/revert. Do not place an LLM in the gradient or action loop. | Ludvig, ENPIRE, approved plan | Coordinator state machine | End-to-end fake and live campaign reaches a terminal decision | M1–M5 |
| R-002 | Start with the reproducible rule-based RLT baseline, then add coding-agent control. | Ludvig, D1 | D1 adapter and baseline gate | Agent execution refuses to start without a frozen D1 Stage-7 evidence commit | M1, integration gate |
| R-003 | Preserve the frozen base VLA as a black box outside agent context and edit scope. | Ludvig, D1, RLT | Scope validator | Adversarial patch against VLA paths is rejected | M3 |
| R-004 | Preserve simulator, reset, success-verification, and evaluation definitions. In simulation these provide ENPIRE's environment/reset and verification layer. | Ludvig, ENPIRE, D1 | Campaign contract and scope validator | Reset IDs, evaluator version, and success definition are hashed; edits are rejected | M1, M3 |
| R-005 | RLinf remains pinned and canonical upstream source remains unmodified. | D1, RLT | Experiment backend | Commit/layout check plus clean upstream tree recorded before every run | M5 |
| R-006 | Begin with allowlisted RLT configuration edits, then permit narrow training-code edits. | Approved plan, Ludvig | Proposal validator | Separate config-only and code-enabled capability tests | M3, M6 |
| R-007 | Code mode must genuinely change training behavior, not merely prompt or configuration text. | Ludvig, ENPIRE | Project-owned actor-objective overlay | Default-equivalence test and one live modified-objective trial | M4, M6 |
| R-008 | Restrict code edits to a project-owned RLT actor-objective plugin; the agent cannot edit orchestration, evaluation, budgets, infrastructure, or canonical RLinf. | Approved plan; inferred from pinned RLinf worker lacking a safe external objective hook | Objective overlay and path validator | Path allowlist and gradient/finite-loss tests | M3, M4, M6 |
| R-009 | Use short, clean agent sessions to prevent context drift and scope creep. | Ludvig, ENPIRE | Claude adapter | Non-persistent session, ten-minute timeout, context hash, no session resume | M2 |
| R-010 | Pass compact delta/context summaries between sessions instead of unbounded raw history. | Ludvig, ENPIRE | Context builder | Snapshot test proves only approved summaries/source excerpts are included | M2 |
| R-011 | Claude is the first implementation behind a provider-neutral proposal interface. | Ludvig, approved plan | Agent backend | Contract test with Claude fixture and alternative fake provider | M2 |
| R-012 | The LLM emits a structured hypothesis and patch/config proposal; it receives no direct shell, Git, SSH, W&B, or filesystem authority. | Ludvig, approved plan | Agent backend and proposal schema | Tool-free invocation configuration and malicious-output rejection tests | M2–M3 |
| R-013 | Every proposal is falsifiable and changes one bounded hypothesis at a time. | ENPIRE, D1, approved plan | Proposal schema and campaign policy | Schema requires expected effect and rollback condition; excessive diffs rejected | M1–M3 |
| R-014 | Use a branch/worktree per hypothesis and retain a known-good incumbent checkpoint. | Ludvig, ENPIRE | Git experiment manager | Isolation, promotion, abandonment, and rollback integration tests | M3 |
| R-015 | Failed explorations must not degrade the stable code; separately valid fixes may be preserved only through explicit review. | Ludvig | Git experiment manager | Failed branch leaves incumbent hash unchanged; no automatic merge | M3 |
| R-016 | Agent claims are non-authoritative; deterministic metrics decide outcomes. | Ludvig, ENPIRE, D1 | Immutable evaluator | Changing proposal prose cannot change the decision for the same evidence | M4 |
| R-017 | Reuse the D1 `KEEP`, `REVERT`, and `INCONCLUSIVE` rule and its three-seed evidence requirements for confirmation. | D1, approved plan | Evaluator adapter | Replay D1 evidence and compare decisions byte-for-byte where schemas permit | Integration gate |
| R-018 | Missing, incompatible, non-finite, or unmatched evidence produces `INCONCLUSIVE` or `FAILED`, never a forced success. | D1 | Evaluator | Failure-mode test matrix | M4–M6 |
| R-019 | Preserve an append-only/tamper-evident numerical record and link it to W&B. Negative and null results are retained. | Ludvig, D1, ENPIRE | Evidence store | Hash reconciliation, append-only event tests, report includes rejected trials | M1, M4 |
| R-020 | Record commands, commits, configs, metrics, resources, costs, artifacts, and decisions for every run. | D1, Ludvig | Evidence store | Required-field completeness test | M1 |
| R-021 | Require one human approval for a bounded campaign envelope; run autonomously only inside the approved paths, trials, time, GPU cost, and LLM cost. | Approved plan | Campaign approval and budget guard | Missing/expired envelope blocks execution; cap cancels future work | M1, M5 |
| R-022 | Dry-run is the default and paid execution requires an explicit acknowledgement in addition to campaign approval. | D1 | Experiment backend | CLI integration tests | M5 |
| R-023 | Use separate GPU workers for independent hypotheses rather than distributing one initial trial across GPUs. | Ludvig, ENPIRE, approved plan | Scheduler | Two-worker concurrency test and live demonstration | M4, M7 |
| R-024 | A local master coordinator compares worker results with the same evaluator and chooses the next verified incumbent. | Ludvig | Coordinator | Concurrent trials cannot self-promote or cross-contaminate artifacts | M4, M7 |
| R-025 | Worker execution is provider-neutral and uses exact commits over SSH. | Approved plan | Worker interface | Fake-worker contract followed by two real SSH workers | M4, M7 |
| R-026 | Recover from coordinator restart and worker loss without duplicate runs or decisions. | Approved plan; ENPIRE reliability requirement | Event state machine and worker protocol | Crash/replay and duplicate-completion tests | M1, M4, M7 |
| R-027 | Report policy, systems, and agent efficiency: success, losses, wall time, utilization, cost, tokens, invalid proposals, and interventions. | Ludvig, ENPIRE, D1 | Report generator | Report completeness test against fixture campaign | M4, M8–M9 |
| R-028 | Evaluate three preregistered arms: fixed rule, Claude config-only, and Claude code-enabled. Give each three discovery trials and confirm each best valid candidate across paired seeds. | Approved plan | Study protocol | Preregistration hash, equal-budget audit, complete run table | M8 |
| R-029 | Demonstrate a live CLI-driven iteration, two-worker dispatch, deterministic decision, static report, and recorded fallback. | Approved plan | CLI/report/demo package | Rehearsed 10–15 minute demo and replay of real evidence | M9 |
| R-030 | Document decisions, changes, outcomes, benchmarks, and limitations throughout, including an Obsidian handoff. | Mohamed, Ludvig | Documentation workflow | Milestone reports, ADRs, campaign reports, task note | Every milestone |
| R-031 | Do all useful no-baseline work first, but do not make real performance claims or agent-vs-rule comparisons until D1 is complete. | Mohamed, D1 | Milestone gates | Dependency gate in coordinator and milestone reports | M0–M4, gate |
| R-032 | Keep the first deliverable narrowly reusable around RLT; do not claim a general paper-implementation agent. | Ludvig | Architecture contract | Scope review and limitation section in final report | M0, M9 |

## Explicitly deferred requirements

| ID | Deferred capability | Reason and trigger to reconsider |
| --- | --- | --- |
| D-001 | Real-robot execution and automatic resets | Simulation evidence must first justify transfer and a separately approved safety contract is required. |
| D-002 | Visual/video diagnosis subagent | Valuable follow-on discussed with Ludvig, but not required to validate the core supervisor. |
| D-003 | Claude-versus-Codex/Kimi agent benchmarking | Would answer a different research question and multiply trial cost. |
| D-004 | Arbitrary repository-wide coding | Conflicts with the reduced-context and least-authority requirements. |
| D-005 | Automatic literature search and research-paper implementation | Long-term direction only; first establish a reliable RLT-specific harness. |
| D-006 | Distributed multi-GPU training for a single candidate | First milestone uses one independent hypothesis per worker. |
| D-007 | Automatic fine-tuning of the base VLA from residual interventions | Relevant to EXPO-FT/long-term transfer, but outside the first supervisor study. |

## Milestone 1 coverage

| Requirement | Implemented evidence |
| --- | --- |
| R-001, R-002 | Separate versioned campaign/trial lifecycles and an explicit D1 baseline commit in every campaign. |
| R-004, R-005 | Reset-set and pinned RLinf hashes are required campaign/evidence fields. |
| R-006, R-008 | Edit mode, safe editable paths, and typed allowlisted parameters are required by the campaign contract. Full patch enforcement remains M3. |
| R-014, R-015 | Parent/candidate commits and incumbent transitions are required evidence; Git worktree enforcement remains M3. |
| R-016–R-018 | Versioned decision/evidence records prevent non-keep promotion and require explicit non-finite metric errors. The D1 evaluator adapter remains gated. |
| R-019, R-020 | Hash-chained event ledger, artifact references, provenance, metric, cost, and decision records implemented. W&B linkage remains M4. |
| R-021, R-022 | Exact campaign-fingerprint approval, expiration, and decimal-safe budget preflight implemented. Paid-launch acknowledgement remains in D1/M5. |
| R-026 | Deterministic event replay, partial-record rejection, and external head anchoring implemented. Worker idempotency remains M4/M7. |
| R-030 | Contracts, ADR 0004, verification report, tests, and Obsidian handoff added. |

## Milestone 2 coverage

| Requirement | Implemented evidence |
| --- | --- |
| R-009 | Claude CLI calls are tool-free, non-persistent, capped at ten minutes, and bound to a recorded context hash. |
| R-010 | Deterministic 64-KiB context builder accepts only bounded baseline/delta/prior summaries and approved source excerpts; raw logs and credential-like text are rejected. |
| R-011 | Provider-neutral protocol, deterministic fake provider, and Claude-first adapter implemented and contract-tested without a real provider call. |
| R-012 | Canonical structured-output schema requires a config or diff proposal; Claude receives no shell, Git, SSH, W&B, or filesystem tools. M3 still owns independent patch enforcement. |
| R-013 | Proposal requires one hypothesis, evidence IDs, expected effect, falsification, rollback, bounded changed paths, tests, and estimated resources. |
| R-021 | Each call receives the remaining decimal-safe LLM session budget; over-reported cost is recorded and stops the slot. Campaign activation remains M5. |
| R-027 | Attempt audits retain provider/model, duration timestamps, costs, token counts when available, validity outcome, validation errors, and response/proposal hashes. Aggregate reporting remains M4/M8–M9. |
| R-030 | Proposal/context contract, fixtures, tests, verification report, requirement update, and Obsidian handoff added. |

## Milestone 3 coverage

| Requirement | Implemented evidence |
| --- | --- |
| R-003–R-005 | Actual diff paths must exactly equal campaign paths; noncanonical paths, symlinks, submodules, and any undeclared changes are rejected. Campaign boundaries keep the VLA, simulator/evaluator, and canonical RLinf outside scope. Live pinned-layout checks remain M5. |
| R-006 | Config JSON and actor-objective Python follow separate enforcement/materialization paths, both tested against valid and malicious fixtures. |
| R-008 | Initial code policy permits one campaign-allowlisted Python file and rejects obvious filesystem, shell, network/import, environment, dynamic-code, and dunder capabilities. The real project-owned overlay arrives in M4. |
| R-012–R-013 | Declared paths are independently parsed; renames, deletes, modes, binaries, multiple files, untrusted tests, and excess estimated budget fail before worktree creation. |
| R-014–R-015 | Exact-incumbent branch/worktree per proposal, stable-HEAD proof, retained failures, independent hypotheses, no auto-merge, and restart discovery implemented with real temporary Git repositories. |
| R-021 | Proposal resource estimates are rechecked against campaign caps before Git work begins. Campaign activation remains M5. |
| R-026 | Deterministic discovery prevents duplicate preparation and trial-ledger binding is idempotent. Worker-message idempotency remains M4/M7. |
| R-030 | Enforcement/Git contract, ADR 0005, adversarial tests, verification report, traceability, and Obsidian handoff added. |

## Milestone 4 coverage

| Requirement | Implemented evidence |
| --- | --- |
| R-001, R-024 | `OfflineCampaignCoordinator` composes an accepted proposal, isolated Git candidate, per-seed runs, strict evidence, the frozen evaluator, a terminal decision, and a per-arm incumbent update. |
| R-007–R-008 | Project-owned `actor_objective.py` is the only intended training-code overlay. Scalar, NumPy shape/dtype, and framework-independent dual-number gradient fixtures prove default algebraic equivalence. Live RLinf/autograd wiring remains M6. |
| R-016–R-018 | The evaluator accepts evidence rather than agent prose, uses the frozen D1 rule, and fails closed for missing seeds, missing metrics, failed runs, metric errors, and provenance mismatches. D1 evidence replay remains the integration gate. |
| R-019–R-020 | Candidate evidence is bound to immutable run-contract hashes and hash-chained ledgers. JSON/CSV/Markdown/HTML reports retain numerical results, failures, costs, tokens, commits, and decision hashes. W&B reconciliation remains M5. |
| R-023, R-025 | Provider-neutral worker protocol and deterministic fake worker are implemented. True concurrent hypotheses and exact-commit SSH workers remain M7. |
| R-026 | Duplicate fake-worker messages and incumbent decision application are idempotent; worker loss cannot promote. Full coordinator crash/lease recovery remains M7. |
| R-027 | Offline report includes attempt/decision counts, success evidence, failures, elapsed time, GPU/LLM costs, tokens, and an explicit unavailable utilization value. Live utilization and human-intervention capture remain M8–M9. |
| R-030–R-031 | One-command demo, contracts, test evidence, limitations, and milestone handoff are documented; every output is labeled synthetic and no performance claim is made before D1. |

## Change control

A future implementation may refine an interface, but it may not weaken an
immutable boundary, evidence requirement, or approval gate without:

1. adding or updating an ADR;
2. updating this matrix;
3. identifying affected tests and scientific comparisons; and
4. obtaining Mohamed's approval before execution under the new contract.
