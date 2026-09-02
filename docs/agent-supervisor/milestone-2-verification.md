# Milestone 2 Verification Report

- Date: 2026-08-04
- Work branch: `feature/d2-agent-supervisor`
- Starting commit: `1120ec9`
- Status: complete, awaiting Mohamed's review
- Paid GPU/LLM/API calls: none

## Outcome

Milestone 2 implements the bounded proposal-generation side of the outer-loop
supervisor. A deterministic context builder supplies compact evidence to a
provider-neutral interface. Claude is the first real adapter, while a fake
provider makes the entire flow testable and demonstrable offline. A proposal
slot permits one initial call and, only for locally invalid structured output,
one repair call.

An accepted proposal is still inert data. This milestone does not apply it,
create a branch, launch training, evaluate performance, or promote an
incumbent.

## Implemented behavior

### Curated, hashed context

- Deterministic canonical context tied to campaign fingerprint and incumbent.
- Explicit immutable boundaries, metric definitions, baseline summary, prior
  trial summaries, approved excerpts, and optional delta summary.
- Limits of 16 prior trials, eight excerpts, 16 KiB per excerpt, and 64 KiB for
  the final rendered context.
- Raw-log exclusion, unique evidence identifiers, finite metrics, and
  credential-pattern rejection without echoing matched material.
- Full context hash and individual excerpt hashes for later evidence records.

### Structured proposal

- Strict versioned config-only and actor-objective-code variants.
- Campaign/arm/incumbent/edit-mode/evidence/path/test/resource binding.
- Required hypothesis, expected effect, falsification, and rollback statements.
- Campaign-specific configuration parameter allowlist, types, choices, and
  bounds.
- Mutually exclusive config overrides or a 64-KiB unified diff.
- Canonical structured-output JSON Schema and stable schema fingerprint.

### Provider and attempts

- Provider-neutral protocol and deterministic queued fake provider.
- Claude CLI adapter using stdin, `shell=False`, reduced environment, no tools,
  `dontAsk`, structured JSON, no session persistence, explicit model/effort,
  call budget, and a maximum ten-minute timeout.
- Strict JSON envelope parsing, one-MiB response limit, non-finite rejection,
  hashed stderr on failure, and provider/model identity verification.
- At most one validation repair using the unchanged original context, bounded
  feedback, and only the remaining decimal-safe dollar budget.
- Audited cost, timestamps, tokens when available, response/proposal hashes,
  status, and validation errors for every attempt.

ADR 0002 already froze these authority and session choices, so no additional
architecture decision record was needed.

## Validation results

| Check | Result |
| --- | --- |
| New Milestone 2 tests | 32/32 passed |
| Complete repository suite | 86/86 passed |
| Python compilation | Passed |
| `git diff --check` | Passed |
| Relative Markdown links | 33 files checked; all resolve |
| Existing D1 files modified by M2 | 0 |
| Paid GPU runs | 0 |
| Claude/external coding-agent calls | 0 |

Covered failure scenarios include unknown/missing proposal fields, conflicting
config/code payloads, stale incumbent or campaign identity, wrong edit mode,
out-of-scope paths, unallowlisted/wrong-type/out-of-bounds parameters,
oversized or malformed diffs, duplicate evidence, non-finite metrics, raw logs,
credential-like context, context/excerpt overflows, malformed/NaN/oversized
Claude envelopes, non-zero provider exits, timeouts, excessive repair feedback,
provider identity mismatch, two invalid attempts, and reported-cost overrun.

The CLI tests use an injected process transport and never execute Claude. The
adapter's planned arguments were also checked against the locally installed
Claude CLI help, without submitting a prompt.

## Honest limitations

- M2 validates proposal structure and campaign-level scope, but not diff hunks,
  symlinks, imports, executable commands, or semantic training-code behavior.
  M3 owns those controls.
- The Claude response-envelope parser matches the locally documented CLI
  interface but has not been confirmed with a paid live response.
- Credential rejection is defense in depth, not a general secret-classification
  system. The source allowlist must remain the primary context boundary.
- The provider process receives only an allowlisted environment, which can
  include the authentication variables required by the selected Claude
  backend. Their values are never included in prompts or audit records.
- Proposal text may still be scientifically poor. Only later deterministic
  execution and evaluation can establish whether it improves RLT.
- There is no Git experiment manager, worker, D1 adapter, evaluator, W&B link,
  CLI campaign runner, or real performance evidence yet.

## Background isolation

All changes were made in `/private/tmp/enpire-d2-agent-supervisor`. The original
worktree remained on `experiment/d1-rlt-baseline` with its independent
background configuration, test, note, script, and temporary-file changes
untouched and unstaged by this milestone.

## Remaining work after review

- Numbered milestones remaining: 7 (M3–M9).
- Separate D1 integration gate remains between M4 and M5.
- Remaining engineering estimate: 75–112 hours, excluding D1 completion, GPU
  queues, and RL training wall time.

M3 will independently validate proposals and implement a per-hypothesis Git
branch/worktree lifecycle with known-good incumbent preservation. It must not
begin until Mohamed explicitly approves this milestone.
