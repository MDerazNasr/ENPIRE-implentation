# Milestone 4 Verification Report

Date: 2026-08-04

Branch: `feature/d2-agent-supervisor`

Mode: offline synthetic fixtures only

## Outcome

M4 is complete. The coding-agent supervisor now has a demonstrable end-to-end
offline path from bounded proposal and isolated candidate creation through
worker evidence, deterministic evaluation, per-arm keep/revert state, ledger
termination, and static reports. No paid model, GPU, SSH host, W&B service, or
RLinf training process was called.

## Implemented

- provider-neutral immutable run contracts and a deterministic fake worker;
- idempotent duplicate worker completion/evidence retrieval;
- worker-loss and failed-evidence behavior that cannot promote a candidate;
- frozen D1 evaluator adapter with strict seed/provenance checking;
- locked, atomic, per-arm incumbent pointers and idempotent decisions;
- offline coordinator composing M2 proposal, M3 Git, M1 ledger, worker,
  evaluator, and incumbent layers;
- project-owned actor-objective overlay and default forward/gradient fixtures;
- canonical JSON, CSV, Markdown, and HTML reports;
- one-command demo with an invalid proposal, bounded repair, three synthetic
  seed trials, `KEEP`, and stable-branch proof.

## Verification evidence

| Check | Result |
| --- | --- |
| Prior M1–M3 suite before M4 | 111 passed, 66 subtests passed |
| Complete repository suite after M4 | 132 passed, 69 subtests passed |
| Offline demo terminal status | `decided` |
| Offline demo decision | `keep` |
| Invalid attempts retained | 1 |
| Synthetic seed evidence records | 3 |
| Stable branch moved | no |
| Report artifacts | JSON, CSV, Markdown, HTML |

The exact final test count is recorded after the final verification command; if
the suite changes during documentation cleanup, this table must be updated to
the observed value before commit.

## Tests added

- worker contract, lifecycle, idempotency, cancellation, failure, and loss;
- evaluator keep/revert/inconclusive/failed and provenance mismatch matrix;
- agent-prose independence;
- per-arm isolation, decision replay, conflict, and restart validation;
- scalar/array/dual-number actor-objective equivalence;
- coordinator keep, revert, loss, stable-branch, ledger, and report behavior;
- one-command demo repair, decision, stable-head, and artifact verification.

## Honest limitations

- Metrics are synthetic fixtures and are not evidence that RLT improved.
- The objective overlay is not yet wired to RLinf/PyTorch/JAX training.
- Workers run synchronously in process; multi-GPU/SSH execution remains M7.
- Worker and decision messages are idempotent, but full coordinator crash/lease
  recovery remains M7.
- W&B reconciliation, GPU utilization, paid-execution gates, and live budget
  cancellation remain M5/M7/M8.
- D1 evidence replay is still the mandatory gate before M5.

## Next gate

Do not begin M5 until the reproducible D1 Stage-7 evidence pack exists. At that
gate, bind the exact D1 commit and artifacts, normalize its evidence, replay the
adapter, and require equivalent decisions before any live configuration-only
agent trial.

After M4, five numbered milestones remain (M5–M9), plus the D1 integration
gate. The prior estimate for that remaining work is 49–74 hours, subject to D1
availability and GPU/SSH integration findings.
