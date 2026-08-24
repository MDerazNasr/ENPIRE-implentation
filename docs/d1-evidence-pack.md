# D1 Evidence Pack

Status: draft assembled on 2026-08-24 while the corrected Candidate-C r4 run
is in progress. Completed values below are evidence-backed; every r4 field is
explicitly `PENDING` until the final 256-trajectory evaluation, checkpoint,
schedule-state audit, cost record, and hashes are available.

## Audit question

D1 asks whether a single transparent 0.8x reduction in RLT's scheduled BC
regularization improves fixed-set task success relative to the upstream
schedule. The frozen Stage-1 VLA/RLT feature actor is held fixed. Control B
uses BC weights `7.0 -> 2.5`; Candidate C uses `5.6 -> 2.0`. The task is
ManiSkill `PegInsertionSideWideClearance-v1`, seed 2026, a 500-step episode
horizon, and 256 fixed reset-state evaluations.

RLinf is pinned to
`c90951a0c799a750cb5294ed10587c61cc2af8bf`. Candidate C starts a fresh
Stage-2 actor/critic from the same verified Stage-1 actor as the comparison;
it does not inherit Control-B weights.

| Role | Reproduction profile |
| --- | --- |
| Stage-1 matched actor | `configs/d1/stage1_fresh_chain_500.yaml` |
| Reference A matched fresh chain | `configs/d1/stage2_5c_reference_h100_chain.yaml` |
| Control B | `configs/d1/stage2_5d_control_h100_chain.yaml` |
| Stage-6R resume gate | `configs/d1/stage2_6_schedule_resume_gate.yaml` |
| Corrected Candidate C | `configs/d1/stage2_6_candidate_modal_multiprocess.yaml` |

## Current evidence

| Condition | Fixed-set result | Wilson 95% interval | Scientific use |
| --- | ---: | ---: | --- |
| Reference A, older 2026-08-04 checkpoint | `33/256` (`12.89%`) | `9.33%--17.55%` | Historical only; different actor hash |
| Reference A, matched fresh chain | `35/256` (`13.67%`) | `10.00%--18.42%` | Reference for Control/Candidate comparisons |
| Control B, seed 2026 | `18/256` (`7.03%`) | `4.49%--10.84%` | Valid trained one-seed control |
| Candidate C r3, historical | `32/256` (`12.50%`) | `9.00%--17.11%` | Invalid as the planned schedule test; preserve, do not promote |
| Candidate C r4, corrected | `PENDING` | `PENDING` | In progress; no decision yet |

The two Reference-A rows are intentionally separate. The August 4 checkpoint
has actor SHA-256 `c7796339...50468` and scored `33/256`. The matched
fresh-chain actor has SHA-256 `b5bf9384...363f3` and scored `35/256`. Only the
latter is the Reference A quoted beside Control B and Candidate C.

Candidate r3 is a completed but invalid intervention test. Its native resume
restored model, optimizer, target, and replay state, but reset
`rlt/update_step` from `16,400` at step 60 to `0` at step 61. Segment 2 ended
at `15,600` with `ready_for_online=0`; the planned online BC weight `2.0` was
never exercised. The observed `+5.46875` percentage-point difference from
Control B must therefore remain historical and cannot be carried into r4.

## Corrected resume contract

The project-owned, opt-in resume adapter writes one strict per-rank JSON
sidecar beside each native RLinf checkpoint. It records the RLT schedule
counters and replay generator state, validates step/rank/world-size/RLinf
commit/schedule fingerprint on load, and fails closed on missing or mismatched
state. RLinf's model and optimizer checkpoint implementation remains
unmodified.

The bounded Stage-6R gate must demonstrate all of the following before r4 is
accepted as a corrected run:

- the source checkpoint contains its schedule sidecar;
- a fresh continuation process reports a restore marker before training;
- the continuation starts from the saved `update_step`, never from zero;
- the actor-weight route changes from warm-up to online at the expected count;
- the continuation saves the next monotonically increasing counter; and
- replay state is restored rather than silently discarded.

Stage-6R passed in Modal app `ap-qwHdysi3czho3XNEgCWafX` (now stopped). The
source process emitted metric `update_step=0`, then saved sidecar
`update_step=1`. The fresh continuation reported `previous=0, restored=1`
before its first metric, that metric was `update_step=1`, replay advanced from
1 to 2 entries, and the continuation saved sidecar `update_step=2`. The
source used warm-up BC/Q weights `5.6/0.05`; the continuation used online
weights `2.0/0.45`, `actor_weight_in_warmup=0`, and `ready_for_online=1`.
The machine result is preserved at
`/workspace/results/stage6r-schedule-resume-gate.json` on the persistent Modal
volume. The paid gate attempts increased the workspace provider total by
`$0.91`, from `$153.20/$123.08` metered/billed to `$154.11/$123.99`.

## Decision boundary

The preregistered final rule needs three paired seeds and a 95% interval for
the across-seed success-rate delta. With seed 2026 alone, even a fully valid r4
can close only the engineering checkpoint; the scientific decision remains
`INCONCLUSIVE` unless the approved seed set is completed.

Operational interpretation after r4:

1. If resume-state validation or the r4 schedule audit fails, mark r4 invalid,
   do not promote, and retain the prior schedule.
2. If r4 is valid but only seed 2026 exists, report the observed delta and
   keep the formal decision `INCONCLUSIVE`.
3. Apply `KEEP` or `REVERT` only after the preregistered paired-seed rule is
   actually satisfiable.

## Reproduction entry points

Dry-resolve any D1 profile without GPU spend:

```bash
export RLINF_HOME=/absolute/path/to/RLinf
export STAGE1_CHECKPOINT=/absolute/path/to/stage1-step-500-actor
export MODEL_PATH=/absolute/path/to/pi05-base
export DATASET_PATH=/absolute/path/to/rlt-maniskill-dataset
scripts/run_d1_experiment.sh \
  configs/d1/stage2_6_candidate_modal_multiprocess.yaml \
  audit-dry-run
```

An actual launcher invocation additionally requires
`GPU_HOURLY_PRICE_USD`, `--execute`, and `--acknowledge-paid-run`. The exact
resolved command, config digest, commits, environment, and output paths are
written into each run manifest.

The corrected Modal path is operated through `modal_stage6.py`: first target
`schedule-resume-gate`, then a fresh Candidate segment to step 60, then a
fresh continuation function from `global_step_60` to step 100 with the fixed
evaluation enabled only at the end. Reproduce from the known-good commit/tag,
not from an uncommitted local copy.

## Evidence map

- Machine-readable run table: `results/d1-evidence-pack/run-table.csv`
- Cost and resource ledger: `results/d1-evidence-pack/cost-resources.csv`
- Hash/path index: `results/d1-evidence-pack/artifact-index.json`
- Fixed evaluation plot: `results/d1-evidence-pack/fixed-eval-success.svg`
- Resume-counter plot: `results/d1-evidence-pack/resume-counter.svg`
- Historical r3 result: `docs/stage6-result.md`
- Control-B report: `docs/stage5d-control.md`
- Experiment contract/checklist: `docs/baseline_protocol.md` and
  `docs/execution_checklist.md`

Compact raw evidence is committed for the matched Reference A and Control B.
Large checkpoints and verbose raw logs remain external; their preservation
paths and SHA-256 digests are indexed so an auditor can verify exported files
independently.

Control B and the relevant Modal runs used offline W&B; the local metrics,
manifests, and raw logs are authoritative. No hosted tracker URL is invented
for those runs. The older August 4 Reference-A tracker link remains in
`docs/benchmark-log.md`, but it belongs to the `33/256` historical checkpoint,
not the matched fresh-chain `35/256` result.

## Cost and resource accounting

Control B used an H100 PCIe 80 GB for 27.96 hours and cost `$91.9730` by the
launcher ledger. Historical Candidate r3 used an RTX PRO 6000 in two segments
for 30.46 hours and a launcher estimate of `$92.3051`. Modal's final r3-era
workspace audit showed `$153.20` metered and `$123.08` billed after credits;
that provider total covers the whole workspace cycle and is not attributable
to r3 alone. Stage-6R gate attempts added `$0.91` of provider spend. Candidate
r4 costs stay `PENDING` until its final manifests and provider audit are
available.

The exact 16-environment Stage-2 route has previously measured more than 24 GB
VRAM, even though VLA inference alone is expected to fit in 24 GB. Resource
selection must follow the measured complete route, not the base-model
inference estimate in isolation.

## Limitations

- Only seed 2026 is complete; no across-seed effect estimate exists.
- Control B and Candidate r3 ran on different provider/runtime/render paths.
  Corrected r4 must record the same limitation unless it exactly matches the
  Control-B environment.
- Candidate r3's result is invalid for the scheduled intervention because of
  the counter reset.
- The Stage-1 actor is a 500-step budget checkpoint, not the upstream
  2,000-step model.
- Simulator success is not evidence of real-hardware transfer.
- The 10 GB Stage-1 actor remains an external Modal-volume prerequisite. Its
  size and SHA-256 are verified before execution; the exact norm-stats input is
  now tracked, and the launcher no longer depends on an untracked cost ledger.

## Honest conclusion

**D1 has a reproducible trained control and a bounded, validated resume-state
repair, but the corrected Candidate r4 result and the preregistered multi-seed
evidence are still pending, so no hyperparameter improvement claim is
justified yet.**
