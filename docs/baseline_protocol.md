# D1 RLT + ManiSkill Baseline Protocol

Status: Stage 0 protocol, awaiting final scientific sign-off before Stage 1.

## Purpose

D1 converts the completed one-transition integration smoke into a reproducible
RLT baseline and one controlled regularization experiment. It asks whether the
complete two-stage RLT pipeline can improve fixed-condition ManiSkill task
success, or successful-task efficiency, relative to its frozen VLA reference
behavior. The direction and magnitude are exploratory; no success target is
assumed in advance.

The official RLinf RLT + ManiSkill guide is the implementation source of truth.
RLinf and the frozen pi0.5 base VLA remain unmodified and are launched as
external dependencies.

## Pinned implementation boundary

- Qualia starting commit: `8c5abfcd04e8b4a155f82e8b3537169169ef8337`.
- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`.
- Initial simulator/task family: the RLinf RLT ManiSkill example. This is a D1
  testbed, not a permanent simulator dependency for the harness.
- Stage 1 trains the RLT-token feature path jointly with the VLA action
  objective using RLinf's upstream objective.
- Stage 2 freezes the selected Stage-1 feature checkpoint and trains the small
  actor/critic against simulator experience and the VLA reference action.
- No RLinf source file or frozen base-VLA weight is an editable experiment
  variable.

The exact model revision, full dataset revision/hash, `norm_stats.json`, task
identifier, action/state dimensions, seeds, checkpoint, and resolved Hydra
configuration must be captured before a scientific run can begin.

## Preregistered conditions

### Reference A — frozen reference actions

Use the trained Stage-1 feature model, but execute only the VLA reference
action chunks. The Stage-2 actor does not control the environment. This is the
behavioral reference, evaluated on the same fixed reset IDs as the trained
conditions.

### Control B — upstream scheduled Stage-2 RLT

Train and evaluate Stage-2 RLT with the pinned upstream BC/Q schedule and no
tuning adjustment:

- warmup BC weight: `7.0`
- online BC weight: `2.5`
- warmup Q weight: `0.05`
- online Q weight: `0.45`

Paths, logging, budgets, and the unsupported expert checkpoint are operational
resolutions, not tuning changes.

### Candidate C — 0.8x scheduled BC regularization

Change only the two scheduled BC weights:

- warmup BC weight: `7.0 -> 5.6`
- online BC weight: `2.5 -> 2.0`

Keep Q weights, Stage-1 checkpoint, dataset, task, seeds, reset IDs, training
budget, evaluation budget, intervention policy, and all other scientific
settings identical to Control B.

## Expert-takeover decision

Disable simulated expert takeover consistently in Reference A, Control B, and
Candidate C. The checked-in upstream example contains a placeholder expert
checkpoint, so enabling it without a verified compatible artifact would make
the conditions unreproducible. This is an explicit, disclosed deviation from
that example configuration. It can be revisited as a separately controlled
experiment if a compatible expert is obtained.

## Evaluation contract

The primary endpoint is fixed-ID `eval/success_once`. Conditions must use the
same task, reset IDs, number of trajectories, episode horizon, success
definition, and expert/intervention setting.

Secondary outcomes are:

- successful episode length and task throughput;
- episode return and overall episode length;
- actor, critic, BC/reference, and Q diagnostics;
- actor/reference switching, intervention, and replay diagnostics;
- wall time, peak VRAM/RAM, disk use, and dollar cost.

Training loss is diagnostic and cannot independently promote a candidate.
Pilot, subset, smoke, and single-seed outcomes can justify further testing but
cannot satisfy the scientific keep rule.

The provisional confirmation design uses one approved Stage-1 checkpoint and
three independent Stage-2 training seeds, evaluated on the same 256 fixed reset
IDs used by the upstream Stage-2 evaluation configuration. This measures
Stage-2 variance; Stage-1 seed variance remains an explicit limitation unless
multiple Stage-1 checkpoints are later approved.

## Keep, revert, and inconclusive rule

If mean Control B success is below `90%`, keep Candidate C only when:

1. its mean success improves by at least `5` absolute percentage points across
   the approved seeds; and
2. the `95%` confidence interval for the candidate-minus-control success
   difference is strictly above zero.

If mean Control B success is at least `90%`, keep Candidate C only when:

1. its success is non-inferior within `5` absolute percentage points; and
2. mean successful episode length improves by at least `10%`.

Use paired fixed-reset outcomes when episode-level records are available.
Return `INCONCLUSIVE`, rather than forcing keep or revert, if required seeds or
episode-level evidence are missing, a condition fails, evaluation sets differ,
or the interval cannot be computed. A valid candidate that fails its applicable
keep criteria is `REVERT`; its artifacts remain preserved.

## Compute and spending policy

- Start on the smallest economical NVIDIA instance with at least 24 GB VRAM.
- Measure the real Stage-1 peak; scale only if Stage-1 checkpoint training
  demonstrably cannot fit. VLA inference and the small PPO/RLT actor do not by
  themselves justify a larger instance.
- Initial paid-pilot cap: `$15` cumulative spend.
- Report cumulative spend at `$5`, `$10`, `$15`, `$20`, and every subsequent
  `$5` threshold.
- Do not cross `$25` cumulative project spend without notifying Mohamed and
  receiving explicit approval first.
- Capture hourly price, billable elapsed time, and estimated/final cost. Process
  termination is not proof that a rented pod stopped billing; pod state must be
  verified separately.

## Promotion and stopping gates

1. Stage 1 infrastructure must pass locally before provisioning paid compute.
2. The checkpoint-producing pilot must report measured memory, throughput, and
   cost before any long training is approved.
3. The Stage-2 checkpoint contract smoke must pass before scientific baseline
   runs.
4. Candidate C is run only if Reference A and Control B are reproducible and
   sufficiently non-degenerate to support the comparison.
5. No coding-agent, multi-GPU trial coordinator, or real-hardware work is part
   of D1.

## Required evidence per scientific run

Preserve the project and RLinf commits, complete resolved config, seed,
model/dataset/checkpoint identifiers, hardware, command, timestamps, exit
status, raw logs, W&B URL, local JSONL record, metrics, artifacts, resource use,
and cost. Completed run directories are immutable and negative/null results are
not deleted.

