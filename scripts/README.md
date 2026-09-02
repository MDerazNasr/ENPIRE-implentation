# Run script

`run_phase1_loop.sh` is the thin Phase 1 entry point. It checks `RLINF_HOME`,
`MODEL_PATH`, and `DATASET_PATH`, then delegates all orchestration to
`agent/policy_improvement.py`.
`run_phase1_loop.sh` launches the completed Phase-1 integration wrapper.

`run_d1_experiment.sh` is the gated D1 entry point. It performs a no-execution
dry run by default. An actual run requires both `--execute` and
`--acknowledge-paid-run`, plus the required path/seed/W&B environment variables
and `GPU_HOURLY_PRICE_USD`.

`run_real_policy_demo.py` is the meeting-safe, dependency-free CPU demo. It
trains three control and three candidate residual policies, routes their real
metrics through the supervisor evaluator, and writes a visual public bundle.
`toy_policy_worker.py` is its fixed subprocess worker; it is not a general
command surface. `verify_real_policy_demo.py` rehashes all curated artifacts.

`build_d1_evidence_pack.py` atomically writes a deterministic D1 readiness
envelope. With `--publish`, it writes the strict Stage-7 pack only when the
tracked reviewed source, matched runtime identity, three-seed matrix, resolved
decision, ancestor commits, and all seven real hashed artifacts pass.
