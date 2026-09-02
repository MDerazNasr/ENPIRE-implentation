# D1/D2 Reconciliation Record

Date: 2026-09-02

Status: A2 reconciliation and A3 offline verification passed

## Inputs

- D1 source branch: `experiment/d1-rlt-baseline`
- D1 source commit: `eed314f68243bb82081f3ab145615f28e2e86173`
- D2 source branch: `feature/d2-agent-supervisor`
- D2 source commit: `707b88f0bfb745c295042f012930ed219e2c21be`
- Integration branch: `integration/d1-d2-agentic-harness`
- Isolated worktree: `/private/tmp/enpire-d1-d2-agentic-harness`

## Reconciliation policy

Newer D1 experiment code, configurations, resume repair, Modal execution,
results, and evidence are authoritative. D2 contributes its supervisor,
contracts, tests, examples, demos, ADRs, and reporting system. Historical D2
milestone reports remain dated evidence; superseding notes identify statements
that no longer describe current D1.

## Merge result

The history-preserving merge produced one content conflict:
`docs/README.md`. It was resolved by retaining the complete newer D1 document
map and adding the D2 supervisor document map. No source, configuration,
result, or test file conflicted.

The merge adds:

- the complete `supervisor/` package;
- supervisor-specific tests and examples;
- M4, M7, M8, M9, and real-policy demo/verification scripts;
- `docs/agent-supervisor/` contracts, ADRs, verification reports, handoff, and
  presentation guidance; and
- the approved generic `modal_app.py` launcher plus its README instructions.

The canonical program plan and root `tmp/` ignore policy were carried from
Obsidian task `MI5T8` planning work. The empty `mo-notes.txt` was not carried.

## Preservation checks

- A path comparison against D1 `eed314f` found no changes under `agent/`,
  `configs/d1/`, `envs/`, `modal_stage6.py`, `sitecustomize.py`, or `results/`.
- A path comparison against D2 `707b88f` found no supervisor code drift;
  `supervisor/README.md` differs only because its current-status paragraph was
  corrected during reconciliation.
- The active D1 worktree remains separate and its 20 GB local `tmp/` evidence
  tree was not copied, deleted, or modified.
- Root `tmp/` is ignored in the integrated tree so local evidence cannot be
  added wholesale accidentally.
- No paid service, provider call, GPU, SSH worker, W&B API, or RLinf process was
  invoked during reconciliation.

## Documentation corrections

Current-status corrections were made in the root README, supervisor README,
supervisor documentation index, integration-gate documents, requirements
traceability, M8 contract, M9 verification, and final handoff.

The reconciled status is:

- D1 Stage 7 is marked complete and one corrected Control/Candidate seed exists.
- The existing `results/d1-evidence-pack/` is source evidence, not the strict
  version-1 supervisor pack.
- The live gate remains blocked by the absent canonical pack and incomplete
  matched approved seeds.
- Historical reports retain their original dated observations and are labeled
  when a superseding status exists.

## A3 verification result

A3 passed on 2026-09-02 against clean integration commit
`059a130927c99d09c013886bd06cdeb83fc48d18`:

- the combined suite passed 236 tests and 125 subtests in 27.64 seconds;
- Python compilation and Git whitespace/conflict-marker checks passed;
- 49 relative links across 62 Markdown files resolved;
- the offline M4, M7, M8, and M9 demonstrations completed without external
  calls, and the M9 verifier accepted its 15-artifact delivery bundle with
  fingerprint
  `79c7f7e600a6814d6b95db42c4e4a8c711a47c90b077eaebca48e7fc974a02dd`;
- the real CPU policy demo completed with six-worker maximum concurrency and a
  deterministic `KEEP` decision, and its verifier accepted 14 artifacts with
  fingerprint
  `9ae476d209b1f69c368cf084e01ce283df49961e377e0b5c7373ee711ec6ce15`;
  this remains explicitly toy/non-RLT evidence; and
- the D1 and D2 source branches remain at their recorded heads, while the
  original D1 worktree and its 20 GB ignored evidence tree remain unchanged.

The reconciliation and offline regression baseline are therefore ready for
Workstream B. No paid service, provider, GPU, SSH worker, W&B API, or RLinf
process was used for A3.
