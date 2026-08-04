# Milestone 5 Verification Report

Date: 2026-08-04

Branch: `feature/d2-agent-supervisor`

Outcome: M5 implementation complete; live D1 acceptance remains blocked.

## Implemented

- explicit dry-run, no-GPU fixture, and paid execution modes;
- exact campaign/approval/D1-gate binding for paid authorization;
- clean exact-commit candidate validation and worker-owned seed configs;
- synchronization from four scientific RLT values to their actual Hydra keys;
- immutable command/config/seed/reset/evaluator/wall-time/cost run contracts;
- process-group timeout termination and fail-closed missing-artifact behavior;
- strict D1 manifest/log normalization and W&B reconciliation;
- real `ExperimentWorker` adapter and coordinator run-contract factory;
- backwards-compatible M4 fake-worker path;
- end-to-end subprocess fixture covering proposal, Git candidate, three seeds,
  evidence, deterministic decision, incumbent update, and stable-branch proof.

## Verification evidence

| Check | Result |
| --- | --- |
| Focused M5/coordinator/gate/worker suite | 29 passed, 5 subtests passed |
| Complete repository suite after M5 | 152 passed, 74 subtests passed |
| No-GPU subprocess adapter | complete |
| Three-seed coordinator fixture | `decided` / `keep` |
| Stable branch moved | no |
| Paid/GPU/RLinf/provider calls | none |
| Live D1 integration gate | blocked |

The read-only live audit on 2026-08-04 reported four blockers: the D1 worktree
is dirty, Stage 7 is incomplete, the evidence pack is missing, and the recorded
baseline is degenerate. M5 did not modify that worktree.

## Failure coverage

- dry-run proves no subprocess is invoked;
- paid mode rejects missing approval, acknowledgement, or ready replay gate;
- dirty or wrong-commit candidate worktrees are rejected;
- subprocess timeout returns no evidence;
- commit tampering and cost overrun invalidate evidence;
- fixture execution requires an explicit synthetic flag;
- coordinator factory rejects dry-run execution and campaign mismatch;
- worker loss or invalid evidence cannot reach evaluation/promotion.

## Honest limitations

- The successful subprocess results are synthetic fixtures, not RLT results.
- No W&B API was called; the fixture only tests URL reconciliation.
- No paid agent, RLinf process, GPU, SSH host, or cloud worker was launched.
- Live acceptance requires the separate D1 Stage-7 evidence gate to become
  ready. The supervisor implementation does not make that scientific evidence
  exist.
- The current worker is synchronous and local. Multi-worker leases, restart
  recovery, utilization capture, and active remote cancellation remain M7/M8.
- Actor-objective code editing remains prohibited until M6.

## Demonstrable result without D1

The M4 report demo remains the presentation-safe product walkthrough. M5 adds
a stronger engineering demonstration: the same coordinator path can execute
real subprocesses and consume D1-shaped artifacts, but labels them synthetic.
This is enough to present architecture, safety, provenance, failure behavior,
and readiness for live integration. It is not enough to claim the agent has
improved RLT.
