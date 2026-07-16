# Phase 1 policy improvement

- `metrics.py` normalizes RLinf's emitted metrics without importing RLinf.
- `rules.py` owns the transparent adjust/continue and keep/revert decisions.
- `policy_improvement.py` merges the four-field config, launches RLinf, reads
  metrics, applies the rule, and records the selected run.

Every run retains its resolved command, raw log, metrics, and summary. A compact
record is also appended to `results/phase1_runs.jsonl`.
