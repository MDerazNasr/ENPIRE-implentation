# Agent Experiment Readiness

## Current result

The Stage-1 development baseline is complete. The frozen selector chose the
2,000-step seed-2026 actor at `125/256` development successes (`48.83%`). The
selected checkpoint is already staged on the `enpire-workspace` Modal volume
and independently hash-verified as
`4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146`.

This closes E1 for protected-operator development use. It does not convert E1
into independent final-set evidence and does not authorize E2 or promotion.

## Prepared first agent pilot

The first agent-facing experiment is a configuration-only evolutionary pilot:

- one supervisor proposes three isolated children per generation;
- two generations are preregistered;
- each child may change at most one of `warmup_bc_weight` or
  `online_bc_weight`, within the frozen bounds;
- all assigned children finish or consume their slot before selection;
- the evaluator, not the agent, supplies the development score; and
- deterministic score, delta, cost, time, and lexical tie-breaking selects the
  next parent.

The immutable preregistration is
[`agent-config-pilot-preregistration-v1.json`](../../results/agent-supervisor/g0/agent-config-pilot-preregistration-v1.json).
The existing M7 scheduler, isolated Git worktrees, structured provider
boundary, F1 Modal RPC, and F2 matched-runtime rehearsal cover the control
plane. No arbitrary shell command, evaluator edit, final-reset access, or
agent-selected winner is permitted.

## Exact activation boundary

The repository is prepared through baseline selection and pilot
preregistration. Starting paid agent or GPU work still requires a separate
activation receipt that fixes:

1. the provider model and maximum LLM cost;
2. the Stage-2 steps, seeds, per-run timeout, and aggregate GPU ceiling;
3. the fixed scientific worker package for the selected actor; and
4. whether the run is an engineering pilot or an independently controlled E2
   study.

An engineering pilot may use development resets only. A scientific E2 or E4
claim additionally requires independent evaluator custody and the approved
matched paired-seed pack. Credentials must be injected at execution time and
must never be committed to this repository.

## Evidence

- Four-shard aggregate: `125/256`, payload fingerprint
  `500511a909be4809c0f04d1a23e9c00d547a82c58b113590ea12f137b6389e3f`.
- Frozen selection: step `2000`, selection fingerprint
  `7f43d9b7d9fbcafab995e926d0a9947ec8d2a260b960cbe45645499c544a6bcb`.
- D1 cumulative runtime-cost estimate: `$12.7449`; provider billing remains
  pending verification.
- No final reset, E2, agent campaign, retry, or promotion was authorized by
  these records.
