# Milestone 0 Verification Report

- Date: 2026-08-04
- Work branch: `feature/d2-agent-supervisor`
- Base commit: `8ae2aad5ebfd2153119994f60ada285834e1318e`
- D1 branch under protection: `experiment/d1-rlt-baseline`
- Status: complete, awaiting Mohamed's review

## Work completed

- Created an isolated Git worktree and branch from the last committed D1
  checkpoint. No uncommitted D1 recovery work was copied or modified.
- Converted the approved design, private Ludvig discussions, ENPIRE design,
  RLinf/RLT guide, and D1 protocol into 32 traceable requirements.
- Recorded seven explicitly deferred capabilities so they cannot silently
  expand the first deliverable.
- Defined the outer-loop supervision model, trust boundaries, component
  responsibilities, state lifecycle, edit modes, baseline gate, formal study,
  and demo boundary.
- Defined compact, hosted, and ephemeral artifact tiers plus privacy,
  retention, and milestone documentation rules.
- Accepted three initial architecture decisions:
  1. keep the coding agent outside the RL run;
  2. use tool-free structured proposals and external evaluation;
  3. expose training-code experiments through a project-owned RLT
     actor-objective overlay rather than modifying canonical RLinf.
- Created Obsidian task `U8KKU` for durable milestone handoffs.

## Decisions and rationale

### Outer-loop rather than step-level supervision

This matches ENPIRE and Ludvig's branch-based experiment discussion while
keeping optimizer and environment execution deterministic. It also makes the
answer to “does the agent supervise RL?” precise: yes, at the experiment and
policy-improvement level.

### D1 remains the scientific authority

The new supervisor will consume D1 manifests, metrics, budgets, and decisions.
It will not replace or weaken the current launcher. Real agent trials remain
blocked until Reference A, Control B, Candidate C, and the Stage-7 evidence pack
are complete.

### Project-owned objective overlay

The pinned RLT Stage-2 worker does not provide a clean external actor-objective
plugin. A narrow project-owned overlay can support genuine code changes without
making the complete upstream worker editable or dirtying the pinned RLinf tree.
Default behavior must pass numerical and gradient equivalence tests before code
mode is allowed.

## Validation

| Check | Result |
| --- | --- |
| Existing dependency-free test suite | 29/29 passed |
| `git diff --check` | Passed |
| Relative Markdown links | All resolve |
| Requirements assigned unique sequential IDs | 32 captured (`R-001`–`R-032`) |
| Deferred capabilities recorded | 7 (`D-001`–`D-007`) |
| Initial ADRs | 3 |
| Paid GPU runs | 0 |
| External coding-agent calls | 0 |
| Changes to tracked D1 files | 0 |

The existing test suite printed its expected argparse error while verifying
that paid execution without acknowledgement is rejected; the test passed.

## Background-work isolation evidence

At final verification, the original worktree remained on
`experiment/d1-rlt-baseline` with its pre-existing/unrelated modified and
untracked Stage-5 recovery files. Milestone 0 changed only new files under
`docs/agent-supervisor/` in the isolated worktree.

## Remaining risks and dependencies

- D1 Stage 5 remains active and the scientific integration gate is not yet
  satisfied.
- The objective-overlay approach must be proven against the pinned RLinf worker
  with fixed tensor and gradient fixtures in M4.
- W&B is an external index, not literally immutable; local chained hashes and
  artifact checksums must provide tamper evidence in M1.
- Exact GPU and LLM campaign caps cannot be derived until the D1 run-time/cost
  measurements exist. The M1 schema will require explicit values and refuse
  execution when they are absent.

## Next approved unit of work

M1 will implement schemas, the append-only state machine, approval/budget
envelopes, and evidence records without running RLinf, Claude, SSH workers, or
paid compute. It must not begin until Mohamed reviews this milestone and
explicitly authorizes M1.
