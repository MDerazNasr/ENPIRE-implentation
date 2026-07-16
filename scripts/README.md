# Run script

`run_phase1_loop.sh` is the thin Phase 1 entry point. It checks `RLINF_HOME`,
`MODEL_PATH`, and `DATASET_PATH`, then delegates all orchestration to
`agent/policy_improvement.py`.
