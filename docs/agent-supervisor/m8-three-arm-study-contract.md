# M8 Preregistered Three-Arm Study Contract

Status: implemented and rehearsed with deterministic synthetic evidence. Live
activation and scientific interpretation remain blocked on the separately
owned D1 Stage-7 integration gate.

## Research question and arms

M8 freezes one narrow engineering comparison before accepting results:

1. `fixed-rule-config`: the transparent rule-based controller may propose only
   configuration changes;
2. `claude-config`: a short, tool-free Claude session may propose only the same
   configuration class; and
3. `claude-code`: a short, tool-free Claude session may change only the
   project-owned actor-objective overlay from M6.

This evaluates outer-loop supervision strategies. It does not put an LLM in
the action, gradient, rollout, reset, or evaluation loop.

## Frozen science identity

`StudySpec` binds the study to:

- the exact baseline and RLinf commits;
- the reset-set hash and evaluator version;
- exactly three paired seeds;
- the primary and secondary metrics;
- the exact ordered arm definitions;
- three discovery candidate slots per arm;
- per-candidate wall-time, GPU-cost, and LLM-cost caps; and
- selection rule `m8-best-valid-v1`.

Its canonical SHA-256 fingerprint is the preregistration identifier. An
activation binds that exact fingerprint. A synthetic activation is explicitly
marked and cannot claim D1 readiness. A live activation requires the hash and
`ready` status of the D1 compatibility gate.

## Fair budgets

All three arms have identical worker wall-time and GPU-cost caps per discovery
candidate. Both Claude arms have the same LLM cap. The fixed-rule arm has a
zero LLM cap because it makes no LLM call; inventing an unused LLM allowance
would not improve fairness. The report includes a mechanical parity audit.

Every arm receives exactly three discovery slots. Invalid proposals, failed
workers, inconclusive evaluations, and null improvements consume their
assigned slot and remain in the record. No arm may borrow a slot or candidate
from another arm.

## Discovery unit and run count

One discovery record is one candidate experiment, not one seed process. A
complete candidate experiment aggregates the exact three paired-seed worker
runs required by the existing frozen evaluator. Therefore:

- the preregistered discovery set is nine candidate experiments;
- a fully valid discovery set can contain up to 27 seed-level worker runs;
- each selected candidate receives one independent three-seed confirmation;
  and
- the maximum full study is 12 candidate records and 36 seed-level worker
  runs.

Invalid proposals produce no worker runs, so the retained record can contain
fewer than 36 without changing the allocation.

## Isolated improvement loops

Each arm starts from the same frozen baseline and owns a separate incumbent
pointer. A discovery record must name the current incumbent of its own arm and
all evidence must match that arm, parent, candidate, RLinf commit, reset set,
evaluator, and paired seeds. Only the deterministic M4 evaluator can advance
that pointer after `KEEP`.

The study state rejects a record whose parent is another arm's incumbent.
Stable project code and other arms never move when one arm advances. This is
the M8 boundary that composes the M1–M6 improvement loop with the M7 scheduler:

1. the appropriate proposer produces one bounded candidate;
2. M3/M6 validate and isolate it;
3. M7 runs its exact per-seed contracts on independent workers;
4. M4 evaluates the returned evidence;
5. M8 records the result and updates only that arm if the evaluator says
   `KEEP`.

M8 accepts evaluated records rather than controlling workers directly. This
keeps scheduling/recovery authority in M7 and scientific authority in the
evaluator.

## Frozen selection and confirmation

Selection cannot run until all nine discovery slots are recorded. Within each
arm, eligible candidates are complete, candidate-valid records with a terminal
non-failure evaluation and a candidate success mean. The deterministic order
is:

1. highest candidate mean success;
2. highest mean success delta;
3. lowest GPU cost;
4. lowest wall time; then
5. lexicographically smallest record ID.

The source record hashes and selected record/commit are persisted. If an arm
has no eligible candidate it is reported as missing; no candidate from a
different arm substitutes for it.

Confirmation must rerun exactly the frozen selected commit against the common
baseline, reset set, evaluator, and paired seeds. A different candidate,
partial seed set, duplicate seed, or different science identity fails closed.

## Durable state and report

The locked, atomic study snapshot contains the immutable spec/activation, arm
lineages, every discovery and confirmation record, selections, and a monotonic
generation. A canonical payload hash detects offline modification. Existing
append-only M1 evidence and external artifact anchoring remain the authority
for a live scientific audit.

The report writer emits:

- `study-report.json`: complete machine-readable protocol and results;
- `study-trials.csv`: one row for every retained record;
- `study-report.md` and `study-report.html`: presentation views; and
- `artifact-manifest.json`: SHA-256 hashes of the report artifacts.

Totals cover candidate experiments, seed-level runs, invalid/failed/
inconclusive outcomes, decisions, wall time, GPU and LLM costs, tokens, and
human interventions. Synthetic output always states that it supports no RL,
policy, agent, or arm-performance claim.

## Statistical boundary

The three paired seeds implement the approved D1 confirmation rule. They do
not justify a broad population or model-superiority claim. The final study must
present per-seed paired outcomes, mean/range or the frozen CI, null and failed
results, and practical resource costs. Any interpretation must stay within the
preregistered task, baseline, evaluator, and compute envelope.

## One-command rehearsal

```bash
python3 scripts/run_m8_study_demo.py --output /tmp/m8-study-demo
```

The fixture deliberately includes invalid proposals, a worker failure,
`KEEP`/`REVERT` decisions, per-arm lineage changes, deterministic selection,
and three confirmations. It makes no network, provider, SSH, GPU, RLinf, W&B,
or paid-service call.
