# Milestone 8 Verification Report

Date: 2026-08-04

Branch: `feature/d2-agent-supervisor`

Outcome: M8 preregistration, three-arm isolation, deterministic selection,
paired confirmation, report aggregation, and synthetic rehearsal complete.
Live/scientific execution remains a D1 compatibility handoff.

## Implemented

- canonical, hashed `m8-three-arm-v1` preregistration;
- exact fixed-rule config, Claude config, and Claude actor-objective arms;
- equal discovery slots and worker caps, with equal Claude LLM caps;
- synthetic/live activation separation and ready-D1 hash requirement;
- durable atomic/hash-checked study state;
- invalid/failed/inconclusive/null result retention and slot charging;
- separate arm incumbents with cross-arm-lineage rejection;
- exact paired-seed and science-identity validation;
- deterministic within-arm best-valid selection;
- frozen-candidate, common-baseline paired confirmation;
- JSON, CSV, Markdown, HTML, and SHA-256 artifact manifest reports; and
- a one-command no-external-call study rehearsal.

## Verification evidence

| Check | Result |
| --- | --- |
| Focused M8 tests | 10 passed |
| Complete repository suite after M8 | 186 passed, 98 subtests passed |
| Synthetic discovery allocation | 3 records per arm; 9 total |
| Synthetic confirmation | selected candidate for each arm; 3 total |
| Retained adverse outcomes | 2 invalid records and 1 failed record |
| Synthetic seed-level executions represented | 30 (invalid slots launch none) |
| Cross-arm incumbent use | rejected |
| Wrong edit mode | rejected |
| Confirmation candidate replacement | rejected |
| Arm without valid candidate | remains empty; no cross-arm substitution |
| State/preregistration modification | rejected |
| Report/CSV/manifest reconciliation | passed |
| Provider/SSH/GPU/RLinf/W&B/paid calls | none |

## Demonstration boundary

The rehearsal exercises real state transitions, exact evaluator results,
selection, confirmation, and static reporting using deterministic evidence
fixtures. Its success values and decisions do not describe RLT, a VLA, Claude,
or the relative quality of any study arm.

## D1 compatibility handoff

No M8 control-plane feature needs the unfinished D1 loop. Live execution does:

1. D1 must provide a clean, non-degenerate, reviewed Stage-7 pack whose replay
   gate returns `ready`;
2. its baseline/RLinf/reset/evaluator identities populate `StudySpec`;
3. M1–M6 produce each evaluated candidate record;
4. M7 schedules the exact paired seed contracts and returns evidence; and
5. M8 records/selects/confirms without altering the D1 science rules.

The D1 dirty worktree, incomplete Stage 7, absent evidence pack, and degenerate
recorded baseline are external compatibility issues owned by the other
workstream. They were not modified here.

## Honest limitations

- Live D1/RLinf evidence, W&B reconciliation, GPU utilization, and actual costs
  are unavailable.
- The synthetic demo directly supplies evaluated fixture records; M7 already
  separately verifies real concurrent dispatch, leases, restart, and loss.
- Study snapshots are hash-checked, while live scientific tamper evidence also
  relies on the M1 ledger/external anchors.
- Three seeds are appropriate only for the frozen D1 engineering decision and
  do not establish general agent superiority.
- M9 still owns the final Ludvig-facing demo narrative, replay packaging, and
  final deliverable polish.
