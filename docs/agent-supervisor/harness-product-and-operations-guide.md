# ENPIRE Harness Product and Operations Guide

Status: **control plane implemented; live F1/F2 engineering acceptance passed;
scientific study not yet authorized**

Obsidian task: `MI5T8`

This is the canonical entry point for understanding and operating the
reproducible ENPIRE-style agentic harness. Detailed contracts and dated
evidence remain authoritative; this guide connects them into one product view.

## 1. What the product is

The harness is a bounded outer-loop research system for improving RLinf/RLT
policies. A short-lived coding agent proposes one constrained hypothesis
between complete training runs. Trusted harness code validates and isolates the
change, schedules immutable runs, collects evidence, evaluates it with a fixed
rule, and records whether the arm should `KEEP`, `REVERT`, or remain
`INCONCLUSIVE`.

The agent is not in the optimizer, gradient, simulator, reset, robot-action,
scoring, approval, or promotion loop. It is an untrusted proposal source.

The current product supports:

- configuration-only proposals within typed allowlisted bounds;
- one narrowly defined actor-objective code surface;
- independent Git branches and worktrees per hypothesis;
- local, fake, SSH, and fixed Modal worker interfaces;
- durable scheduling, leases, recovery, retry, and cancellation;
- immutable manifests, metrics, costs, logs, and artifact hashes;
- deterministic evidence-based decisions and per-arm incumbents;
- isolated multi-arm studies with selection and confirmation; and
- JSON, CSV, Markdown, HTML, diagram, and artifact-manifest delivery.

It is RLT-specific today. It is not a general autonomous paper-implementation
system and does not yet authorize real-robot execution.

## 2. System map

```text
reviewed campaign + budget + baseline
                  |
                  v
         bounded evidence context
                  |
                  v
       untrusted proposal provider
                  |
                  v
 schema/scope/source/behavior validation
                  |
                  v
 isolated branch + worktree + candidate commit
                  |
                  v
 immutable run contracts -> scheduler -> independent workers
                  |                         |
                  |                         v
                  +---------------- immutable evidence
                                            |
                                            v
                                independent evaluator
                                  /       |        \
                               KEEP    REVERT   INCONCLUSIVE
                                  \       |        /
                                   per-arm ledger
                                         |
                                         v
                           deterministic study/report bundle
```

## 3. Component inventory

| Responsibility | Primary implementation |
|---|---|
| Canonical JSON and hashes | `supervisor/canonical.py` |
| Campaign, approval, evidence contracts | `supervisor/contracts.py` |
| Campaign/trial state machines | `supervisor/state.py` |
| Append-only hash-chained records | `supervisor/ledger.py` |
| Decimal budget accounting | `supervisor/budget.py` |
| Curated bounded agent context | `supervisor/context.py` |
| Structured proposals | `supervisor/proposals.py` |
| Provider adapters and bounded repair | `supervisor/providers.py`, `supervisor/attempts.py` |
| Static and scope enforcement | `supervisor/enforcement.py` |
| Candidate Git isolation | `supervisor/git_manager.py` |
| Coordinator lifecycle | `supervisor/coordinator.py` |
| Worker contract and fake worker | `supervisor/workers.py` |
| Durable multi-worker scheduling | `supervisor/scheduler.py` |
| Fixed SSH transport | `supervisor/ssh_worker.py` |
| Fixed Modal RPC transport | `supervisor/modal_worker_rpc.py` |
| D1 subprocess execution | `supervisor/d1_backend.py` |
| Objective ABI and behavioral proof | `supervisor/objective_validation.py` |
| Live objective attachment | `agent/rlt_objective_attachment.py`, `sitecustomize.py` |
| Resume schedule/RNG sidecar | `agent/rlt_resume_state.py` |
| Independent decisions | `supervisor/evaluation.py` |
| D1 pack construction and gate | `supervisor/d1_pack_builder.py`, `supervisor/d1_gate.py` |
| Three-arm study | `supervisor/study.py` |
| Reports and final delivery | `supervisor/reporting.py`, `supervisor/study_reporting.py`, `supervisor/delivery.py` |

Strict Python loaders are normative where prose and implementation disagree.
The approved scientific protocol and immutable evidence outrank convenience
behavior or historical demo documentation.

## 4. Roles and authority

### Human approver

Reviews the protocol and grants an exact, time-bound execution envelope. A
replacement host, changed artifact, larger budget, changed destination, or new
scientific scope requires new authority.

### Proposal agent

Receives compact evidence and returns one structured hypothesis, expected
effect, falsification condition, change, tests, and cost estimate. It has no
direct tools in the scientific proposal session and receives at most one
bounded repair opportunity.

### Coordinator and scheduler

Own lifecycle transitions, scope enforcement, reservations, leases, worker
assignment, cancellation, recovery, and reconciliation. They cannot invent a
scientific score.

### Worker

Executes the exact harness-owned `RunContract`. An agent cannot inject a shell
command, endpoint, artifact namespace, or evaluator. One candidate per worker
is the initial scientific model.

### Evaluator

Consumes normalized, identity-bound evidence and owns the official decision.
Agent prose and candidate-local tests cannot affect it. Missing or mismatched
evidence fails closed.

## 5. Lifecycle and invariants

Campaign lifecycle:

```text
draft -> validated -> approved -> active -> completed
```

Trial lifecycle:

```text
proposing -> proposal_validated -> queued -> running -> evaluated
                                                    -> kept
                                                    -> reverted
                                                    -> inconclusive
                                                    -> failed/cancelled
```

Core invariants:

- Stable project HEAD never moves automatically.
- `KEEP` advances only the named arm's incumbent pointer.
- Every candidate names and verifies its exact parent.
- Cross-arm candidate substitution is rejected.
- Invalid and failed proposals consume their allocated slot.
- Duplicate or stale worker completion cannot overwrite accepted evidence.
- Actual overrun is recorded and blocks later work; it is never hidden.
- Paid launch requires campaign approval and backend paid acknowledgement.
- Completed evidence is immutable; corrections are new superseding records.

## 6. Edit modes

### Configuration mode

Campaign rules enumerate individual fields, types, and bounds. The enforcer
materializes only those values and proves all other scientific settings remain
unchanged. This is the first live agent-value mode.

### Actor-objective mode

The agent may edit only the project-owned actor-objective function. The
surrounding adapter is frozen. Static policy rejects unsafe syntax/imports and
an isolated real-tensor test must demonstrate finite, intentional value and
gradient behavior. Canonical RLinf remains unmodified.

## 7. Local verification and demonstrations

Run commands from the repository root. Output directories must be outside the
repository so demos do not dirty the scientific worktree.

### Complete regression suite

```bash
python3 -m unittest discover -s tests -v
```

Current verified baseline: 296 tests and 142 subtests pass.

### Unified offline product demonstration

```bash
demo_dir="$(mktemp -d)/m9-demo"
python3 scripts/run_m9_ludvig_demo.py --output "$demo_dir"
python3 scripts/verify_m9_bundle.py "$demo_dir"
```

This exercises proposals, repair, candidate isolation, decisions, worker
concurrency/loss, a nine-slot three-arm study, confirmation, reporting, and
manifest verification. It is synthetic and permits no policy claim.

### Real CPU toy-policy demonstration

```bash
demo_dir="$(mktemp -d)/real-policy-demo"
python3 scripts/run_real_policy_demo.py --output "$demo_dir"
python3 scripts/verify_real_policy_demo.py "$demo_dir"
```

This trains and evaluates a real small policy and uses the real harness
boundaries. Its improvement applies only to the toy task, not RLinf/RLT.

### M8 study rehearsal

```bash
demo_dir="$(mktemp -d)/m8-demo"
python3 scripts/run_m8_study_demo.py --output "$demo_dir"
```

The fixture contains all nine discovery records, adverse outcomes,
deterministic selection, and independent confirmations.

## 8. D1 evidence pack and integration gate

The D1 pack is the bridge between the reproducible training laboratory and the
agentic supervisor. It binds seven required artifact roles, scientific
identities, decisions, Git containment, and evaluator replay.

Generate a readiness report without claiming publication:

```bash
python3 scripts/build_d1_evidence_pack.py \
  --repository /path/to/d1-repository
```

`--publish` may be used only after every strict source and evidence gate passes.
Audit a pack without modifying the D1 repository:

```bash
python3 scripts/check_d1_integration_gate.py \
  --d1-repository /path/to/d1-repository
```

Exit `0` means `ready`. Exit `2` means blocked or invalid; use the emitted
reasons rather than weakening the gate.

## 9. Operating a real campaign

There is intentionally no one-command scientific launch. A real campaign
progresses through reviewed gates:

1. Define question, arms, editable surface, seeds, reset sets, metrics,
   evaluator, confirmation rule, runtime, retention, and maximum budget.
2. Serialize and fingerprint the `CampaignSpec`.
3. Validate the clean baseline, D1 pack, commits, assets, and worker runtime.
4. Create a time-bound `ApprovalEnvelope` for the exact fingerprint.
5. Activate the campaign before requesting proposals or viewing results.
6. Build bounded context and request exactly one structured proposal per slot.
7. Validate schema, scope, source, behavior, lineage, and remaining budget.
8. Materialize the accepted change in an isolated branch/worktree and commit
   its exact tree.
9. Create immutable per-seed run contracts and reserve capacity/cost.
10. Dispatch to qualified workers; heartbeat and recover through durable state.
11. Fetch artifacts, verify digests, normalize evidence, and retain failures.
12. Run the independent evaluator and update only the permitted arm pointer.
13. Wait for every discovery slot before deterministic selection.
14. Freeze selected commits and run the paired hidden confirmation.
15. Generate and independently verify the report/artifact bundle.
16. Close the campaign, release workers, and record the terminal idle gate.

The examples under `examples/supervisor/` are schema fixtures, not approved
campaigns. The coordinator and study APIs are library contracts; a production
operator must not bypass them with ad hoc shell commands.

## 10. Workers, concurrency, and recovery

The scheduler filters workers by declared capabilities, reserves conservative
budgets, and assigns leases. Heartbeats renew authority. Expired/lost workers
requeue work; late results from revoked attempts are rejected. Coordinator
restart reconstructs the same state from the ledger and exact run contracts.

The initial research topology is one supervisor coordinating three independent
single-GPU workers. It tests three sibling hypotheses concurrently. It does not
split one candidate's training across three GPUs.

Cancellation revokes coordinator authority before transport cancellation.
Evidence fetched after completion is size-capped and digest-verified. SSH and
Modal clients expose fixed operations—not an agent-selected command surface.

## 11. Evidence and retention

### Tier 1 — tracked compact truth

Protocols, approvals without secrets, commits, hashes, manifests, normalized
metrics, costs, decisions, compact logs, and artifact indexes remain in Git.

### Tier 2 — approved artifact storage

Full checkpoints, replay buffers, videos, detailed telemetry, and long metric
series live in W&B or approved object/local storage with identifiers and
digests in Tier 1.

### Tier 3 — ephemeral material

Disposable worktrees, caches, partial downloads, and unnecessary intermediate
state may be removed only after terminal evidence and any required diagnostic
artifacts are preserved.

Never write API tokens, SSH keys, cookies, credentials, private transcripts,
or unrelated personal information to Git, reports, agent context, or Obsidian.

## 12. Current evidence-backed status

| Area | Status | Meaning |
|---|---|---|
| M0–M6 | Passed offline/live-attachment engineering gates | Contracts, proposal, enforcement, Git, coordinator, evaluator, and bounded objective behavior implemented |
| M7 | Passed synthetic distributed tests | Scheduling, recovery, stale-result rejection, and fixed SSH client implemented |
| M8–M9 | Passed synthetic study/delivery tests | Study and final reporting work; no agent-superiority claim |
| CPU toy policy | Passed real local demo | Real learning improvement on toy task only |
| D2 paid acceptance | Failed safely | Real remote launch boundary retained its failure evidence |
| F1 | Passed live Modal attempt 3 | Fixed worker RPC, GPU probe, recovery, cancellation, and artifact transfer accepted |
| F2 | Passed H100 PCIe attempt 7 | Matched Control/Candidate-shaped execution and strict resume contract accepted |
| G0 | Draft | Scientific experiment test program documented; no GPU authority |
| G1–G3 | Not complete | Matched paired-seed scientific baseline and conclusion remain |
| H | Blocked | Canonical D1 gate awaits complete matched evidence |
| I–L | Not activated | Live agent study, confirmation, and final research analysis remain |

F2's authoritative terminal record is
`results/runtime-qualification/f2/h100-pcie-attempt-7/terminal.json`. It binds
four exit-0 runs, ten passing resume checks, a clean idle gate, and USD
`3.7082904651310202` in-container cost. Evaluation and promotion were false.

## 13. What is proven and unproven

Proven engineering properties:

- bounded proposals can be validated and isolated;
- unsafe/invalid candidates fail closed;
- immutable jobs can be scheduled and recovered;
- evidence and decisions are identity- and hash-bound;
- live GPU worker RPC and artifact transfer work;
- the H100 F2 execution/resume sequence works; and
- the complete offline product flow is reproducible.

Not yet proven:

- reduced BC weights improve policy success across paired seeds;
- agent proposals beat manual, random, or fixed-rule proposals;
- agent-authored objective code improves RLT;
- results generalize across tasks, models, runtimes, or robots; or
- the system can operate safely on physical hardware.

## 14. Next approved design gate

The next work is GPU-free G0 protocol review. The full test program is
`g0-scientific-experiment-test-program.md`; record the reviewed choices in
[`g0-decision-worksheet.md`](g0-decision-worksheet.md). Before renting a GPU, freeze the
independent evaluator, development/final reset sets, exact seeds, Stage-1
horizon rule, BC conditions, confidence/decision rule, retention, run matrix,
and maximum cost. Then request a new exact approval.

The current seed/reset proposal is
[`g0-seeds-and-reset-sets.md`](g0-seeds-and-reset-sets.md). Its proposed values
remain non-authorizing. Deterministic export and live CPU reset confirmation
now pass; human acceptance and production custody remain unresolved.

The evaluator trust boundary, local same-user isolation rehearsal, strict
production receipt schemas, and remaining operator choices are in
[`g0-evaluator-custody-and-deployment.md`](g0-evaluator-custody-and-deployment.md).

The non-authorizing runtime alternatives, pricing arithmetic, retry-inclusive
cost ceiling, and retention proposal are in
[`g0-runtime-cost-retention-candidate.md`](g0-runtime-cost-retention-candidate.md).

## 15. Failure handling and troubleshooting

- Dirty or wrong repository: stop before outputs; restore a reviewed clean
  worktree rather than ignoring the gate.
- Missing D1 pack: generate readiness diagnostics; do not publish a partial
  pack or reinterpret one-seed evidence.
- Proposal invalid: retain the failed slot and optional bounded repair record.
- Worker unreachable: preserve lease/attempt state; do not duplicate a run
  whose status is unknown.
- Result incomplete: mark failed or inconclusive under the frozen rule; never
  invent missing metrics.
- Artifact mismatch: reject evidence and preserve both expected/observed hash.
- Cost overrun: record actual cost and block further dispatch.
- Resume mismatch: fail closed; do not treat segmented execution as matched.
- Evaluator mismatch: stop the campaign and require a new preregistration.

## 16. Documentation protocol

Repository documents and tracked machine records are detailed truth. Obsidian
task `MI5T8` is the concise resume-ready memory. Chat is disposable.

At each milestone or terminal experiment:

1. update the relevant protocol/status document;
2. add or supersede the machine-readable record;
3. record exact validation commands and outcomes;
4. retain failures, costs, deviations, and interventions;
5. update documentation indexes and stale status statements;
6. update the Obsidian summary, files, decisions, validation, and session log;
7. commit the coherent evidence/documentation change; and
8. state the exact next gate and whether any paid resource is safe to release.

See `artifact-policy.md`, `contracts.md`, and
`../reproducible-agentic-enpire-plan.md` for normative detail.
