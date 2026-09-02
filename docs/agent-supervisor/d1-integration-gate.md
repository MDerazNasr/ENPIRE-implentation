# D1 Integration Gate

Status on 2026-08-04: **BLOCKED by D1 scientific evidence availability, not by
the supervisor implementation.**

## Superseding integration status — 2026-09-02

D1 has advanced from the historical state described below to commit `eed314f`.
Stage 7 is marked complete, Reference A is non-zero, and one trained corrected
Control/Candidate seed is available. A read-only audit still returns `blocked`
because the D1 worktree is dirty and the strict
`results/d1-stage7/evidence_pack.json` is absent. The existing
`results/d1-evidence-pack/` directory is valuable source evidence but is not
the version-1 gate artifact.

B1 now provides `scripts/build_d1_evidence_pack.py`. Its tracked
`results/d1-stage7/readiness.json` deterministically inventories the source
evidence and reports every current blocker while explicitly setting
`canonical_pack_claimed` to false. Strict publication remains refused; no
placeholder `evidence_pack.json` was created. See `d1-pack-builder.md` and
`d1-evidence-schema-mapping.md`.

The gate must continue to reject live activation until a clean reviewed commit
contains matched Control/Candidate evidence for the approved seed set. The
August audit below is retained as historical evidence and must not be read as
the current D1 status.

This gate prevents the first live coding-agent campaign from silently treating
an infrastructure smoke, single-seed null result, or mutable worktree as a
reproducible RLT baseline.

## Historical read-only audit — 2026-08-04

The command below was run against the background D1 worktree without modifying
it:

```bash
python3 scripts/check_d1_integration_gate.py \
  --d1-repository /Users/mderaznasr/Documents/GitHub/ENPIRE-implentation
```

It returned exit code `2` and `status: blocked` for four independently useful
reasons:

1. the D1 worktree contains uncommitted Stage-5 work, so it is not an immutable
   Stage-7 handoff;
2. all Stage-7 checklist items remain open;
3. `results/d1-stage7/evidence_pack.json` does not exist; and
4. D1 explicitly records a degenerate baseline and blocks Stage 6.

The scientific evidence behind reason 4 is honest and useful: Reference A
completed at `0/256` success; the bounded scratch-RLT probe completed at
`1/256`, collected only `41/10,000` replay transitions, and performed zero
actor/critic updates. Control B and Candidate C were intentionally not launched.

## Stage-7 pack contract

The eventual `evidence_pack.json` is strict version-1 JSON. Unknown or missing
fields are rejected. It binds:

- a pack ID and reviewed conclusion;
- reviewer identity and UTC review timestamp;
- a known-good scientific source commit;
- distinct incumbent and candidate commits;
- the full supervisor `CampaignSpec`, including pinned RLinf commit, seeds,
  reset-set hash, evaluator version, budgets, and evaluation count;
- an explicit non-degenerate-baseline assertion;
- the decision recorded by the legacy D1 path;
- Reference A plus exactly one Control B and Candidate C run for every approved
  seed; and
- the seven required Stage-7 artifact IDs listed below.

Each condition run records its condition, seed, project/config/command hashes,
UTC timestamps, exit contract, elapsed time, GPU cost, success rate, successful
episode length when available, and explicit metric errors.

Required artifact IDs:

- `commands`
- `configs`
- `tracker`
- `run-table`
- `plots`
- `cost-report`
- `limitations`

Each artifact also has a kind, URI, SHA-256 digest, and byte size.

## Git binding without a self-referential commit

The reviewed pack must be tracked in a clean repository `HEAD`. Its
`known_good_commit`, `incumbent_commit`, and `candidate_commit` must each exist
as ancestors of that `HEAD`.

The pack does not claim that its own containing commit is its content field:
embedding the containing commit hash inside a tracked file would change the
commit hash. Instead, Git `HEAD` immutably contains the reviewed pack, while
the pack binds the earlier source/evidence commits it audits.

## Replay and equivalence

The gate converts matched Control B and Candidate C records into strict
`TrialEvidence`. It then runs two independent call paths over the same ordered
seed values:

1. the frozen legacy `decide_d1_candidate` function;
2. M4's `OfflineD1Evaluator` and versioned `DecisionRecord`.

The gate opens only when:

- the declared legacy decision, replayed legacy decision, and supervisor
  decision agree;
- control mean, candidate mean, mean delta, and CI95 agree exactly;
- Reference A evidence is complete;
- the baseline is explicitly non-degenerate;
- all evidence and artifact contracts pass; and
- the clean/tracked Git ancestry checks pass.

Missing metrics, failed runs, mismatched decisions, incomplete seeds,
provenance differences, dirty worktrees, untracked packs, and degenerate
baselines cannot open the gate.

## What can unblock it

D1 must first receive an explicitly approved revised scientific protocol that
can produce a usable Control B. After Reference A, Control B, and Candidate C
are completed under that matched protocol, Stage 7 can publish the pack and a
clean reviewed commit. At that point this command performs the replay; no
supervisor code change should be necessary unless the pack exposes a genuine
schema incompatibility.

M5 remains prohibited while this gate returns anything other than `ready`.
