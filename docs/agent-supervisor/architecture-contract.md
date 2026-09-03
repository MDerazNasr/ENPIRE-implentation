# Coding-Agent Supervisor Architecture Contract

Status: Milestone 0 design contract. This document specifies responsibilities
and boundaries; later milestones implement them incrementally.

## 1. Meaning of “the agent supervises RL”

The agent supervises the **outer policy-improvement loop**. A complete RLT run
remains an ordinary, bounded RLinf process. Between runs, the supervisor reads
trusted evidence and asks a short-lived coding agent for one next hypothesis.

```text
approved campaign
       |
       v
curated evidence --> proposal backend --> structured proposal
                                             |
                                             v
                                      static validation
                                             |
                                             v
known-good commit --> isolated worktree --> bounded RLT run
                                             |
                                             v
                                  immutable run evidence
                                             |
                                             v
                                  deterministic evaluator
                                  /        |          \
                              keep      revert    inconclusive
```

The LLM never observes or controls each optimizer step, environment step, or
robot action. This keeps the fast control/training loops deterministic and
makes supervision auditable.

## 2. Trust boundaries

### Trusted and immutable during a campaign

- Approved campaign specification and budget envelope.
- Baseline project commit and pinned RLinf commit.
- Base VLA weights and inference behavior.
- Simulator implementation, task, reset IDs, and observation/action semantics.
- Success definition, evaluator code/version, and confirmation rule.
- Worker authentication, coordinator, artifact hashing, and cost enforcement.
- Completed run directories and prior decisions.

### Untrusted

- LLM prose, reasoning, generated configuration, and generated patches.
- Candidate-local tests supplied by the LLM.
- Partially written remote outputs.
- A candidate process's claim that it completed successfully.

Untrusted output becomes executable only after schema, scope, static, test, and
budget validation. Candidate tests supplement but never replace harness-owned
tests.

## 3. Planned component contracts

### Campaign coordinator

Owns two related append-only state machines. Campaign approval and trial
execution are separate because one approved campaign can contain several
independent hypotheses:

```text
campaign: draft -> validated -> approved -> active -> completed
             \---------- cancellation/failure boundaries --------/

trial:    proposing -> proposal_validated -> queued -> running -> evaluated
                                                        -> kept
                                                        -> reverted
                                                        -> inconclusive
                                                        -> failed/cancelled
```

Only the coordinator transitions state. Every transition records the previous
event hash, actor, timestamp, reason, and relevant artifact hashes. A trial's
terminal decision does not terminate its parent campaign. Replaying either
ledger reconstructs the same state. Repeated worker messages are idempotent.

### Proposal provider

Provider-neutral request/response boundary. Claude is first. A request contains
only the campaign goal, editable contract, relevant source excerpts, baseline
summary, compact prior-trial summaries, and metric definitions. A response
must contain one hypothesis, expected effect, falsification condition, exact
change, tests, and estimated cost.

The provider has no direct tools. One proposal slot permits an initial response
and one schema/scope repair within one combined budget. Sessions are isolated,
non-persistent, and limited to ten minutes.

### Proposal validator

Validates before a worktree or paid job is created:

- schema version and campaign/base identifiers;
- exactly one declared hypothesis;
- allowed change mode and paths;
- parameter names, types, and campaign-specific bounds;
- diff size, file size, imports, and forbidden commands;
- unchanged evaluator, reset, budget, infrastructure, and base-model hashes;
- estimated cost within remaining envelope.

### Git experiment manager

Creates one branch/worktree from an explicit verified incumbent per proposal.
It applies only validated changes, runs harness-owned checks, commits the exact
candidate, and records the diff/tree hashes. Promotion updates the arm's
incumbent pointer; it does not merge into the stable branch. Reversion preserves
evidence and marks the branch abandoned. Stable integration remains a human
review action.

### Experiment backend

Wraps the existing D1 launcher contract rather than replacing it. A worker
checks out the exact candidate and pinned RLinf commits, resolves the approved
configuration, verifies required assets, and uses dry-run by default. Paid
execution requires both campaign approval and the launcher's explicit paid-run
acknowledgement.

### Worker interface

Provider-neutral SSH workers expose prepare, launch, status/heartbeat, cancel,
and fetch-evidence operations. One worker runs one independent candidate at a
time in the initial implementation. Authentication material stays outside
campaign context and evidence.

### Evaluator

Consumes normalized evidence and applies a versioned deterministic rule. D1
confirmation uses the existing three-seed `KEEP`, `REVERT`, and `INCONCLUSIVE`
contract. Training loss is diagnostic and cannot independently promote a
candidate. Missing seeds, mismatched reset sets, incompatible configurations,
or insufficient episode evidence are inconclusive; runtime/non-finite failures
are failed or reverted according to the frozen protocol.

### Evidence and reporting

Local compact records are authoritative for orchestration and are linked to
W&B run IDs/URLs. Reports are derived from records rather than copied from LLM
summaries. Every displayed number identifies its source run and artifact hash.

## 4. Edit modes

### Mode A: configuration-only

The campaign lists individual Hydra/config keys and numeric/categorical bounds.
The candidate contains only generated overrides. Fixed scientific controls are
not allowlisted. This mode validates the complete supervisor before training
code generation is enabled.

### Mode B: actor-objective code

Pinned RLinf currently hard-codes the RLT Stage-2 actor objective inside its
worker rather than exposing a stable external objective plugin. Editing that
upstream file in place would violate D1's reproducibility boundary.

E0 froze a project-owned, opt-in `sitecustomize` adapter that reproduces the
pinned worker's `forward_actor` plumbing and delegates the differentiable
combination to one narrow plugin. E1 proved the default plugin exactly
numerically/gradient equivalent to upstream on fixed fixtures and real PyTorch
CPU tensors. The agent may edit only the plugin and its
candidate-local configuration/tests. The surrounding adapter is harness-owned.
See `e0-live-objective-seam.md`, `e1-default-objective-equivalence.md`, and ADR
0010.

This provides genuine training-code experiments while keeping canonical RLinf
clean and making every algorithmic delta explicit.

## 5. Integration and dependency gates

### Can be built before D1 Stage 7

- schemas, state machine, budgets, evidence ledger;
- Claude/fake proposal providers and context builder;
- validators and Git sandbox;
- fake experiment backend and fake SSH workers;
- evaluator interface, report generation, and replay;
- actor-objective adapter and equivalence fixtures;
- all non-GPU and adversarial tests.

### Requires D1 Stage 7

- selecting the immutable scientific baseline commit;
- replay validation against complete Reference A, Control B, and Candidate C;
- real config-only and code-enabled candidate runs;
- trustworthy keep/revert decisions against Control B;
- the three-arm comparison and performance conclusions;
- two-worker live GPU demonstration.

The integration gate requires the complete D1 evidence pack, a known-good
commit, fixed evaluation evidence, measured runtime/cost, and no unresolved
scientific mismatch. The current Phase-1 smoke and incomplete Stage-5 evidence
do not satisfy it.

## 6. Formal study boundary

The preregistered comparison has three arms, each starting from Control B and
receiving three discovery trials:

1. frozen deterministic rule controller, configuration-only;
2. Claude, configuration-only;
3. Claude, actor-objective code-enabled.

Each arm may advance only from its own externally verified incumbent. The best
valid candidate from each arm is confirmed over the approved three paired
Stage-2 seeds and fixed reset set. Discovery and confirmation budgets are
matched where the edit mode permits. Invalid and null trials remain visible.
With only three seeds, reports emphasize paired outcomes, ranges, and the
preregistered decision rather than broad statistical significance.

## 7. Demo boundary

The Ludvig demonstration will show a real, bounded CLI proposal/validation and
two-worker dispatch, then use completed real campaign evidence for final
decisions and comparisons. Replay or recorded material must be visibly labelled
and must reference the same immutable evidence; synthetic fixtures are used
only for development demonstrations, never presented as research results.

## 8. Non-goals

- supervising individual gradient or environment steps with an LLM;
- modifying/fine-tuning the base VLA;
- editing arbitrary RLinf or repository code;
- distributing one candidate across multiple GPUs;
- real-robot reset/safety orchestration;
- automated visual diagnosis or model-provider benchmarking;
- a general-purpose autonomous research-paper implementation system.
