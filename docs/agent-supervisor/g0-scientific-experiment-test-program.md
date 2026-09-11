# G0 Scientific Experiment Test Program

Status: **draft for protocol review; no GPU execution authorized**

Obsidian task: `MI5T8`

This document converts the September research meeting into a gated sequence of
experiments for testing the RLT hypothesis, the coding-agent supervisor, and
the efficiency of the multi-worker improvement loop. It begins after the
successful H100 PCIe F2 engineering rehearsal and before any scientific GPU
campaign.

F2 established that the fixed Control, Candidate, resume-source, and
resume-continuation sequence can execute on one matched runtime. It did not
evaluate policy quality and did not show that Candidate is better than
Control. The tests below produce those missing forms of evidence without
trusting agent-written claims.

## 1. Questions and claim boundaries

The program asks four separate questions:

1. Is the starting Stage-1 actor trained enough for a non-degenerate Stage-2
   comparison?
2. Does reduced scheduled BC weight improve RLT learning or final success?
3. Does an agent choose better experiments than manual or non-agent search
   under the same evidence and compute budget?
4. Does three-worker parallel search reduce time-to-improvement without
   weakening isolation, reproducibility, or cost control?

These questions must not be collapsed into one result. A policy improvement
does not prove agent value, and a faster scheduler does not prove a better
policy. Until its corresponding test passes, do not claim Candidate or agent
superiority, generalization beyond the frozen task/runtime, physical-robot
improvement, or authority to promote or enlarge the campaign.

## 2. Shared trust and execution contract

Every scientific test freezes these items before observing results:

- baseline, project, supervisor, and RLinf commits;
- Stage-1 actor, norm-stat, dataset, task, and runtime hashes;
- training seeds and disjoint development/final reset-set hashes;
- primary and secondary metrics;
- candidate configurations and permitted differences;
- timeout, GPU-cost, storage, and retry limits;
- evaluator source and environment hashes;
- selection, stopping, failure, and missing-data rules; and
- approver identity plus UTC activation timestamp.

The agent may propose a candidate. It may not modify or directly read the final
evaluator, choose retained results, compute the official score, select the
winner, approve paid execution, or promote a candidate. Harness-owned
deterministic code performs those actions.

Use two disjoint evaluation sets:

- **Development evaluation:** exposed only as bounded normalized evidence and
  used for horizon selection and discovery.
- **Final evaluation:** hidden from proposers and run once on frozen selected
  candidates during confirmation.

The evaluator lives outside agent-writable worktrees. It rejects unknown
commits, reset drift, duplicate or partial seeds, non-finite metrics, missing
artifacts, and identity drift. Every attempt retains its proposal, commits,
resolved config, command, manifests, metrics, logs, checkpoints, telemetry,
cost, evaluator result, decision, and SHA-256 manifest. Invalid, failed,
interrupted, retried, reverted, and inconclusive attempts remain in the ledger.

## 3. E0 — independent evaluator integrity

**Hypothesis:** The official score and selection are reproducible from
immutable artifacts and cannot be changed by candidate code or agent prose.

Run without paid training:

1. Build the evaluator from a separate read-only source root.
2. Expose training constraints and bounded development summaries to the agent,
   but not the final reset IDs or evaluator implementation.
3. Replay known evidence twice and require byte-identical normalized metrics
   and decisions.
4. Test metric spoofing, missing trajectories, duplicate seeds, reset
   substitution, evaluator tampering, identity mismatch, path escape, and
   fabricated success text.
5. Verify direct append-only ledger output and that worktrees cannot change it.

Pass gate:

- [ ] Repeated evaluation is byte-identical.
- [ ] Every adversarial fixture fails closed.
- [ ] Agent narrative has no effect on score or selection.
- [ ] Every result binds evaluator and reset-set identities.
- [ ] Final evaluation inputs are absent from agent-visible context.

GPU requirement: none.

## 4. E1 — Stage-1 horizon and checkpoint selection

**Hypothesis:** Longer Stage-1 training yields a non-degenerate starting actor,
and a development curve identifies the shortest defensible checkpoint before
Stage-2 comparisons.

Evaluate one uninterrupted lineage at proposed checkpoints 500, 1,000, 2,000,
4,000, and 8,000 steps. These values remain provisional until G0 review
confirms dataset size, batch semantics, cadence, and cost. Use a bounded pilot
seed to estimate the plateau, then rerun the selected horizon on paired seeds
if Stage-1 is seed-dependent. Never select the horizon using final evaluation.

Metrics:

- Primary: development `success_once` over the fixed trajectory count.
- Secondary: confidence interval, learning-curve area, steps and cost to a
  frozen threshold, wall/GPU time, peak VRAM/RAM, checkpoint size, and seed
  variance.

Pass gate:

- [ ] Every checkpoint loads without fallback and has complete ancestry.
- [ ] The selected checkpoint is non-degenerate under the frozen rule.
- [ ] The stopping/plateau rule is applied mechanically.
- [ ] Selection uses development results only.
- [ ] The selected actor is exported and independently hash-verified.

GPU requirement: one large-memory GPU for training; evaluation uses only a
runtime that preserves the frozen scientific identity.

## 5. E2 — three-branch BC-schedule theory pilot

**Hypothesis:** Reducing scheduled BC contribution improves Stage-2 policy
learning under otherwise identical RLT execution.

Proposed conditions:

| Condition | Warm-up BC | Online BC | Purpose |
|---|---:|---:|---|
| Control | 7.0 | 2.5 | Current matched baseline |
| Candidate | 5.6 | 2.0 | Existing 20% reduction hypothesis |
| Strong reduction | 4.2 | 1.5 | Proposed directional/dose-response point |

The third condition is not approved. G0 may replace it, but it must be frozen
before execution. Q weights and every other scientific field remain identical.
Each condition starts from the same selected actor and uses the same paired
seeds, runtime, horizon, batching, evaluator, reset sets, checkpoints, and cap.

Metrics and decision:

- Primary: paired final success difference versus Control.
- Secondary: development curve, area under the curve, time/episodes to
  threshold, update/replay counters, wall time, GPU cost, and failure rate.
- Report each seed, mean difference, frozen interval, and missing/failed runs.
- Apply only the preregistered `KEEP`, `REVERT`, or `INCONCLUSIVE` rule.

Pass gate:

- [ ] Static comparison finds only the approved BC differences.
- [ ] Every condition completes the same paired seed set.
- [ ] Runs enter the intended online schedule and perform real updates.
- [ ] Resume fingerprints and replay RNG satisfy the F2 contract.
- [ ] The independent evaluator produces the official result.
- [ ] All outcomes and costs are retained before a next generation.

GPU requirement: three matched workers are preferred for simultaneous runs;
sequential execution is valid only with preserved runtime identity.

## 6. E3 — deterministic evolutionary search

**Hypothesis:** A one-parent-to-three-child loop uses multiple measured delta
points to choose the next parent reproducibly without LLM winner selection.

For two initial generations:

1. Start three isolated children from one frozen parent.
2. Permit one bounded config change per generation-1 child.
3. Execute children on independent matched workers.
4. Wait until all assigned records are terminal.
5. Evaluate every valid child on the same development benchmark.
6. Select by primary score, paired delta, lower cost, lower wall time, then
   lexical candidate ID.
7. Create the next three children only from the selected branch.

Invalid, failed, or inconclusive children consume their slot. Unselected
branches remain immutable and cannot silently re-enter later generations.

Pass gate:

- [ ] One parent produces exactly three isolated children.
- [ ] No file, checkpoint, context, or evaluator-result leakage occurs.
- [ ] Selection is deterministic and independent of agent prose.
- [ ] Coordinator restart reproduces the same state.
- [ ] Worker loss or late completion cannot duplicate accepted evidence.
- [ ] The complete branch tree is rendered from ledger data.

GPU requirement: three matched GPUs for live timing; fixture and smoke gates
must pass first.

## 7. E4 — agent-value comparison

**Hypothesis:** With equal information, edit scope, trials, and compute, the
agentic proposer finds a better or more efficient candidate than manual or
non-agent search.

Arms:

1. **Manual:** researcher-selected configs frozen before the generation.
2. **Random/grid:** deterministic samples from the same allowed domain.
3. **Agentic config:** one short tool-free session sees the same bounded
   development evidence and proposes within that domain.

This first comparison is configuration-only. The broader M8 fixed-rule,
Claude-config, and Claude-code study remains later, after G/H readiness.

Fairness controls:

- same parent, generations, discovery slots, paired seeds, and evaluator;
- same timeout and GPU cap per candidate;
- same development evidence and no final-evaluation visibility;
- separate reporting of LLM tokens/cost, with no fictional LLM allowance for
  non-LLM arms; and
- invalid proposals and failed runs consume their slots.

Outcomes:

- Primary: selected candidate's paired final success delta.
- Efficiency: delta per GPU-hour, dollar, candidate, and wall-clock hour.
- Agent behavior: invalid, repaired, duplicated, unsupported, or abandoned
  proposals, tokens, LLM cost, and interventions.
- Reproducibility: seed variance and independent confirmation.

Pass gate:

- [ ] Allocation and compute parity audit passes.
- [ ] Runtime and evaluator identities match across arms.
- [ ] Selection waits for all discovery slots.
- [ ] Selected commits freeze before hidden confirmation.
- [ ] Confirmation uses common paired seeds and final resets.
- [ ] Conclusions separate policy gain from proposer efficiency.

GPU requirement: up to three matched GPUs concurrently; calculate and approve
the total seed-run and cost ceiling before activation.

## 8. E5 — parallel scheduling and cost efficiency

**Hypothesis:** Three workers reduce wall time versus one without changing the
evidence, decision, scientific variance, or declared GPU work.

Replay identical contracts through simulated serial and three-worker
schedules. If live confirmation remains necessary, use short non-scientific
smoke contracts instead of duplicating full training. Candidate results and
selection must be invariant to completion order.

Measure wall time, aggregate GPU seconds/cost, utilization, queue wait, lease
expiry, retries, cancellations, stale results, duplicates, polling overhead,
and result equality.

Pass gate:

- [ ] Serial and parallel schedules produce the same evidence and decision.
- [ ] Parallel execution meets its frozen wall-time target.
- [ ] GPU seconds stay within jobs plus approved retry budget.
- [ ] Worker loss and coordinator restart do not duplicate evidence.

GPU requirement: none for replay; up to three inexpensive GPUs for an optional
bounded live systems smoke.

## 9. E6 — secondary task-quality metrics

**Hypothesis:** Simulator-derived quality metrics distinguish policies with
similar binary success without creating an agent-controllable score.

Candidate metrics include action jerk/smoothness, collisions, constraint
violations, object stability, spillage or retained contents where supported,
episode length, action magnitude, and samples-to-success. Each metric needs a
harness-owned definition, units, direction, aggregation, missing-value rule,
and deterministic fixture. Primary success remains the initial promotion
endpoint; secondary metrics may break a tie only if preregistered.

Pass gate:

- [ ] Metrics derive from simulator evidence, not agent text.
- [ ] Deterministic trajectories reproduce identical values.
- [ ] Pathological trajectories produce expected adverse values.
- [ ] Missing sensors or unsupported tasks fail explicitly.
- [ ] No post-result reweighting or composite score is permitted.

GPU requirement: none for fixtures; collect during approved runs thereafter.

## 10. Deferred tool and multi-agent ablations

Do not initially allow arbitrary tool creation. First establish the
configuration-only, single-supervisor baseline. If a measured limitation
appears, preregister separate tests for no extra tools versus curated analysis
tools, curated versus agent-created tools in an isolated non-scientific
sandbox, and one supervisor versus bounded specialist subagents.

Compare proposal validity, improvement per budget, context loss, duplicated
work, policy violations, and reproducibility. Keep a tool or subagent only if
it improves a frozen outcome without expanding authority.

## 11. Ordered execution checklist

### GPU-free design and integrity

- [ ] Approve this document as the G0 protocol basis.
- [ ] Resolve exact paired seeds and whether Stage-1 is seed-dependent.
- [ ] Freeze development/final reset sets and evaluator.
- [ ] Complete E0 integrity and adversarial tests.
- [ ] Freeze horizon checkpoints, plateau rule, and E1 budget.
- [ ] Freeze E2's third condition or reduce E2 to two conditions.
- [ ] Freeze metrics, interval, decision, and failure rules.
- [ ] Generate the complete run matrix and maximum cost.

### Baseline and theory

- [ ] Obtain exact E1 paid approval.
- [ ] Run E1 and export/hash the selected actor.
- [ ] Freeze matched E2 contracts from that actor.
- [ ] Obtain exact E2 approval and run all paired conditions.
- [ ] Apply the independent evaluator and preserve the conclusion.

### Search and agent value

- [ ] Run E3 with fixtures, then approved bounded candidates.
- [ ] Freeze E4 contexts, proposal domain, allocations, and budgets.
- [ ] Activate E4 before receiving proposals or results.
- [ ] Complete discovery, deterministic selection, and hidden confirmation.
- [ ] Report policy outcome and proposer efficiency separately.

### Systems, metrics, and closeout

- [ ] Complete E5 replay and optional bounded live smoke.
- [ ] Validate each E6 metric before reporting it.
- [ ] Decide whether evidence justifies tool or multi-agent ablations.
- [ ] Rehash all curated artifacts from a clean checkout.
- [ ] Reconcile JSON, CSV, Markdown, plots, and cost totals.
- [ ] Record deviations, failures, retries, and interventions.
- [ ] Update repository and Obsidian records after each terminal gate.

## 12. Minimum first campaign

After E0 and E1 pass, run E2 first:

- one manipulation task and frozen non-degenerate Stage-1 actor;
- two or three preregistered BC schedules;
- three paired seeds per condition;
- identical H100 PCIe runtime and training budget;
- development evaluation for diagnostics;
- one untouched final evaluation for comparison; and
- deterministic non-agent scoring and selection.

Three conditions require nine Stage-2 training runs. This tests the RLT
objective hypothesis, not agent superiority. E4 subsequently tests whether the
agentic proposer adds value.

## 13. Documentation per terminal test

Each E0–E6 test receives a reviewed protocol JSON and fingerprint, human
amendment, attempt evidence and hashes, run/cost/resource table, evaluator and
decision record, validation command/result, explicit claim boundary, and an
Obsidian `MI5T8` link to repository truth.

No chat transcript, dashboard screenshot, agent statement, or untracked remote
file is sufficient evidence by itself.
