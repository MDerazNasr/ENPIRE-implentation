# Run script

`run_phase1_loop.sh` is the thin Phase 1 entry point. It checks `RLINF_HOME`,
`MODEL_PATH`, and `DATASET_PATH`, then delegates all orchestration to
`agent/policy_improvement.py`.
`run_phase1_loop.sh` launches the completed Phase-1 integration wrapper.

`run_d1_experiment.sh` is the gated D1 entry point. It performs a no-execution
dry run by default. An actual run requires both `--execute` and
`--acknowledge-paid-run`, plus the required path/seed/W&B environment variables
and `GPU_HOURLY_PRICE_USD`.
