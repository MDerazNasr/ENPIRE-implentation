# G0/E0 Independent Evaluator Integrity

Status: **GPU-free fixture, reset, packaging, and local-isolation rehearsals
pass; production custody and deployment remain blocked**

This gate proves the fail-closed input and replay behavior required before the
official evaluator may consume scientific evidence. It evaluates deterministic
fixtures only and grants no campaign, provider, GPU, model-egress, evaluation,
promotion, or paid-execution authority.

## Implemented boundary

`supervisor/evaluator_integrity.py` adds strict contracts for:

- explicit ordered 256-ID reset-set artifacts;
- same-task/simulator/generator identity and disjoint development/final sets;
- six exact episode batches: Control and Candidate for three paired seeds;
- per-reset boolean `success_once` evidence;
- reset omission, duplication, reordering, substitution, and overlap rejection;
- condition commit and seed identity;
- evaluator source/environment hashes;
- byte-stable deterministic result envelopes; and
- rejection of final reset/evaluator material from nested agent contexts.

The evaluator ignores agent prose because prose is not part of its input
contract. New G0 decisions use the separate versioned
`supervisor.g0_decision.decide_g0_candidate`; the historical D1 rule remains
unchanged for replay.
The fixture layer preserves per-reset outcomes so paired analysis can be
reconstructed rather than trusting only candidate-supplied aggregate metrics.

## Adversarial matrix

| Threat | Expected result |
|---|---|
| Repeated identical replay | Byte-identical result and fingerprint |
| Missing condition/seed batch | Reject before decision |
| Duplicate condition/seed batch | Reject before decision |
| Partial reset list | Reject artifact/input |
| Duplicate reset ID | Reject artifact |
| Development/final overlap | Reject pair |
| Reset reordering or substitution | Reject batch |
| Condition commit drift | Reject batch |
| Non-boolean or mismatched outcomes | Reject batch |
| Final reset IDs/trajectories in agent context | Reject context |
| Evaluator source in agent context | Reject context |

## Local validation

```bash
python3 -m unittest tests.test_g0_e0_integrity -v
python3 scripts/run_g0_e0_integrity_preflight.py

# Build only in an external disposable/reviewer-owned location.
python3 scripts/build_g0_evaluator_bundle.py --output /tmp/enpire-g0-evaluator
```

The preflight hashes the integrity, deployment, official-rule, supervisor,
reset, and protocol sources. It binds the source-derived/live-confirmed reset
hashes and the non-authorizing local isolation receipt. Every execution and
promotion authority flag remains false.

The current checked-in non-authorizing output is
[`../../results/agent-supervisor/g0/e0-preflight-lambda-h100-image-v1.json`](../../results/agent-supervisor/g0/e0-preflight-lambda-h100-image-v1.json).
Earlier receipts remain preserved as historical evidence.

## Remaining acceptance gates

- Deploy the reviewed bundle under a separate evaluator-owned OS identity or
  immutable mount and freeze its production source/environment hashes.
- Select independent production destinations and custody for the append-only
  ledger and trusted external head anchor.
- Extend context auditing to the actual production context bundle and worker
  delivery path.
- Review the confidence/decision rule before evaluating new policy outcomes.

Until those gates pass, E0 is not complete and no scientific evaluation may
run.

## Isolated bundle and ledger boundary

`scripts/build_g0_evaluator_bundle.py` copies only the evaluator runner,
canonical encoding, integrity contract, and official D1 decision rule into a
hash-manifested tree outside the repository, then removes write permission from
all bundle files and directories. It rejects destinations inside the project.

`scripts/g0_independent_evaluator.py` accepts one strict JSON input, rejects
unknown fields, produces the deterministic envelope, and can append it to a
hash-chained JSONL ledger paired with a separately stored trusted head anchor.
Replay checks the complete chain and anchor before append, detecting content
edits, deletion, reordering, or forged tails.

This is an isolation mechanism, not authority. The bundle manifest sets
evaluation, GPU, and promotion authorization to false. The production paths
for the bundle, ledger, and anchor must be chosen during protocol freeze and
must remain outside candidate-writable worktrees.

Read-only mode bits prove the fixture packaging behavior, not a complete
production security boundary: the bundle owner can restore write permission.
Production acceptance therefore requires a separate OS identity or immutable
mount controlled by the evaluator operator, plus independent verification of
the manifest after deployment. The trusted ledger anchor must not share the
ledger's writer or failure domain.

The same-user local custody/deployment rehearsal and strict production receipt
schemas are specified in
[`g0-evaluator-custody-and-deployment.md`](g0-evaluator-custody-and-deployment.md).
The rehearsal passed but explicitly sets both production acceptance fields to
false.

## Reset capture boundary

Pinned RLinf and ManiSkill source plus NumPy 1.26.4 were installed in an
isolated `/private/tmp` environment. Source audit established that the actual
initial reset identities are ManiSkill's expanded episode seeds, not RLinf's
internal 0--126 `reset_state_ids`. `scripts/export_g0_reset_sets.py` accepts a
source-bound capture, requires extractor identity
`rlinf-maniskill-fixed-reset-export-v1`, requires the explicitly supplied
frozen RLinf commit, enforces seeds 2026/2027, validates 256 unique IDs per set
and zero overlap, and writes canonical artifacts plus a non-authorizing receipt.
Unknown fields, identity drift, and pre-existing output directories fail closed.

`scripts/capture_g0_maniskill_episode_seeds.py` implements that exact pinned
expansion. Two captures are byte-identical, contain 256 unique IDs per set, and
have zero overlap. Development IDs and public receipts are checked in; ordered
final IDs are excluded from the repository. The 512-reset CPU simulator
confirmation passed; separate final-artifact custody remains required. See
[`g0-reset-source-audit.md`](g0-reset-source-audit.md).
