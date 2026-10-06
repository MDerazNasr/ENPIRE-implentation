# Reproducible Agentic Policy Improvement for VLA Models

This repository is a research implementation of an ENPIRE-inspired loop for
improving a vision-language-action (VLA) policy. It combines reproducible
RLinf training with a constrained coding-agent supervisor that can propose
changes, run isolated trials, and compare them using a protected evaluator.

The project is currently an engineering and preliminary-development study. It
does **not** yet establish that an agent improves robotic policy performance.

## Research question

Can a coding agent iteratively improve a robotic policy while the surrounding
system keeps training, evaluation, experiment selection, cost, and provenance
reproducible and outside the agent's control?

The intended loop is:

```text
frozen parent policy
        ↓
agent proposes bounded changes
        ↓
isolated training branches on independent workers
        ↓
protected fixed-set evaluation
        ↓
programmatic selection from measured results
        ↓
next experiment generation
```

The agent may propose changes. It cannot approve paid runs, alter evaluation
inputs, assign its own score, or promote a result.

## What has been built

- A pinned RLinf/OpenPI training and evaluation path for ManiSkill RLT.
- Fixed reset sets and a deterministic `eval/success_once` endpoint.
- Hash-bound manifests for code, configurations, checkpoints, logs, metrics,
  costs, and run lineage.
- Fail-closed paid-run approvals, retry limits, and budget controls.
- A coding-agent supervisor with structured proposals, source restrictions,
  isolated Git worktrees, worker scheduling, and deterministic decisions.
- Local, SSH, and Modal worker paths with restart and stale-result handling.
- Reproducible synthetic and CPU-policy demonstrations of the orchestration
  layer, explicitly separated from scientific VLA evidence.

The completed baseline history is on `main`. The latest integrated supervisor
and evaluator work is maintained on
[`integration/d1-d2-agentic-harness`](https://github.com/MDerazNasr/ENPIRE-implentation/tree/integration/d1-d2-agentic-harness).

## Current baseline results

One seed-2026 Stage-1 run completed all 2,000 planned optimizer steps. Four
checkpoints were retained and evaluated on the same 256 frozen development
trajectories with a 500-step episode horizon.

| Checkpoint | Successful trials | Development success | Mean episode length | Status |
| ---: | ---: | ---: | ---: | --- |
| 250 | 0 / 256 | 0.00% | 500.0 | Complete |
| 500 | 23 / 256 | 8.98% | 462.54 | Complete |
| 1,000 | 108 / 256 | 42.19% | 323.32 | Complete |
| 2,000 | — | — | — | Incomplete: terminated after 5/16 rollout epochs |

These are development results from one training seed, not final-set results.
The 2,000-step attempt produced no aggregate metric, and its partial output is
not accepted. The completed curve shows substantial learning between steps 500
and 1,000 but cannot yet determine the best checkpoint on the frozen grid.

## Next experiment

1. Obtain a complete, valid 2,000-step checkpoint evaluation.
2. Select the highest-scoring checkpoint using the frozen mechanical rule.
3. Start matched agent-controlled experiments from that exact parent policy.
4. Run candidate approaches on isolated workers with identical evaluation.
5. Select winners from evaluator results, not agent-written claims.
6. Repeat across the preregistered paired seeds before making an improvement
   claim.

## Repository map

```text
agent/          Early transparent policy-improvement loop
configs/        Versioned training and evaluation configurations
docs/           Protocols, runbooks, research decisions, and result reports
scripts/        Reproducible launch, evaluation, and verification commands
tests/          Offline contract, safety, provenance, and integration tests
results/        Compact tracked receipts and evidence summaries
```

The active integration branch additionally contains `supervisor/`, its
agent-orchestration documentation, and the latest evaluator receipts.

Start with:

- [`docs/reproducible-agentic-enpire-plan.md`](docs/reproducible-agentic-enpire-plan.md)
- [`docs/baseline_protocol.md`](docs/baseline_protocol.md)
- [Scientific experiment test program](https://github.com/MDerazNasr/ENPIRE-implentation/blob/integration/d1-d2-agentic-harness/docs/agent-supervisor/g0-scientific-experiment-test-program.md)
- [`docs/research-meeting-transcript-2026-09-02.md`](docs/research-meeting-transcript-2026-09-02.md)

Some supervisor documents exist only on the active integration branch until
that work passes its remaining research gates.

## Verification

The core test suite is dependency-free:

```bash
python3 -m unittest discover -s tests -v
```

The repository also includes a generic Modal GPU workspace launcher:

```bash
python3 -m venv .venv
.venv/bin/pip install modal
.venv/bin/modal setup
.venv/bin/modal run modal_app.py
```

GPU execution requires separately provisioned model, dataset, checkpoint, and
simulator assets. Paid or scientific execution is never implied by running the
offline tests.

## Scientific boundaries

- Current checkpoint scores are preliminary development evidence.
- The incomplete 2,000-step run is not a result.
- Synthetic supervisor demos validate orchestration, not VLA improvement.
- A single seed cannot establish a reliable treatment effect.
- No final-reset, real-robot, or agent-superiority claim is currently made.
- Negative, failed, and inconclusive runs are retained rather than discarded.

The goal is not merely to obtain a higher number. It is to produce an
improvement whose code, inputs, evaluation, cost, and lineage can all be
independently checked.
