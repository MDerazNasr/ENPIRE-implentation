# D1 Integration Gate Verification

Date: 2026-08-04

Branch: `feature/d2-agent-supervisor`

Historical-snapshot notice: this report records the 2026-08-04 verification.
As of 2026-09-02 D1 is at `eed314f`, Stage 7 is marked complete, and one
corrected Control/Candidate seed exists. The gate is still blocked by the
absent canonical pack, a dirty source worktree, and incomplete matched-seed
evidence; see `d1-integration-gate.md` for the superseding status.

Second superseding notice: B2 reran the gate from clean integrated commit
`dead3b1`. Stage 7 was complete and no degenerate baseline was detected; the
only gate-level reason was the absent canonical pack. The separate B1
readiness report explains the underlying scientific and provenance blockers.
An end-to-end fixture also proves exact native-schema builder/gate compatibility
without an adapter. See `d1-pack-gate-compatibility.md`.

## Outcome

The integration-gate implementation is complete, but the live D1 gate is
correctly **BLOCKED**. This is the intended safety outcome for the currently
available null/degenerate baseline evidence.

## Implemented evidence

- strict D1 Stage-7 evidence-pack and per-condition run contracts;
- required artifact-role completeness and digest checks;
- D1 run normalization into M4 `TrialEvidence`;
- direct legacy-rule and supervisor-evaluator replay;
- exact comparison of decision, means, mean delta, and CI95;
- Reference A validity and explicit non-degenerate-baseline gates;
- clean repository, tracked pack, and commit-ancestry checks;
- read-only CLI with `0` for ready and `2` for blocked/invalid;
- fixtures for complete, degenerate, mismatched, failed, missing, duplicate,
  dirty, untracked, and incomplete evidence.

## D1 result observed on 2026-08-04

| Field | Observed value |
| --- | --- |
| D1 HEAD | `8ae2aad5ebfd2153119994f60ada285834e1318e` |
| Worktree clean | no |
| Stage 7 complete | no |
| Pack present | no |
| Degenerate baseline recorded | yes |
| Gate status | `blocked` |

No D1 file, GPU job, provider service, W&B run, or paid execution was changed or
started by this audit.

## Validation

- Complete repository suite: 142 tests passed, 72 subtests passed.
- Python compilation, public export audit, `git diff --check`, relative
  Markdown links, and the live exit-code-2 audit passed.
- An unsafe pack path containing `..` is rejected before any out-of-repository
  read.

## Boundary

Passing synthetic complete-pack fixtures proves compatibility logic, not that
D1 is scientifically complete. Only a future clean, reviewed Stage-7 pack can
open the real gate.
