# Milestone 1 Verification Report

- Date: 2026-08-04
- Work branch: `feature/d2-agent-supervisor`
- Starting commit: `296c67f`
- Status: complete, awaiting Mohamed's review
- Paid GPU/LLM/API calls: none

## Outcome

Milestone 1 implements the dependency-free, version-1 foundation for later
Claude, Git, worker, evaluator, and reporting components. It cannot launch an
experiment. All authority is represented as strict data and deterministic
state rather than implicit process behavior.

## Implemented contracts

### Campaign and approval

- Exact project/RLinf commits, research question, edit mode, editable paths,
  typed parameter bounds, seeds, reset hash, evaluator, run budgets,
  concurrency, artifact namespace, and cost/time/trial caps.
- Strict schema version and unknown-field rejection.
- Canonical campaign fingerprint independent of input dictionary order.
- Approval bound to the exact fingerprint, active UTC window, edit mode,
  concurrency, and limits no broader than the campaign.
- Canonical decimal-string costs to avoid binary floating-point cap errors.

### Evidence and decision

- Trial identity, arm, parent/candidate/RLinf commits, config/command/reset
  hashes, seed, evaluator, timestamps, exit state, costs, finite metrics,
  explicit metric errors, and hashed artifact references.
- Completed/failed status consistency with process exit code.
- Decision records bind evidence hashes to evaluator/version, reason,
  timestamp, and incumbent transition.
- Non-keep decisions cannot change the incumbent; keep decisions must promote
  a new incumbent.

### Lifecycle and ledger

- Separate campaign and trial state machines, recorded in ADR 0004.
- Locked, flushed, and `fsync`-backed JSONL appends.
- Strict sequence and previous-event hash chain.
- Replay reconstructs the same state after coordinator restart.
- Optional trusted sequence/head anchors detect deletion of an otherwise valid
  complete ledger tail.

### Budget accounting

- Preflight rejection for projected trial, wall-time, GPU-cost, or LLM-cost
  overflow.
- Actual usage is retained even when it overruns a cap; the exceeded state
  blocks subsequent work.
- Duplicate trial accounting is rejected.

## Validation results

| Check | Result |
| --- | --- |
| New Milestone 1 tests | 25/25 passed |
| Complete repository suite | 54/54 passed |
| Python compilation | Passed |
| Relative Markdown links | All resolve |
| Existing D1 files modified | 0 |
| Paid GPU runs | 0 |
| Claude/external coding-agent calls | 0 |

The existing D1 acknowledgement test prints its expected argparse error while
verifying that paid execution without acknowledgement is rejected; it passes.

Covered failure scenarios include unknown/missing fields, unsafe paths,
duplicate seeds, bad parameter bounds, non-finite/negative budgets, non-UTC
timestamps, changed/expired approval, non-finite metrics, inconsistent exit
status, invalid promotion, illegal/skipped state transitions, content edits,
reordering, internal and anchored-tail deletion, duplicated ledger entries,
partial JSONL writes, malformed event contracts, duplicate cost records, and
every budget cap. Non-canonical NaN metadata is rejected before append.

## Honest limitations

- Approval identity is an auditable record, not a cryptographic human
  signature. The future CLI will create it only after explicit user action.
- A hash chain alone cannot detect deletion of a complete tail unless its prior
  head/sequence is anchored elsewhere. The API supports this; W&B/artifact
  linkage will retain anchors later.
- Budget tracking is single-coordinator and completed-usage based. Concurrent
  reservations and worker leases belong to the scheduler milestones.
- Editable-path validation currently guarantees safe relative syntax and a
  campaign allowlist. Patch/hunk/import/command enforcement belongs to M3.
- Evidence schemas exist, but there is no D1 adapter, W&B connection, Claude,
  Git experiment manager, SSH worker, or paid execution yet.
- The example campaign is contract-valid fixture data and carries no approval.

## Background isolation

All work was performed in `/private/tmp/enpire-d2-agent-supervisor`. The active
D1 worktree remained on `experiment/d1-rlt-baseline`; none of its tracked or
untracked recovery/probe files were staged, edited, or committed by this
milestone.

## Remaining work after review

- Numbered milestones remaining: 8 (M2–M9).
- Separate D1 integration gate remains between M4 and M5.
- Remaining engineering estimate: 85–127 hours, excluding D1 completion, GPU
  queues, and RL training wall time.

M2 will implement the Claude-first, tool-free structured proposal provider and
the curated, hashed context builder. It must not begin until Mohamed explicitly
approves this milestone.
