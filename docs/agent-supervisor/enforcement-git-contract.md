# Proposal Enforcement and Git Isolation Contract Version 1

Status: implemented in Milestone 3. The normative implementation is in
[`../../supervisor/enforcement.py`](../../supervisor/enforcement.py) and
[`../../supervisor/git_manager.py`](../../supervisor/git_manager.py).

## Enforcement order

The supervisor uses four independent gates:

1. M2 parses the provider response into a strict `Proposal`.
2. M3 compares that proposal with the current campaign, incumbent, trusted
   test registry, resource caps, and diff policy before creating a worktree.
3. Git checks and applies the accepted candidate inside its own worktree.
4. M3 inspects the resulting files, runs harness-owned checks, and repeats the
   exact-path and content checks before staging and committing.

Provider claims and declared paths are never authoritative. Git's parsed
result and the candidate files are checked independently.

## Initial M3 policy

One proposal may change exactly one file. This deliberately narrow starting
policy matches the one-hypothesis-at-a-time research design.

Configuration mode:

- requires one JSON target in the campaign allowlist;
- accepts only typed, bounded parameters from the campaign contract;
- requires every dotted key to exist as a scalar in the supplied frozen base
  configuration; and
- records hashes of the base, overrides, resolved configuration, and complete
  materialization record.

Actor-objective code mode:

- requires one Python target in the campaign allowlist;
- requires declared and independently parsed diff paths to match exactly;
- rejects noncanonical paths, new/deleted files, renames, copies, file-mode
  changes, binary patches, submodules, duplicate sections, and missing hunks;
- limits the resulting candidate file to 128 KiB and requires UTF-8 Python that
  parses successfully; and
- applies an allowlist for import roots plus checks for obvious shell,
  filesystem, dynamic-code, environment, and dunder-escape capabilities.

Only test identifiers in the harness-owned registry are accepted. Commands are
not taken from the proposal. Each command uses an absolute executable,
`shell=False`, a reduced environment, a maximum ten-minute timeout, and hashed
stdout/stderr. The exact trusted command and its hash are recorded.

Static Python inspection is defense in depth, not a language sandbox. Later
workers must still use bounded processes, a minimal environment, and no
credentials or infrastructure authority.

## Git lifecycle

The stable repository must be clean. The exact incumbent must resolve to the
declared full commit. Worktrees live outside the stable repository and use the
deterministic identity:

```text
branch:   hypothesis/<campaign-id>/<proposal-id>
worktree: <root>/<campaign-id>--<proposal-id>
```

Preparation then:

1. creates a branch/worktree from the exact incumbent;
2. applies the validated patch or writes the deterministic config artifact;
3. verifies that the actual changed paths exactly match the proposal;
4. rejects symlink traversal and non-regular targets;
5. checks candidate content;
6. runs every requested harness-owned check;
7. repeats path and content validation after the checks;
8. stages only the validated paths and runs `git diff --cached --check`;
9. disables Git hooks and creates a candidate commit; and
10. verifies that the stable repository HEAD did not move.

The preparation record binds proposal/validation hashes, exact paths, base and
candidate commits, tree and staged-diff hashes, config hashes, checks, errors,
timestamps, branch, worktree, and stable HEAD before/after.

## Failure and recovery

- Static rejection creates neither a branch nor a worktree.
- Failure after branch creation retains the branch and worktree for audit.
- Nothing is automatically merged, promoted, reverted, deleted, or cleaned.
- Repeating the same proposal fails closed instead of overwriting prior work.
- `discover` reconstructs the deterministic branch, worktree, HEAD, and dirty
  path state after coordinator restart.
- Two proposal IDs create independent branches/worktrees from the same
  incumbent and cannot contaminate each other.

## Trial ledger binding

`append_preparation_to_ledger` attaches the hashed preparation record to the
M1 trial state machine:

```text
ready:              proposing -> proposal_validated -> queued
post-validation fail: proposing -> proposal_validated -> failed
static rejection:    proposing -> failed
```

Replaying the identical terminal outcome is idempotent. A different outcome or
proposal hash cannot overwrite an existing trial history.

## Non-capabilities

Milestone 3 does not implement the real actor-objective overlay, run RL, call a
provider, use GPUs/SSH/W&B, compare metrics, promote an incumbent, or merge a
candidate into the stable branch. Those responsibilities begin in M4 and the
post-D1 integration gate.
