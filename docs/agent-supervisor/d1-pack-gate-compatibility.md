# B2 D1 Pack and Integration-Gate Compatibility

Date: 2026-09-02

Status: compatibility passed; live scientific gate remains blocked

## Outcome

The B1 publisher and the existing D2 integration gate are directly compatible.
The publisher constructs the native version-1 `D1EvidencePack` type and the
gate reads that same type, so no schema adapter or version change is required.
No gate was loosened.

This result has two deliberately separate parts:

1. a clean synthetic Git fixture proves that builder output can be committed,
   audited, replayed, and accepted end to end; and
2. the real integrated repository remains `blocked` because honest current D1
   evidence cannot produce the canonical pack.

## End-to-end canonical-pack fixture

`tests/test_d1_pack_builder.py` now creates a temporary Git repository with:

- distinct incumbent and candidate commits plus an ancestor known-good commit;
- a complete version-1 campaign with exactly three paired seeds;
- one Reference record and matching Control/Candidate records for every seed;
- identical Reference/Control/Candidate runtime-identity hashes;
- a resolved legacy `KEEP` decision and explicit non-degenerate baseline;
- seven tracked, clean artifact sources; and
- a complete Stage-7 checklist.

The fixture runs `scripts/build_d1_evidence_pack.py --publish`, commits the
computed `evidence_pack.json`, and invokes `run_d1_integration_gate`. The gate
returns `ready`, the pack is tracked in a clean worktree, all referenced
commits are ancestors, and replay equivalence is true.

The fixture is contract evidence only. Its numerical values are synthetic and
make no D1, RLinf, policy, or agent-performance claim.

## Exact evaluator comparison

The fixture compares the legacy `decide_d1_candidate` result to every
corresponding field returned by the supervisor replay using equality, not a
tolerance:

| Field | Legacy result | Supervisor result | Exact |
| --- | ---: | ---: | --- |
| Decision | `keep` | `keep` | yes |
| Control mean success | `0.4000000000000001` | `0.4000000000000001` | yes |
| Candidate mean success | `0.5` | `0.5` | yes |
| Mean success delta | `0.09999999999999998` | `0.09999999999999998` | yes |
| CI95 lower | `0.09999999999999998` | `0.09999999999999998` | yes |
| CI95 upper | `0.09999999999999998` | `0.09999999999999998` | yes |

The declared legacy decision, independently replayed legacy decision, and
supervisor decision also agree exactly.

## Schema compatibility decision

No incompatibility was found. The B1 source wrapper carries publication-only
review controls—runtime-identity hashes and paths to real artifact sources—then
materializes the existing native `D1EvidencePack`. Those wrapper fields do not
belong in the evaluator wire schema and do not require an adapter.

A versioned adapter would be added only if real reviewed evidence cannot be
represented without changing meaning. Adding an adapter now would create an
unnecessary second representation and increase the risk of silent coercion.

## Preserved gates

The compatibility path retains all previous requirements:

- exact three-seed Control/Candidate matrix and Reference evidence;
- strict field sets, finite values, terminal statuses, and explicit metric
  errors;
- matching campaign, run, candidate, incumbent, RLinf, reset-set, config, and
  command identities;
- non-degenerate baseline assertion;
- resolved and exactly replayable deterministic decision;
- tracked canonical pack in a clean repository;
- known-good, incumbent, and candidate ancestor checks; and
- seven unique artifact roles whose hashes and sizes were computed by B1 from
  tracked clean sources.

The existing negative fixtures continue to cover degenerate, failed,
incomplete, duplicated, dirty, untracked, path-escaping, and ancestry-invalid
inputs. B1 fixtures additionally cover runtime mismatch, unresolved decision,
non-finite data, missing/duplicate roles, dirty/untracked sources, and
run/commit mismatch. No newly discovered incompatibility required a special
case.

## Real integrated-repository diagnostic

The read-only command below was run from clean commit `dead3b1` before B2
documentation edits:

```bash
python3 scripts/check_d1_integration_gate.py --d1-repository .
```

It returned exit code `2` with:

| Audit field | Value |
| --- | --- |
| Worktree clean | `true` |
| Stage 7 complete | `true` |
| Degenerate baseline recorded | `false` |
| Canonical pack exists | `false` |
| Replay | `null` |
| Status | `blocked` |
| Reason | `D1 evidence pack is missing at results/d1-stage7/evidence_pack.json` |

This is the expected post-B1 state. The separate readiness report explains why
the pack cannot yet be published: one paired seed, runtime mismatch, missing
reset/provenance/campaign fields, incomplete tracker coverage, remote-only
Candidate policy, and absent final review.

## B2 gate result

**Passed on 2026-09-02.** Builder-to-gate compatibility and exact evaluator
equivalence are covered by an end-to-end fixture. No schema adapter was needed,
and no safety or scientific gate changed. The real gate remains honestly
`blocked`; B2 does not authorize a live agent, provider, GPU, W&B API, SSH
worker, or RLinf run.
