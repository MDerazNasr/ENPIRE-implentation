# Ludvig Demo Runbook

Target duration: 10–15 minutes. Prepare the bundle before the meeting and keep
the verified static presentation open as the fallback.

## Before the meeting

From the clean `feature/d2-agent-supervisor` worktree:

```bash
git status --short
python3 -m pytest -q
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-ludvig-demo
python3 scripts/verify_m9_bundle.py \
  /tmp/enpire-m9-ludvig-demo
```

`git status --short` must print nothing. The demo should finish with status
`complete`, `scientific_claim_permitted: false`, `external_calls: []`, and
`stable_head_unchanged: true`.

Serve the static page locally if the browser does not render linked SVG files
from disk:

```bash
python3 -m http.server 8765 \
  --directory /tmp/enpire-m9-ludvig-demo
```

Open `http://127.0.0.1:8765/presentation.html`. This server is local and makes
no internet request.

If a reviewed D1 Stage-7 pack exists, prepare a separate replay bundle:

```bash
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-d1-replay \
  --d1-repository /path/to/d1-worktree
```

Do not use `--require-d1-ready` for the live meeting unless a pre-meeting check
already passed. Do not launch a paid/GPU run as part of this runbook.

## Talk track

### 0:00–2:00 — Problem and scope

- We want an agent to supervise the outer RLT improvement loop: inspect
  completed evidence, propose one bounded change, run, evaluate, and keep or
  revert.
- The agent does not control gradients, robot actions, resets, success labels,
  infrastructure, or promotion.
- The first target is deliberately RLT-specific; it is not a general paper
  implementation agent.

Show the architecture diagram in `presentation.html`.

### 2:00–5:00 — One bounded policy-improvement iteration

Show the M4 card and `components/m4/report/report.html`:

- one malformed/out-of-bounds proposal is retained;
- one structured repair becomes inert proposal data;
- the harness validates scope and creates an isolated candidate;
- fake worker evidence goes to the frozen D1 evaluator; and
- only that evaluator produces `KEEP`/`REVERT`; stable HEAD stays unchanged.

State explicitly that the numbers are fixtures testing authority boundaries.

### 5:00–8:00 — Parallel workers and recovery

Show the M7 card and `components/m7/m7-demo.json`:

- two independent worker threads overlap;
- one worker is lost;
- the scheduler creates a new lease for a replacement worker;
- the late old completion is rejected as stale; and
- complete evidence is evaluated centrally rather than by a worker.

This demonstrates orchestration reliability, not GPU speedup.

### 8:00–11:00 — Frozen three-arm study

Show `components/m8/report/study-report.html`:

- fixed-rule config, Claude config, and Claude objective-code arms;
- three discovery opportunities per arm with equal worker caps;
- invalid and failed work remain visible and consume slots;
- each arm advances only from its own verified incumbent; and
- the mechanically selected commit receives exact paired confirmation.

The fixture contains nine discovery records, three confirmations, two invalid
proposals, one failed candidate, and 30 represented seed runs.

### 11:00–13:00 — Evidence and honesty

Show `artifact-manifest.json` and the verifier output:

- every curated displayed artifact has a role, SHA-256, and byte count;
- the final report is generated from retained records; and
- the bundle permits no scientific claim.

If D1 replay is available, show its gate status. If it is blocked, say exactly
that the control plane is complete while real policy evidence is pending.

### 13:00–15:00 — Next experiment

- Freeze the ready D1 baseline and exact RLinf/objective attachment.
- Activate the already preregistered M8 study.
- Execute nine discovery candidate experiments, then three paired
  confirmations, under approved compute.
- Compare policy outcome, systems reliability/cost, and agent efficiency
  without changing metrics after results.

## Fallback plan

If the unified command fails during the meeting:

1. stop; do not improvise a paid or external run;
2. run `verify_m9_bundle.py` on the pre-generated bundle;
3. use `presentation.html` and its linked component reports;
4. show the recorded failure honestly if it produced one; and
5. continue with the same talk track.

If D1 is unavailable, use the offline bundle. If a browser fails, open
`demo-report.md`. If the architecture image fails, the report still contains
the complete textual boundary.

## Expected questions

**Is the coding agent supervising RL?** Yes, at the experiment/policy-
improvement level between complete runs—not inside the optimizer or robot
control loop.

**Why not give Claude Code the repository and GPUs directly?** Proposal,
execution, evaluation, and promotion are separate authorities. This reduces
scope drift and makes negative results auditable.

**What is real today?** The schemas, enforcement, Git isolation, subprocess
boundary, leases/recovery, evaluator, study protocol, and reports. The final
meeting metrics are synthetic fixtures.

**What needs D1?** Real RLT execution, exact actor-loss attachment, real costs/
utilization, trustworthy keep/revert evidence, and arm-performance conclusions.

**Why three seeds?** They implement the frozen D1 paired engineering rule. They
do not justify broad model-superiority claims.
