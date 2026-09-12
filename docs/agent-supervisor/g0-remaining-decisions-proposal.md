# G0 Remaining Decisions — Freeze Candidate

Status: **accepted 2026-09-11 for locally resolvable design fields; still
non-authorizing and incomplete pending production identity/custody and human
acceptance of the runtime/cost proposal**

Obsidian task: `MI5T8`

This document records the accepted locally resolvable G0 choices. It does not
fill identities that require the pinned simulator,
private assets, a production evaluator deployment, current provider pricing,
or an approval window. It authorizes no evaluation, GPU, provider, model
egress, campaign activation, selection, or promotion.

## Audit finding

The earlier proposed Stage-1 grid `500, 1000, 2000, 4000, 8000` is incompatible
with `configs/d1/stage1_scientific.yaml`, which freezes
`actor.optim.total_training_steps=2000`. The candidate grid below stays inside
that boundary. Extending training beyond 2,000 steps would be a separate
scientific amendment, not a checkpoint-selection decision.

The current `agent/d1_rules.py` rule is historical D1 behavior. Below ceiling,
it maps every valid result that does not meet `KEEP` to `REVERT`; at or above
90% Control it switches to an episode-length rule. G0 should not silently
inherit those semantics. The proposed rule below separates evidence of harm
from absence of evidence and leaves ceiling handling inconclusive.

## Recommended E1 freeze

| Decision | Freeze candidate |
|---|---|
| Training lineage | One uninterrupted Stage-1 seed-2026 run |
| Checkpoint grid | `[250, 500, 1000, 2000]` optimizer steps |
| Checkpoint cadence | 250 steps; retain the four grid checkpoints |
| Evaluation set | Development reset artifact only, exactly once per grid checkpoint |
| Non-degeneracy | `eval/success_once >= 0.05` and all 256 outcomes valid |
| Selection | Highest development success; exact tie selects earlier checkpoint |
| Plateau diagnostic | First two consecutive grid improvements each `< 0.02`; diagnostic only |
| No qualifying checkpoint | E1 `INCONCLUSIVE`; do not enter E2 |
| Stage-1 seed follow-up | Out of scope for first E2, already accepted |

Selection uses the complete fixed grid, not opportunistic stopping. This avoids
changing exposure after seeing intermediate outcomes. Checkpoints that fail to
load, lack ancestry, or have incomplete evaluation remain retained but cannot
be selected.

## Recommended first E2 freeze

| Decision | Freeze candidate |
|---|---|
| Conditions | Control `7.0/2.5`; Candidate `5.6/2.0` warm-up/online BC |
| Strong-reduction arm | Omit from the first confirmatory comparison |
| Training seeds | `[2026, 2027, 2028]`, matched by condition |
| Required Stage-2 runs | Six |
| Initial actor | Exact single E1-selected actor for all six runs |
| Horizon | 120 runner steps |
| Validation/checkpoint | Step 120 |
| Q weights | Warm-up `0.05`, online `0.45` |
| Runtime mechanics | Preserve all remaining fields in the accepted F2 matched profile |
| Scheduling | Concurrent or sequential permitted only with identical immutable runtime contracts |

This tests only the scheduled-BC hypothesis. Adding `4.2/1.5` later requires a
new multiplicity-aware exploratory protocol and cannot retroactively join this
comparison.

## Recommended deterministic decision rule

The primary endpoint is Candidate minus Control `eval/success_once`, paired by
training seed. Compute the mean of the three paired seed deltas and a two-sided
95% Student-t interval using `df=2` (`t=4.303`). Do not substitute an unpaired
analysis or pool 768 episodes as independent training replicates.

| Result | Rule |
|---|---|
| `KEEP` | mean delta `>= 0.05` and interval lower bound `> 0` |
| `REVERT` | interval upper bound `< 0` |
| `INCONCLUSIVE` | every other valid result |

Any missing seed, invalid/non-finite metric, reset mismatch, identity drift,
failed run, unresolved duplicate risk, or incomplete evidence is
`INCONCLUSIVE`. A Control mean at or above 90% is also `INCONCLUSIVE` under
this first success-only protocol; episode length is descriptive and cannot
rescue a `KEEP`. Secondary metrics never break ties or control promotion.

This rule is implemented separately in `supervisor/g0_decision.py` and covered
by adversarial boundary tests. The historical D1 rule remains unchanged and
available for replay of its original evidence.

## Recommended failure and retention policy

- One original attempt per run identity. At most one superseding retry, only
  for a preregistered infrastructure/transport failure that occurred before a
  usable policy outcome.
- Numerical failure, invalid evidence, timeout after workload start, and
  scientific underperformance are not retryable by default.
- Unknown remote status remains unknown. A possible duplicate requires a new
  explicit authorization naming the duplicate risk and new run identity.
- Timeout or actual cost overrun terminates further dispatch while retaining
  the actual record; it never changes a result to success.
- Compact manifests, metrics, logs, costs, hashes, failures, and lineage remain
  indefinitely in Git. Large checkpoints/replay are retained until terminal
  reconciliation and the frozen retention decision; no private model enters
  Git.
- W&B or object storage may mirror evidence but is never authoritative; local
  hash-bound evaluator evidence is authoritative.

## Decisions that remain impossible to freeze locally

The following must stay `TBD` until their real inputs exist:

- exact task/simulator, dataset, model, norm-stat, Stage-1 actor, and runtime
  hashes;
- production evaluator source root, OS identity/immutable mount, environment
  hash, ledger destination, and independently controlled anchor;
- measured E1/E2 timeout and storage envelopes;
- provider-specific price, worst-case cost, concurrency, billing lifecycle,
  and approval window; and
- reviewer identity, timestamp, disposition, and final protocol fingerprint.

No price or capacity value from the F2 engineering rehearsal should be copied
into G0 without a fresh, matched, read-only qualification.

The current machine-readable blocker inventory is generated by
`scripts/run_g0_readiness_gate.py` and checked in as the latest versioned
`results/agent-supervisor/g0/g0-readiness-*.json` receipt. The gate deliberately has no
ready transition: even if files appear at the expected paths, it remains
`blocked_pending_ready_transition_review` until their schemas and custody are
separately reviewed and implemented.

## Acceptance sequence

1. [Completed engineering gate] Export both pinned reset sets twice and confirm
   all 512 resets without policy evaluation.
2. [Local rehearsal completed; production pending] Deploy and independently
   verify the evaluator isolation/ledger boundary.
3. Measure runtime only through a separately authorized non-scientific probe if
   existing evidence cannot safely establish the envelope.
4. Fill every required identity, cost, and custody field; fingerprint G0.
5. Request a distinct paid scientific authorization. G0 acceptance alone never
   launches work.
