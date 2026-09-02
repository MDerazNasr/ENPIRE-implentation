# Real CPU Policy-Improvement Demo

Status: implemented as a meeting-safe extension to M9.

## One-sentence explanation

The supervisor takes one bounded, recorded coding-agent idea, creates an
isolated candidate, trains six real CPU residual policies, independently
compares three paired control/candidate seeds, and keeps the candidate because
measured success improves on the public toy task.

This is real model training. It is not RLinf/RLT, π0.5, ManiSkill, or physical
robot evidence.

## Why this demo exists

The M9 demonstration proves the complete control plane using deterministic
fixtures. That is strong engineering evidence but visually abstract. This demo
adds one small real learning job so a general audience can see what “propose,
isolate, train, evaluate, keep” means.

The task is a two-dimensional point reacher. A fixed base controller moves
toward a target and a three-parameter residual policy learns small corrections
from reward. The control configuration explores too narrowly. The recorded
proposal changes only `training.exploration_std` from `0.01` to `0.35`; all
other training and evaluation settings stay fixed.

## What actually runs

1. The runner requires a clean supervisor Git worktree and a new output path.
2. It creates a small disposable stable Git repository for the toy policy.
3. The existing structured proposal and enforcement contracts check the one
   allowlisted setting, one JSON path, budget, and trusted config check.
4. The existing Git experiment manager creates and commits an isolated
   hypothesis worktree without moving stable HEAD.
5. Six fixed subprocess workers run concurrently: control and candidate for
   seeds 101, 202, and 303.
6. Every worker really trains a residual policy and evaluates 256 shared
   unseen resets on the CPU.
7. Results are normalized into the existing `TrialEvidence` schema.
8. The existing frozen D1 evaluator applies its paired-seed keep rule.
9. The runner writes the visual presentation, complete run evidence, decision,
   CSV, Markdown report, trajectory SVG, and SHA-256 artifact manifest.

No GPU, network, W&B, SSH, provider, or paid service is contacted.

## Run it

From the clean `feature/d2-agent-supervisor` worktree:

```bash
python3 scripts/run_real_policy_demo.py \
  --output /tmp/enpire-real-policy-demo
```

The output directory must be absent or empty. Use a different output name for
another rehearsal.

Verify all curated evidence:

```bash
python3 scripts/verify_real_policy_demo.py \
  /tmp/enpire-real-policy-demo
```

Open the meeting page on macOS:

```bash
open /tmp/enpire-real-policy-demo/public/presentation.html
```

The runner normally completes in a few seconds on a laptop. Do not promise an
exact runtime or exact success percentage before running on the presentation
machine. The checked-in acceptance threshold requires a large, consistent
paired improvement and a `KEEP` decision.

## Output map

- `public/presentation.html`: primary audience view;
- `public/trajectory-comparison.svg`: shared before/after resets;
- `public/report.md`: concise written interpretation;
- `public/real-policy-demo.json`: complete normalized record;
- `public/proposal.json`: recorded proposal and source disclosure;
- `public/campaign.json`: frozen question, scope, seeds, resets, and budgets;
- `public/decision.json`: independent evaluator result;
- `public/trials.csv`: six-run comparison table;
- `public/runs/*.json`: real policies, traces, metrics, and evidence; and
- `artifact-manifest.json`: raw SHA-256 and byte count for 14 curated files.

The `runtime/` directory contains disposable Git/worktree detail and is not
part of the public evidence manifest.

## Exact claim boundary

The demo supports these statements:

- six real residual policies were trained on the CPU;
- the candidate improved this frozen toy task on three paired seeds;
- scope enforcement, Git isolation, workers, evidence normalization, the
  evaluator, and reporting compose around a real learning job; and
- the stable supervisor repository remained unchanged.

It does not support these statements:

- RLinf/RLT, π0.5, ManiSkill, or a real robot improved;
- the same setting will improve D1;
- a live LLM produced the proposal during the meeting; or
- coding agents generally outperform fixed search or human researchers.

## Relationship to D1

The toy worker occupies the same logical position that the D1 worker will
occupy. Replacing the toy runner with D1 should not change who is allowed to
propose, validate, execute, evaluate, or promote. D1 remains necessary for the
project’s real RLT conclusion.
