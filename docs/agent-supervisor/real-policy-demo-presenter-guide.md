# Presenter Guide: Real Policy Improvement

Target length: 8–10 minutes. The page carries the result; the terminal is only
used to demonstrate that it was freshly produced.

## Before the meeting

1. Use the clean `feature/d2-agent-supervisor` worktree.
2. Run the demo once into a rehearsal directory.
3. Verify the bundle.
4. Open `public/presentation.html` and check it at the display resolution.
5. Keep that verified page open as the fallback.
6. For the live run, choose a new output directory so preflight does not reject
   an existing bundle.

## Spoken walkthrough

### 1. Frame the two systems — 45 seconds

> “D1 is the real RLT laboratory. This supervisor is the automated researcher
> around that laboratory. D1 is still being made reproducible, so today I will
> first show the same research loop improving a small real policy locally.”

### 2. Explain the task — 45 seconds

> “The dot is a tiny robot. It gets three moves to reach a target. A fixed base
> controller gets close, and a small residual policy learns corrections—similar
> in spirit to the correction layer we want around the larger policy.”

### 3. Explain the proposal — 60 seconds

> “The baseline learner barely explores, so it cannot discover strong
> corrections. The recorded coding-agent proposal changes one permitted setting:
> exploration from 0.01 to 0.35. It cannot change the task, scorer, budget, base
> model, or any unrelated file.”

Explicitly add:

> “The proposal is recorded for meeting reliability; I am not claiming a live
> Claude call happened in this run.”

### 4. Run it — 60 seconds

Run:

```bash
python3 scripts/run_real_policy_demo.py \
  --output /tmp/enpire-real-policy-demo-live
```

Point out the final terminal fields:

- `decision: keep`;
- control and candidate mean success;
- paired improvement;
- six concurrent workers;
- `external_calls: []`; and
- `rlt_claim_permitted: false`.

### 5. Show the page — 3 minutes

Open the generated `public/presentation.html`.

> “On the exact same starts and targets, the control policies average roughly
> twelve percent success, while the candidate reaches every target in this
> frozen toy evaluation. The trajectories make the change visible.”

Then point to `KEEP`:

> “The coding agent did not award itself this result. The independent evaluator
> compared all three paired seeds using the rule we froze in advance.”

Move to “What just happened”:

> “The idea was checked, isolated in Git, trained by independent workers,
> evaluated, and recorded. Stable code never moved.”

### 6. State the boundary — 60 seconds

> “This proves that our supervisor can improve a real small model end to end. It
> does not prove RLT or π0.5 improved. D1 is what turns this system demonstration
> into the robotics experiment.”

### 7. Connect D1 — 45 seconds

> “Once D1 produces a non-degenerate reproducible baseline, its launcher and
> evidence replace this toy worker. The proposal, safety, branch, worker,
> evaluator, and reporting boundaries remain the same.”

## Likely questions

### “Is the improvement real?”

Yes for this toy task. Real policies were trained and evaluated. It is not a
synthetic score, but its scientific scope is deliberately small.

### “Why does it reach 100%?”

The task is intentionally simple and the baseline is intentionally
under-exploring so the improvement is visual and reliable. The value is not the
difficulty of the toy benchmark; it is the verified end-to-end connection.

### “Did Claude generate the idea live?”

No. It is a recorded coding-agent proposal used to make the meeting reliable.
The provider seam already exists, but live provider quality is a different
claim and can fail for reasons unrelated to the supervisor.

### “Could you make any model look better this way?”

The toy task was selected to be improvable, but the candidate still has to use
the same seeds, resets, compute, and evaluator. All evidence and the exact
change are preserved. No conclusion is extended beyond this task.

### “What remains?”

Complete D1’s training run and evidence pack, bind its actual actor-loss seam,
then run the preregistered control versus coding-agent experiments on real RLT.

## Failure fallback

If the live command fails, do not improvise or delete evidence. Open the
verified rehearsal page and say:

> “This is the bundle generated during rehearsal from the same clean commit. Its
> 14 artifacts can be independently rehashed. I will preserve today’s failed run
> as failure evidence rather than hiding it.”
