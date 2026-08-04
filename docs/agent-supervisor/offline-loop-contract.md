# Milestone 4 Offline Loop Contract

Milestone 4 proves that the supervisor components can form one complete loop
without claiming an RL result. Every worker metric is a deterministic fixture.
Every generated report states **SYNTHETIC OFFLINE DEMONSTRATION — NOT RESEARCH
EVIDENCE**.

## End-to-end path

1. The M2 attempt controller receives a bounded context and accepts at most one
   initial proposal plus one repair.
2. The M3 Git manager independently validates the accepted proposal, creates a
   hypothesis branch/worktree from the exact incumbent, runs trusted checks,
   and commits the candidate without moving the stable branch.
3. The M4 coordinator creates one immutable `RunContract` per approved seed.
   It binds campaign, arm, parent/candidate/RLinf commits, config and command
   hashes, seed, reset set, evaluator version, and resource caps.
4. A provider-neutral worker returns a `WorkerSnapshot`. The offline worker is
   synchronous and deterministic, but duplicate prepare/launch/fetch messages
   return the same state and evidence.
5. Only strict `TrialEvidence` reaches the evaluator. Worker prose or success
   claims are not an evaluator input.
6. `OfflineD1Evaluator` applies the existing D1 rule to matched control and
   candidate seeds. Missing or incompatible evidence is inconclusive; failed
   evidence is failed.
7. `ArmIncumbentStore` atomically moves only the named arm, and only when the
   versioned `DecisionRecord` is `KEEP`. No candidate is merged into stable.
8. Trial ledgers terminate as kept, reverted, inconclusive, or failed, and the
   report writer emits JSON, CSV, Markdown, and static HTML.

## Trust boundaries

- The agent proposes; it never evaluates or promotes itself.
- The worker executes an exact contract; it cannot change evaluator inputs.
- The evaluator consumes hashes and metrics, not proposal rationale.
- The incumbent store is per-arm, locked, atomic, and decision-idempotent.
- Candidate branches are retained as evidence; stable `HEAD` is unchanged.
- The base VLA, canonical RLinf, simulator/reset definitions, evaluator,
  budgets, orchestration, and reporting remain outside edit scope.

## Actor-objective overlay

`supervisor/objectives/actor_objective.py` contains the narrowly editable
function. `ActorObjectiveAdapter` is the harness-owned boundary. Its default is
checked against a separately defined reference for scalar values, NumPy tensor
shape/dtype behavior, and exact forward-mode derivatives. This proves the
overlay contract before RLinf is available; it does not prove PyTorch/JAX
autograd integration. M6 must wire the overlay into the pinned RLT actor update
and repeat finite-loss/gradient checks in the real framework.

## Demonstration

From the repository root:

```bash
demo_dir="$(mktemp -d /tmp/enpire-m4-demo.XXXXXX)"
python3 scripts/run_m4_offline_demo.py --output "$demo_dir"
```

The demonstration deliberately sends one invalid out-of-bounds configuration,
records its rejection, accepts one repaired proposal, builds a candidate in an
isolated worktree, executes three synthetic seeds, produces a deterministic
`KEEP`, verifies stable `HEAD` did not move, and writes the report bundle under
`$demo_dir/report`.

## Deferred to real integration

- D1 Stage-7 evidence replay and equality check between legacy and adapter
  decisions;
- approval activation, dry-run/paid acknowledgement, and campaign budget
  accounting around actual launches;
- pinned RLinf command construction and W&B/artifact reconciliation;
- real actor-objective framework integration;
- SSH workers, leases, true concurrency, cancellation, and crash recovery;
- GPU utilization and research comparisons.
