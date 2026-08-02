# D1 No-GPU Infrastructure

Stage 1 adds an external, dependency-free planning and launch boundary around
the pinned RLinf entry point. It does not import or edit RLinf.

## Profiles

| Profile | Purpose | Paid status |
| --- | --- | --- |
| `stage1_pilot.yaml` | Six-step, step-5 checkpoint resource pilot | Approved only after Stage 2 environment review |
| `stage1_scientific.yaml` | Upstream 2,000-step Stage-1 proposal | Not approved; cost gate required |
| `stage2_smoke.yaml` | Bounded Stage-1-to-Stage-2 contract check | Not approved until pilot checkpoint exists |
| `reference.yaml` | Reference-A fixed-ID evaluation contract | Not approved until baseline gate |
| `control.yaml` | Upstream scheduled-BC Control B | Not approved until baseline gate |
| `candidate_bc_080.yaml` | Candidate C with only 0.8x scheduled BC weights | Not approved until Control B is valid |

The `.yaml` files use the JSON subset of YAML so validation requires only the
Python standard library.

## Required environment

Profiles resolve only the variables they reference:

- `RLINF_HOME`: pinned RLinf checkout;
- `MODEL_PATH`: compatible pi0.5 base model for Stage 1;
- `DATASET_PATH`: full official Stage-1 dataset;
- `NORM_STATS_PATH`: dataset-matched `norm_stats.json`;
- `STAGE1_CHECKPOINT`: saved `global_step_<n>/actor` directory for Stage 2;
- `WANDB_PROJECT`: shared tracker project name;
- `D1_SEED`: explicit integer experiment seed;
- `GPU_HOURLY_PRICE_USD`: required only for an actual paid execution.

Secrets such as the W&B API key are authenticated outside the config and are
never copied into the manifest.

## Dry run

Dry-run is the default and does not require the referenced paths to exist:

```bash
scripts/run_d1_experiment.sh configs/d1/control.yaml control-seed-2026
```

It prints the resolved manifest, working directory, exact command, config hash,
commits, evaluation contract, and budget. It does not create the run directory
or launch RLinf.

## Paid-run gate

Execution requires both flags:

```bash
scripts/run_d1_experiment.sh configs/d1/stage1_pilot.yaml pilot-001 \
  --execute --acknowledge-paid-run
```

Before process creation the launcher verifies all required paths and the exact
RLinf commit. Missing variables, missing assets, placeholders, expert takeover,
an RLinf revision mismatch, a reused run ID, or a cumulative cost cap prevents
launch.

## Evidence written by an actual run

Each unique `results/d1/<run-id>/` directory receives:

- `manifest.json`: resolved config, commands, commits, paths, host, status,
  timing, price, and cost;
- `command.sh`: shell-escaped exact command;
- `run.log`: combined RLinf stdout/stderr;
- `resources.jsonl`: timestamped GPU, disk, and estimated cost samples;
- `events.jsonl`: cost-threshold and cap events.

The append-only `results/d1_runs.jsonl` ledger stores completed-run manifests.
Cumulative spend is reconstructed from that ledger before each launch. Configs
currently cap cumulative D1 spend at `$15`; reporting events occur at `$5`,
`$10`, and `$15`. A higher cap cannot exceed `$25` under the Stage-1 schema and
requires a reviewed config change.

Resource sampling uses `nvidia-smi` when available and remains valid on a
no-GPU development host. Pod billing must still be checked with the provider:
terminating the training subprocess does not prove the pod stopped billing.

## Scientific decision module

`agent/d1_rules.py` implements the preregistered three-seed paired comparison.
It returns `keep`, `revert`, or `inconclusive`; incomplete inputs cannot fall
through to the historical Phase-1 smoke rule. The ceiling efficiency condition
interprets improvement as at least 10% shorter successful episodes.

## Stage-2 verification boundary

The generated Hydra keys are based on the pinned upstream configuration and
the earlier successful smoke logs. Stage 2 must still verify the commands
against the actual pinned checkout before any execution. In particular,
Reference A's `rlt_policy_switch.enable=false` must be proven to execute only
VLA reference chunks rather than assumed from its name.

