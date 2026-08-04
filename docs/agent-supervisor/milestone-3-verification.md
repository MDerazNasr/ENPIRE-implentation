# Milestone 3 Verification Report

- Date: 2026-08-04
- Work branch: `feature/d2-agent-supervisor`
- Starting commit: `cb56f49`
- Status: complete, awaiting Mohamed's review
- Paid GPU/LLM/API calls: none

## Outcome

Milestone 3 converts an M2 proposal from untrusted structured data into either
a rejected audit record, a retained failed hypothesis, or an isolated candidate
commit ready to queue. It implements independent diff/config enforcement,
deterministic configuration materialization, real Git branch/worktree
isolation, post-check revalidation, restart discovery, and M1 trial-ledger
binding.

It never merges, promotes, evaluates, or executes RL.

## Implemented behavior

### Independent enforcement

- Revalidates campaign, exact incumbent, edit mode, campaign paths, parameter
  rules, trusted test IDs, and estimated resource caps.
- Limits the initial policy to one file per hypothesis.
- Parses diff paths independently of Claude's declaration.
- Rejects noncanonical paths, mismatched paths, renames, copies, new/deleted
  files, mode changes, binaries, submodules, duplicate sections, and malformed
  headers/hunks.
- Limits candidate source to 128 KiB of UTF-8 parseable Python.
- Rejects imports outside the small actor-objective allowlist and obvious
  filesystem, process, environment, dynamic-code, and dunder escape features.

### Configuration materialization

- Starts from an explicit frozen base mapping.
- Requires each allowlisted dotted key to already identify a scalar leaf.
- Changes only the proposed leaves.
- Emits canonical JSON with base, overrides, resolved-config, and complete
  materialization hashes.

### Git isolation and backtracking

- Requires a clean stable repository and exact full incumbent commit.
- Creates deterministic `hypothesis/<campaign>/<proposal>` branches and
  external worktrees.
- Rejects symlink traversal and non-regular candidate targets.
- Uses Git's own apply check after static validation.
- Runs only harness-owned absolute commands with `shell=False`, reduced
  environment, time limits, exact command records, and hashed outputs.
- Rechecks exact paths and source/config contents after tests.
- Stages only validated paths, disables hooks, commits on the hypothesis
  branch, and proves stable HEAD did not move.
- Retains failed branches/worktrees, refuses duplicate proposal identities, and
  can rediscover branch/HEAD/dirty-path state after restart.
- Supports multiple independent hypotheses from the same incumbent.

### Trial lifecycle

- Ready preparation: `proposing -> proposal_validated -> queued`.
- Failure after validation: `proposing -> proposal_validated -> failed`.
- Static rejection: `proposing -> failed`.
- Replaying the same terminal preparation is idempotent; a different record
  cannot overwrite it.

## Validation results

| Check | Result |
| --- | --- |
| New Milestone 3 tests | 25/25 passed |
| Complete repository suite | 111/111 passed |
| Real temporary Git integration tests | 14/14 passed |
| Python compilation and public import | Passed |
| `git diff --check` | Passed |
| Relative Markdown links | 36 files checked; all resolve |
| Existing D1 files modified by M3 | 0 |
| Paid GPU/provider/API calls | 0 |

The 14 Git tests create actual temporary repositories, branches, worktrees,
commits, failures, and trial ledgers. They cover valid config and code
candidates, failed checks, undeclared files produced by checks, unsafe source,
static rejection before worktree creation, two independent hypotheses, dirty
stable state, unapplicable patches, duplicate/restart recovery, symlink escape,
ready-ledger replay, rejected-ledger termination, forged-record rejection, and
disabled checkout/commit hooks.

The 11 pure policy tests cover config determinism/missing leaves/stale commits,
valid diff parsing, rename/binary/mode/submodule/duplicate/malformed patches,
trusted tests, budget caps, path mismatch, multiple targets, allowed Python,
and import/call/dunder/syntax/binary/size rejection.

## Honest limitations

- Python AST checks catch obvious capabilities but are not a sandbox or proof
  of semantic safety. Worker process/container controls remain necessary.
- M3's one-file policy is intentionally narrower than a future multi-file
  objective implementation. Expanding it requires ADR/test updates.
- Failed worktrees are retained and can consume disk; automatic cleanup is
  intentionally absent until a retention policy is approved.
- Restart discovery reports existing Git state but does not resume a partially
  running test process. Worker leases/recovery belong to M4/M7.
- The candidate commit has passed contract and harness-owned preparation checks,
  not scientific evaluation. It cannot promote itself.
- The real project-owned RLT actor-objective overlay does not exist yet; M4
  must implement default forward/gradient equivalence fixtures.
- The real D1 baseline paths, evidence, and evaluator are not integrated; that
  remains the gate between M4 and M5.

## Background isolation

All work was performed in `/private/tmp/enpire-d2-agent-supervisor`. The
original `experiment/d1-rlt-baseline` worktree and its independent background
changes were not edited, staged, committed, or cleaned by M3.

## Remaining work after review

- Numbered milestones remaining: 6 (M4–M9).
- Separate D1 integration gate remains between M4 and M5.
- Remaining engineering estimate: 63–94 hours, excluding D1 completion, GPU
  queues, and RL training wall time.

M4 will add fake worker/coordinator execution, deterministic evaluator/report
interfaces, and the project-owned actor-objective overlay with equivalence and
gradient tests. It must not begin until Mohamed explicitly approves M3.
