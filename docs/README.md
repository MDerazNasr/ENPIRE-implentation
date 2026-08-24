# Project documentation

This directory holds the project notes, integration record, diagram export when
available, and benchmark run table. Experiment results are reported honestly,
including small or null effects.

The gated D1 scientific-baseline work is specified in:

- `baseline_protocol.md` — hypothesis, conditions, evaluation, decision, and
  compute contract;
- `experiment_matrix.md` — exact controlled comparison and unresolved inputs;
- `execution_checklist.md` — sequential implementation and evidence gates.
- `d1-infrastructure.md` — Stage-1 profiles, dry-run/paid gates, provenance,
  resource monitoring, and known verification boundary.
- `stage2-environment-audit.md` — pinned-source findings, corrected launch
  boundaries, and the remaining live-pod gate.
- `stage5b-resource-probe.md` — failed A10/H100 paths, viable L40S batching,
  Reference-A result, cost, and the degenerate-baseline decision.
- `stage5c-500-checkpoint.md` — revised 500-step checkpoint, fixed-set
  Reference-A result, cost/resource evidence, and checkpoint-selection gate.
- `stage5d-control.md` — trained Control-B objective, upstream warm-up
  contract, calibration boundary, same-instance Stage-6 continuation, resume
  limitation, and budget gate.
- `stage6-readiness.md` — Candidate-C scientific-diff, scratch initialization,
  preserved-input, dry-run, and current budget-authorization audit.
- `stage6-result.md` — completed Candidate-C execution, fixed-evaluation
  result, resume-counter validity failure, artifact hashes, and the formal
  `INCONCLUSIVE` decision.
- `local-artifact-backup.md` — progressive local weight/evidence download and
  hash gates required before any workspace termination.
