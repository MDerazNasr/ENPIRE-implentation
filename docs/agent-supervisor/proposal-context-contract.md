# Proposal and Context Contract Version 1

Status: implemented in Milestone 2. The strict Python validators in
[`../../supervisor/proposals.py`](../../supervisor/proposals.py),
[`../../supervisor/context.py`](../../supervisor/context.py), and
[`../../supervisor/attempts.py`](../../supervisor/attempts.py) are normative.

## Authority boundary

The provider proposes one experiment. It does not apply a patch, launch a
trial, read the repository, use a shell, inspect credentials, decide whether a
trial succeeded, or promote an incumbent. M3 will independently validate and
apply an accepted proposal in an isolated Git worktree. Later milestones will
run and evaluate it.

## Curated context

`build_context` produces deterministic UTF-8 JSON wrapped by a fixed system
instruction. It contains only:

- the strict campaign specification and its fingerprint;
- the current incumbent commit;
- explicit immutable boundaries and metric definitions;
- one bounded baseline summary;
- at most 16 compact prior-trial summaries;
- at most eight approved source, protocol, or evidence-summary excerpts; and
- an optional bounded delta summary.

Raw logs are not an allowed excerpt type. Individual excerpts are limited to
16 KiB and the rendered context to 64 KiB. Credential-like content is rejected
before rendering. Excerpt content hashes and the full context hash are returned
for audit records. Excerpts and prior summaries are labeled as untrusted
evidence, not instructions.

## Proposal

Every proposal binds itself to the campaign, arm, current incumbent commit,
edit mode, referenced evidence, paths, requested tests, and estimated resource
use. It must state:

- one bounded hypothesis;
- an expected effect;
- a condition that would falsify the hypothesis; and
- a rollback condition.

Configuration proposals contain only non-empty parameter overrides. The
campaign validator enforces parameter names, scalar types, enum choices, and
numeric bounds. Code proposals contain only a unified diff, limited to 64 KiB.
Both modes declare changed paths, which must be a subset of the campaign's
editable paths. M3 adds hunk-level and semantic patch validation; M2 acceptance
does not authorize execution.

The JSON Schema passed to Claude is canonicalized and fingerprinted. Python
validation remains authoritative because provider-side schema enforcement
cannot enforce campaign-specific scope or numerical parameter bounds.

Valid non-executable examples are
[`../../examples/supervisor/proposal-config.json`](../../examples/supervisor/proposal-config.json)
and
[`../../examples/supervisor/proposal-code.json`](../../examples/supervisor/proposal-code.json).

## Provider session

`ProposalProvider` is provider-neutral. `FakeProposalProvider` supports offline
tests and demonstrations. `ClaudeCliProvider` uses a supplied absolute CLI
path, a supplied working directory, a reduced environment allowlist, stdin,
`shell=False`, JSON structured output, no tools, `dontAsk` permission mode,
no session persistence, a dollar cap, and a timeout of at most ten minutes.

The adapter does not place credentials in context, command arguments, output,
or audit errors. Non-zero exits retain only a stderr hash. Provider output is
limited to 1 MiB and must be strict JSON; NaN and infinity fail closed.

## Initial and repair attempts

A proposal slot receives at most two short calls:

1. one initial structured proposal; then
2. only if local contract validation fails, one repair call containing bounded
   validation feedback and the identical original context.

Timeouts, provider errors, identity mismatches, and budget overruns do not
trigger a repair. The second call receives only the unspent session budget.
Every attempt records provider/model identity, context and schema hashes,
timestamps, timeout, dollar cap and reported cost, token counts when available,
response/proposal hashes, status, and validation errors. The audit schema
enforces consistency between each status and its required hashes/errors.

## Explicit non-capabilities

Milestone 2 does not:

- call Claude or any paid API in tests or examples;
- apply configuration or code changes;
- create hypothesis branches/worktrees;
- launch RL, GPU, simulator, SSH, or W&B work;
- use D1 evidence; or
- make performance or scientific claims.
