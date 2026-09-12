# Supervisor Contract Version 1

Status: implemented in Milestone 1. The strict Python loaders in
[`../../supervisor/contracts.py`](../../supervisor/contracts.py) are the
normative validators; this document describes their public wire behavior.
Later milestones implement activation, execution, scheduling, evaluation, and
study orchestration around these version-1 records; see
[`harness-product-and-operations-guide.md`](harness-product-and-operations-guide.md)
for current status.

## Canonical encoding

- Records use UTF-8 JSON with sorted keys and compact separators when hashed.
- `schema_version` is currently `1`; unknown versions and unknown fields fail
  closed.
- NaN and infinity are forbidden in JSON and metric records.
- Dollar values cross the wire as canonical decimal strings.
- Commits are full lowercase 40-character Git hashes.
- Content identifiers are lowercase SHA-256 hashes.
- Timestamps are timezone-aware UTC ISO-8601 values.
- Editable paths are POSIX-relative and cannot contain `..` or backslashes.

## Campaign specification

The campaign binds the research question to:

- project and RLinf commits;
- `config_only` or `actor_objective_code` mode;
- editable paths and typed parameter rules;
- seeds and reset-set hash;
- evaluator version and train/evaluation budgets;
- maximum concurrency and artifact namespace;
- trial, wall-time, GPU-cost, and LLM-cost caps.

[`../../examples/supervisor/campaign.json`](../../examples/supervisor/campaign.json)
is a valid fixture, not an approved or executable campaign.

## Approval envelope

An approval contains the exact campaign fingerprint, approver, active UTC time
window, edit mode, concurrency, and cost/trial/time caps. Approval validation
fails when:

- the campaign ID or fingerprint changed;
- the time is before approval or at/after expiration;
- edit mode differs; or
- any approved limit is broader than the campaign specification.

Execution authority was not implemented in M1. The later execution code calls
this validator immediately before activating a campaign; this historical M1
statement does not authorize execution by itself.

## Lifecycle records

Campaign lifecycle:

```text
draft -> validated -> approved -> active -> completed
```

The permitted cancellation/failure edges are encoded in
[`../../supervisor/state.py`](../../supervisor/state.py). Completed, failed,
and cancelled campaigns are terminal.

Trial lifecycle:

```text
proposing -> proposal_validated -> queued -> running -> evaluated
                                                    -> kept | reverted
                                                     | inconclusive | failed
```

Failed/cancelled edges exist at the appropriate pre-evaluation stages. A trial
decision is terminal for that trial only.

## Event ledger

Each JSONL event contains the entity identity, strict sequence, previous-event
hash, declared state transition, actor, UTC timestamp, reason, metadata, and
event hash. Appends use an exclusive file lock, one complete JSONL write,
flush, and `fsync`.

Replay detects malformed/partial records, content edits, internal deletion,
reordering, duplication, identity mismatch, broken hashes, and illegal state
transitions. Detecting deletion of a complete ledger tail requires comparing
the reconstructed sequence/head hash with a separately retained trusted anchor;
the API supports both expected values. Hosted artifact linkage will provide
that external anchor in a later milestone.

## Budget records

Preflight accounting rejects a new trial when its estimated usage would exceed
any approved trial, wall-time, GPU-cost, or LLM-cost limit. Completed actual
usage is always recorded, even if a provider overrun crosses a cap; the
resulting exceeded state blocks further work. Duplicate trial usage is rejected.

M1 is single-coordinator accounting. Concurrent reservation/lease semantics
belong to the worker scheduler milestone.

## Evidence and decisions

Trial evidence requires commits, hashes, seed/reset/evaluator identity,
timestamps, exit status, finite metrics, explicit non-finite metric errors,
costs, and hashed artifact references. A completed trial requires exit code
zero; a failed trial requires a non-zero exit code.

Decision records bind one or more trial-evidence hashes to the evaluator,
reason, timestamp, and incumbent transition. Only `KEEP` can change the
incumbent, and `KEEP` must select a new incumbent.

## Milestone 2 extension

The version-1 proposal, curated-context, provider-attempt, and repair-session
contracts are documented separately in
[`proposal-context-contract.md`](proposal-context-contract.md). Acceptance by
that layer means only that a proposal is structurally compatible with its
campaign; it does not authorize patch application or experiment execution.

## Milestone 3 extension

Independent proposal enforcement, deterministic configuration materialization,
candidate preparation records, and hypothesis Git lifecycle are documented in
[`enforcement-git-contract.md`](enforcement-git-contract.md). A `ready`
preparation authorizes later worker queuing only; it is not a performance
decision or permission to merge.
