# Reproducible Agentic ENPIRE Program Plan

Status: active planning and reconciliation

Obsidian task ID: `MI5T8`

Current D1 branch and head: `experiment/d1-rlt-baseline` at `eed314f`

Current D2 branch and head: `feature/d2-agent-supervisor` at `707b88f`

## 1. Purpose

This is the canonical execution plan for joining the reproducible D1 RLT
laboratory with the D2 coding-agent supervisor and then running the first
scientifically defensible ENPIRE-style agent comparison.

The program has two independently valuable systems:

- **D1, the laboratory:** pinned RLinf execution, fixed evaluation, provenance,
  cost controls, resume integrity, evidence preservation, and a frozen
  scientific decision rule.
- **D2, the automated researcher:** bounded proposals, policy enforcement, Git
  isolation, worker orchestration, deterministic evaluation, arm isolation,
  and reproducible reporting.

The immediate goal is not to launch a large study. It is to reconcile the two
systems, prove their live compatibility with bounded acceptance tests, and open
the strict D1 integration gate without weakening it.

## 2. Current evidence-backed status

### 2.1 D1 laboratory

- [x] Pinned RLinf integration exists.
- [x] Dry-run and explicit paid-run gates exist.
- [x] Commands, configurations, commits, logs, costs, resources, and artifacts
  are retained.
- [x] Stage-1 step-500 actor is hash-pinned.
- [x] Fixed 256-reset Reference A evaluation exists.
- [x] A trained Control B seed-2026 result exists: `18/256`.
- [x] A corrected Candidate C seed-2026 result exists: `17/256`.
- [x] Strict RLT schedule/replay resume sidecars exist and passed the bounded
  continuation gate.
- [x] The D1 Stage-7 evidence directory exists at `results/d1-evidence-pack/`.
- [x] The repository records the formal scientific decision as
  `INCONCLUSIVE`.
- [ ] Control B and Candidate C have not been completed on three paired seeds.
- [ ] The existing Control/Candidate pair used different runtime paths and is
  not a strict one-factor causal comparison.
- [ ] The supervisor's canonical `results/d1-stage7/evidence_pack.json` does
  not exist.

### 2.2 D2 coding-agent supervisor

- [x] M0-M9 control-plane implementation exists on
  `feature/d2-agent-supervisor`.
- [x] Provider-neutral, Claude-first structured proposal boundary exists.
- [x] Claude sessions are short, tool-free, non-persistent, budgeted, and
  schema-constrained.
- [x] Configuration and narrow actor-objective proposal modes exist.
- [x] Schema, path, diff, AST, test, and behavioral validation exist.
- [x] Each accepted hypothesis receives an isolated branch/worktree.
- [x] Campaign/trial state, hash-chained evidence, budgets, and approvals exist.
- [x] Deterministic evaluation exclusively owns `KEEP`, `REVERT`, and
  `INCONCLUSIVE`.
- [x] Worker capabilities, leases, retries, recovery, cancellation, and stale
  result rejection exist.
- [x] Fixed SSH RPC and D1 subprocess adapter seams exist.
- [x] The preregistered three-arm study and offline delivery bundle exist.
- [x] A real CPU toy-policy demonstration exists with an explicit non-RLT
  claim boundary.
- [x] The extracted D2 head passes 200 tests and 98 subtests.
- [ ] No real Claude proposal has been accepted as scientific evidence.
- [ ] No real D2-controlled RLinf/GPU trial has run.
- [ ] The actor-objective ABI is not attached to the live PyTorch/RLinf loss.
- [ ] Remote worker deployment and real SSH/GPU acceptance remain incomplete.
- [ ] D2 documentation contains stale pre-D1-completion status statements.

### 2.3 Current integration-gate result

The read-only D2 checker reports `blocked` for the current D1 worktree because:

1. the worktree is not clean; and
2. `results/d1-stage7/evidence_pack.json` is absent.

Even after those mechanical issues are resolved, the gate must remain blocked
until the approved paired-seed evidence contract is satisfied or a new protocol
is explicitly reviewed and preregistered. The gate must not be weakened merely
to obtain `ready`.

## 3. Governing principles

### 3.1 Source hierarchy

When sources conflict, use this order:

1. Reviewed scientific protocol and its immutable evidence commit.
2. Pinned RLinf source and official RLT behavior.
3. Versioned D1/D2 contracts and accepted ADRs.
4. ENPIRE paper architecture and evaluation lessons.
5. Convenience behavior in demos or historical wrappers.

### 3.2 Authority boundaries

- The coding agent may propose; it may not approve, launch, score, or promote.
- The supervisor owns scope, validation, Git isolation, budgets, and lifecycle.
- Workers execute immutable run contracts and return evidence only.
- The evaluator alone decides promotion under the frozen rule.
- RLinf owns optimizer, rollout, simulator, action, reset, and metric behavior
  inside a run.
- Paid execution always requires an exact approval envelope and explicit
  acknowledgement.
- Completed and failed runs are retained; negative evidence is not deleted.
- Canonical RLinf and frozen VLA weights remain immutable.

### 3.3 Claim boundary

Until the live study is completed, permissible claims are limited to:

- reproducible D1 engineering execution;
- a tested agentic control-plane implementation;
- safe proposal, isolation, worker, evidence, and evaluation boundaries; and
- real improvement on the explicitly scoped CPU toy task.

Do not claim Claude improves RLT, one arm beats another, the VLA improves
across seeds, or physical ENPIRE reproduction before the corresponding gates
and evidence exist.

## 4. Documentation and Obsidian memory protocol

### 4.1 Durable sources

- Repository Markdown and tracked machine-readable artifacts are the detailed
  source of truth.
- Obsidian task `MI5T8` is the concise resume-ready program memory.
- Run directories are immutable evidence, not narrative documentation.
- Chat history is disposable and must never be the only record of a decision.

### 4.2 Start-of-session checklist

- [ ] Resolve and read Obsidian task `MI5T8` before broad exploration.
- [ ] Read `Current Summary`, `Decisions`, `Validation`, and the last session
  log entry.
- [ ] Confirm current branch, head, worktree status, and active milestone.
- [ ] Inspect the last gate artifact rather than relying on prose alone.
- [ ] Record any user-supplied related task IDs as Obsidian wikilinks; do not
  infer related tasks.

### 4.3 During-work checklist

- [ ] Update the task note when a decision is accepted.
- [ ] Record explored approaches that were rejected and why.
- [ ] Record newly identified authoritative files and artifact locations.
- [ ] Record validation that changes confidence or gate status.
- [ ] Keep task memory concise; link to repository documents instead of copying
  long transcripts, logs, or specifications.
- [ ] Never place credentials, tokens, private endpoints, or raw secrets in
  Git or Obsidian.

### 4.4 End-of-session checklist

- [ ] Update `last_updated` without changing `created`.
- [ ] Replace `Current Summary` with the current state in two to five lines.
- [ ] Update `Files / Areas That Matter`.
- [ ] Deduplicate `Decisions` and `Dead Ends / Compressed Exploration`.
- [ ] Record exact tests, dry runs, hashes, and manual checks under
  `Validation`.
- [ ] Append a concise dated session-log entry.
- [ ] State the next gate and any exact blocker.

### 4.5 Per-experiment documentation checklist

- [ ] Campaign ID, trial ID, arm, parent commit, and candidate commit.
- [ ] Project, supervisor, and RLinf commits.
- [ ] Model, dataset, checkpoint, norm-stat, reset-set, and evaluator hashes.
- [ ] Exact resolved configuration and logical command hash.
- [ ] Proposal/context/response hashes, model identity, tokens, and LLM cost.
- [ ] Approval identity, timestamp, budget envelope, and paid acknowledgement.
- [ ] Worker identity, capabilities, lease, attempt number, and runtime class.
- [ ] Start/end timestamps, exit status, wall time, GPU utilization, and cost.
- [ ] Raw logs plus normalized primary and secondary metrics.
- [ ] Artifact paths, sizes, SHA-256 digests, and preservation status.
- [ ] Deterministic decision record and incumbent result.
- [ ] Limitations, protocol deviations, failures, and human interventions.

## 5. Workstream A: preserve and reconcile branches

### A0. Protect current user work

- [x] Inventory modified and untracked files on the D1 worktree.
- [x] Treat `README.md`, `modal_app.py`, `mo-notes.txt`, and `tmp/` as
  user-owned until classified.
- [x] Do not clean, reset, overwrite, or absorb them implicitly.
- [x] Record which files must remain outside the reconciliation commit.

Inventory recorded on 2026-09-02:

- `README.md` has 29 uncommitted lines documenting a generic Modal GPU shell
  and diagnostic workflow.
- `modal_app.py` is the matching untracked 62-line Modal launcher. The user
  confirmed that this file and the README instructions are intended project
  work and should be preserved.
- `mo-notes.txt` was an empty one-byte untracked file. The user approved its
  removal, and it was removed.
- `tmp/` contains 78 files and approximately 20 GB. It holds Stage-1 actor
  backups, Control/Candidate evidence, logs, hashes, the ENPIRE paper extract,
  and a handoff archive. Tracked `results/d1-evidence-pack/artifact-index.json`
  references several of these paths. It must remain local and protected; it
  must not be added wholesale to Git. The root `.gitignore` now excludes
  `tmp/` without removing any evidence.
- `docs/README.md` and `docs/reproducible-agentic-enpire-plan.md` are changes
  created for task `MI5T8` and belong to the reconciliation documentation.

Gate A0: all pre-existing changes are identified and preserved.

Gate A0 result: **passed on 2026-09-02**. The Modal pair is retained, the empty
notes file is removed with approval, the 20 GB evidence tree is preserved and
ignored, and the reconciliation documentation is separately identified.

### A1. Create an isolated reconciliation worktree

- [x] Create a new integration branch from D1 head `eed314f`.
- [x] Use a separate worktree outside the active repository directory.
- [x] Record base head, D2 head, worktree path, and creation command.
- [x] Verify the original D1 HEAD and worktree contents did not change.

Suggested branch: `integration/d1-d2-agentic-harness`.

Recorded A1 state on 2026-09-02:

- Integration branch: `integration/d1-d2-agentic-harness`.
- Integration worktree: `/private/tmp/enpire-d1-d2-agentic-harness`.
- D1 base: `eed314f68243bb82081f3ab145615f28e2e86173`.
- D2 source: `707b88f0bfb745c295042f012930ed219e2c21be`.
- Creation command: `git worktree add -b
  integration/d1-d2-agentic-harness
  /private/tmp/enpire-d1-d2-agentic-harness eed314f...`.
- The integration worktree is clean and its branch/head match the recorded
  values.
- The original worktree remains on `experiment/d1-rlt-baseline` at `eed314f`;
  its intended changes and 20 GB `tmp/` evidence tree remain present.
- Git also reports a pre-existing prunable registration for
  `/private/tmp/enpire-d2-agent-supervisor`; the D2 branch itself resolves to
  the required head, so no cleanup was performed.

Gate A1: isolated clean worktree exists and both source heads are recorded.

Gate A1 result: **passed on 2026-09-02**.

### A2. Integrate D2 selectively

- [x] Bring in `supervisor/`, its tests, examples, scripts, and
  `docs/agent-supervisor/`.
- [x] Preserve newer D1 launcher, resume, evidence, and Modal work.
- [x] Resolve `README.md`, `docs/README.md`, and checklist conflicts manually.
- [x] Do not overwrite newer D1 evidence with the D2 branch's August snapshot.
- [x] Retain accepted D2 ADRs unless superseded by a documented new ADR.
- [x] Produce a file-level reconciliation report.

Gate A2: combined tree contains current D1 and complete D2 without evidence
regression or undocumented contract changes.

Gate A2 result: **passed on 2026-09-02**. The history-preserving merge produced
one documentation-index conflict and no code/evidence conflicts. D1-owned
paths compare unchanged with `eed314f`; D2 supervisor code compares unchanged
with `707b88f` except for current-status documentation. The reconciled tree was
bound in merge commit `059a130927c99d09c013886bd06cdeb83fc48d18`. See
`docs/agent-supervisor/d1-d2-reconciliation.md`.

### A3. Baseline verification after integration

- [x] Run the complete D1 and D2 test suites.
- [x] Run Python compilation checks.
- [x] Run `git diff --check`.
- [x] Verify relative documentation links.
- [x] Run all offline M4, M7, M8, and M9 demonstrations.
- [x] Run and verify the real CPU policy demo.
- [x] Confirm the original stable branch and active D1 worktree are unchanged.

Gate A3: all offline regression and artifact-verification gates pass from a
clean integration commit.

Gate A3 result: **passed on 2026-09-02**. From clean integration commit
`059a130927c99d09c013886bd06cdeb83fc48d18`, the combined suite passed 236
tests and 125 subtests; Python compilation, whitespace/conflict checks, and 49
relative links across 62 Markdown files passed. The M4, M7, M8, and M9 offline
demos completed without external calls. The M9 bundle verifier accepted 15
artifacts with delivery fingerprint
`79c7f7e600a6814d6b95db42c4e4a8c711a47c90b077eaebca48e7fc974a02dd`.
The real CPU policy demo and verifier accepted 14 artifacts with result
fingerprint
`9ae476d209b1f69c368cf084e01ce283df49961e377e0b5c7373ee711ec6ce15`.
That demo is explicitly toy/non-RLT evidence. The source branches remain at
`eed314f` and `707b88f`; the original D1 worktree and its 20 GB ignored local
evidence tree are unchanged.

## 6. Workstream B: canonical D1 Stage-7 handoff

### B0. Map existing evidence to the supervisor schema

- [x] Inventory every file in `results/d1-evidence-pack/`.
- [x] Map existing run table, cost table, hashes, plots, summaries, and raw
  evidence to the seven required supervisor artifact roles.
- [x] Identify fields unavailable from tracked evidence.
- [x] Distinguish missing packaging from missing scientific evidence.
- [x] Document whether W&B is authoritative, supplementary, or unavailable for
  each run.

Gate B0: a complete schema-mapping table exists with no invented fields.

Gate B0 result: **passed on 2026-09-02**. The ten tracked source-pack files,
fourteen indexed evidence references, seven required artifact roles, strict
pack/run/campaign fields, and per-run W&B status are mapped in
`docs/agent-supervisor/d1-evidence-schema-mapping.md`. The mapping confirms
that deterministic packaging can improve the handoff but cannot manufacture
the missing matched seeds, reset-set hash, runtime parity, exact provenance,
or reviewer approval. The current scientific result remains `INCONCLUSIVE`.

### B1. Implement the canonical pack builder and readiness report

- [x] Add a deterministic pack builder or validator rather than hand-maintain
  derived values.
- [x] Emit a separate readiness report that lists all present and missing
  source evidence without claiming that the canonical gate pack exists.
- [x] Make canonical publication refuse incomplete approved seeds, unmatched
  runtime identities, missing artifacts, or unresolved decisions.
- [x] Bind reviewed source commits without a self-referential Git hash.
- [x] Include all required artifact roles with real sizes and SHA-256 values.
- [x] Reject missing, duplicated, non-finite, mismatched, or untracked inputs.

Gate B1: the builder is reproducible and fails closed on today's one-seed,
runtime-mismatched evidence; its readiness report explains every blocker.

Gate B1 result: **passed on 2026-09-02**. The strict publisher in
`supervisor/d1_pack_builder.py` computes all seven artifact hashes/sizes from
tracked clean inputs and validates the existing version-1 pack contract,
matched runtime identity, exactly three paired seeds, resolved decision, and
ancestor commits. `scripts/build_d1_evidence_pack.py` atomically emitted
`results/d1-stage7/readiness.json`; repeated generation was byte-identical
(SHA-256
`2259d0aeea3192869d303913be286cb1eeaf609a0fdb4f48953be98274461c97`).
Today's evidence exits `2`, lists eleven explicit blockers, sets
`canonical_pack_claimed: false`, and leaves `evidence_pack.json` absent.
Adversarial builder tests and the full combined suite passed: 244 tests and
125 subtests.

### B2. Update integration-gate compatibility

- [x] Run the D2 gate against the canonical pack.
- [x] Compare legacy D1 and D2 evaluator outputs exactly.
- [x] Reconcile genuine schema changes with a versioned adapter.
- [x] Do not loosen cleanliness, ancestry, seed, provenance, or baseline gates.
- [x] Add fixtures reproducing every newly discovered incompatibility.

Gate B2: evaluator compatibility is covered by fixtures and any valid subset
diagnostic; the live gate remains `blocked` until a complete canonical pack can
be published.

Gate B2 result: **passed on 2026-09-02**. An end-to-end clean-Git fixture builds,
publishes, commits, and opens the unchanged D1 integration gate. The declared
legacy, replayed legacy, and supervisor decisions are all `KEEP`; control mean,
candidate mean, mean delta, and both CI95 bounds compare exactly. The B1 wrapper
materializes the gate's native version-1 `D1EvidencePack`, so no genuine schema
incompatibility or versioned adapter was required. A real read-only audit from
clean commit `dead3b1` remains `blocked` solely because the canonical pack is
absent; the readiness report retains the underlying eleven blockers. See
`docs/agent-supervisor/d1-pack-gate-compatibility.md`.

## 7. Workstream C: proposal-provider acceptance

### C0. Freeze the provider contract

- [ ] Confirm Claude CLI executable/version and selected model.
- [ ] Preserve the provider-neutral interface.
- [ ] Confirm `--tools ""`, safe mode, no session persistence, JSON schema,
  ten-minute ceiling, and dollar budget.
- [ ] Confirm the sanitized environment allowlist contains only required
  provider credentials and runtime fields.
- [ ] Freeze context-size, output-size, attempt, and repair limits.

Gate C0: provider invocation is deterministic in shape and least-authority.

### C1. Conduct one no-GPU real-provider acceptance

- [ ] Build one curated, hashed D1 context bundle.
- [ ] Request one configuration-only proposal.
- [ ] Record provider/model, prompt/context hash, response hash, tokens, cost,
  duration, and validation result.
- [ ] Exercise the bounded repair path only if the first proposal is invalid.
- [ ] Prove Claude had no tools and caused no repository or external mutation.
- [ ] Preserve invalid output if produced.

Gate C1: one real provider response passes or fails safely through the same
contracts as fixtures; no policy-performance claim is made.

## 8. Workstream D: configuration-mode live attachment

### D0. Dry-run acceptance

- [ ] Apply an accepted allowlisted proposal in an isolated hypothesis
  worktree.
- [ ] Run harness-owned configuration checks.
- [ ] Generate worker-owned seed configurations outside the candidate tree.
- [ ] Dry-resolve exact D1/RLinf commands and hashes.
- [ ] Verify stable HEAD and every other arm remain unchanged.
- [ ] Verify no GPU or paid process can launch in dry-run mode.

Gate D0: proposal-to-D1-plan path passes without external execution.

### D1. Bounded no-GPU subprocess acceptance

- [ ] Execute the D1-shaped local fixture through the real subprocess adapter.
- [ ] Test timeout, missing artifact, hash mismatch, cost overrun, and failure
  normalization.
- [ ] Confirm invalid evidence cannot reach evaluation or promotion.

Gate D1: the integrated coordinator consumes real subprocess artifacts with
the correct authority boundary.

### D2. Small paid configuration acceptance

- [ ] Define a minimal live acceptance profile that tests attachment without
  pretending to be a scientific candidate.
- [ ] Obtain explicit approval for its exact cost and runtime envelope.
- [ ] Run on one qualified worker.
- [ ] Reconcile manifest, log, W&B semantics, costs, hashes, and cleanup.
- [ ] Preserve the result regardless of success.

Gate D2: one real D2-controlled D1 run completes or fails safely under the
immutable run contract.

## 9. Workstream E: actor-objective code attachment

### E0. Locate and freeze the PyTorch seam

- [ ] Identify the exact pinned-RLinf actor-loss combination site.
- [ ] Record tensor shapes, reductions, dtype, device, scaling, and autograd
  expectations.
- [ ] Determine a project-owned overlay mechanism that does not modify
  canonical RLinf source.
- [ ] Define the manifest proof that the intended objective was loaded.
- [ ] Record the design in a new ADR if it changes the M6 contract.

Gate E0: the live ABI is explicit, reviewable, and compatible with immutable
RLinf.

### E1. Prove default equivalence

- [ ] Run the default `actor_loss + bc_weight * bc_loss` overlay against the
  native path.
- [ ] Compare forward values and all relevant gradients.
- [ ] Test representative shapes, devices, dtypes, zero/edge values, and
  accumulation behavior.
- [ ] Define tolerances before viewing candidate results.
- [ ] Fail closed on disconnected or non-finite gradients.

Gate E1: default overlay is behaviorally equivalent within frozen tolerances.

### E2. Prove a bounded candidate change

- [ ] Generate or use one allowed non-no-op objective proposal.
- [ ] Pass source, AST, import, signature, value, and gradient checks.
- [ ] Verify the objective source hash appears in plan, command, manifest, and
  evidence.
- [ ] Run a no-GPU or smallest possible attachment probe.
- [ ] Preserve failed and rejected candidates.

Gate E2: code-mode proposal-to-live-objective provenance is complete; no RLT
improvement claim is made.

## 10. Workstream F: worker/runtime qualification

### F0. Select one matched scientific runtime

- [ ] Choose a graphics-capable GPU class from measured complete-route needs.
- [ ] Pin OS/image, Python, Torch/CUDA, simulator, renderer, RLinf, and harness
  versions.
- [ ] Pin batching, actor offload, weight transport, and resume behavior.
- [ ] Verify model, Stage-1 actor, dataset, and norm-stat hashes.
- [ ] Record provider storage and billing lifecycle.

Gate F0: Control and all candidate arms can use the same declared runtime.

### F1. Deploy fixed worker RPC

- [ ] Implement/deploy the harness-owned remote helper.
- [ ] Pin SSH endpoints and commands outside agent control.
- [ ] Validate prepare, launch, status, heartbeat, cancel, and fetch-evidence.
- [ ] Test identity spoofing, malformed payloads, late results, worker loss,
  coordinator restart, and retry.
- [ ] Implement artifact transfer and digest verification.
- [ ] Capture actual GPU utilization and provider cost.

Gate F1: remote workers satisfy the existing M7 contract without general shell
authority for the agent.

### F2. Matched runtime rehearsal

- [ ] Run one bounded Control-shaped and Candidate-shaped rehearsal on the same
  runtime.
- [ ] Confirm identical science identity except the approved intervention.
- [ ] Verify resume counters and RNG limitations.
- [ ] Decide whether uninterrupted runs are required for the definitive study.
- [ ] Update cost projections using measured end-to-end runtime.

Gate F2: runtime differences no longer confound the planned comparison.

## 11. Workstream G: complete the reproducible baseline

### G0. Review the seed and rerun policy

- [ ] Confirm the three approved training seeds before launching new runs.
- [ ] Decide whether seed 2026 must be rerun because existing Control and
  Candidate used different runtimes.
- [ ] Freeze the decision before seeing new outcomes.
- [ ] Record whether one Reference A evaluation can be shared across Stage-2
  seeds and why.

Gate G0: the exact run matrix and causal comparison are preregistered.

### G1. Execute matched Control B

- [ ] Run every approved Control seed on the matched runtime.
- [ ] Use the same Stage-1 actor, reset set, horizon, batching, and evaluator.
- [ ] Verify online schedule entry and real actor/critic updates.
- [ ] Preserve every terminal, failed, interrupted, and retried attempt.

Gate G1: complete matched Control evidence exists for all approved seeds.

### G2. Execute matched Candidate C

- [ ] Run every approved Candidate seed with only the frozen BC intervention.
- [ ] Use the same worker/runtime contract as Control.
- [ ] Verify schedule and resume state continuously.
- [ ] Preserve every outcome without selective reruns.

Gate G2: complete paired Candidate evidence exists for all approved seeds.

### G3. Freeze the D1 conclusion

- [ ] Apply the preregistered paired evaluator.
- [ ] Report per-seed values, means, delta, CI, failures, cost, and runtime.
- [ ] Return exactly `KEEP`, `REVERT`, or `INCONCLUSIVE`.
- [ ] Regenerate the canonical Stage-7 pack and artifact hashes.
- [ ] Publish `results/d1-stage7/evidence_pack.json` only after the builder
  confirms all strict scientific and provenance requirements.
- [ ] Review and commit the immutable evidence handoff.

Gate G3: another engineer can reproduce and audit D1 without live explanation.

## 12. Workstream H: open the supervisor gate

- [ ] Start from a clean reviewed D1 evidence commit.
- [ ] Validate pack schema and all artifact digests.
- [ ] Validate Git ancestry and tracked-pack containment.
- [ ] Replay both the legacy and supervisor evaluators.
- [ ] Require exact agreement on decision, means, delta, and CI.
- [ ] Record the ready gate hash in the D2 campaign and M8 activation.

Gate H: D1 integration status is `ready`; no scientific or safety validation
was bypassed.

## 13. Workstream I: freeze and activate the live three-arm study

### I0. Final protocol review

- [ ] Confirm the three arms:
  - fixed-rule configuration;
  - Claude configuration;
  - Claude actor-objective code.
- [ ] Confirm three discovery candidates per arm.
- [ ] Confirm three paired seeds per valid candidate.
- [ ] Confirm one independent confirmation per selected arm candidate.
- [ ] Confirm identical GPU and wall-time caps across arms.
- [ ] Confirm equal LLM caps for both Claude arms and zero fictional LLM budget
  for the fixed-rule arm.
- [ ] Confirm invalid/failed/inconclusive slots are retained and charged.
- [ ] Confirm selection ordering and no cross-arm substitution.
- [ ] Confirm reporting and claim language.

Gate I0: protocol hash is reviewed before any study result is observed.

### I1. Approval and activation

- [ ] Bind baseline, RLinf, reset-set, evaluator, worker, and gate hashes.
- [ ] Approve maximum seed-run count, wall time, GPU cost, LLM cost, and storage.
- [ ] Define cost-notification thresholds and stop conditions.
- [ ] Record approver and UTC activation timestamp.
- [ ] Activate the exact M8 fingerprint.

Gate I1: immutable live activation exists and budgets are enforceable.

## 14. Workstream J: discovery execution

For each of the nine discovery slots:

- [ ] Build the same bounded evidence context available to the appropriate arm.
- [ ] Generate exactly one proposal plus at most one permitted repair.
- [ ] Validate schema, scope, budget, diff/code behavior, and parent lineage.
- [ ] Materialize the candidate in an isolated worktree and commit it.
- [ ] Schedule the three seed contracts on qualified workers.
- [ ] Reconcile attempts, leases, retries, costs, artifacts, and evidence.
- [ ] Run the frozen evaluator.
- [ ] Update only that arm's incumbent when the evaluator returns `KEEP`.
- [ ] Retain invalid, failed, reverted, and inconclusive results.
- [ ] Update the Obsidian task summary after each terminal candidate, not after
  every log line.

Gate J: all three slots in all three arms are terminal and auditable.

## 15. Workstream K: deterministic selection and confirmation

### K0. Select within each arm

- [ ] Require all nine discovery records before selection.
- [ ] Exclude invalid or failed candidates mechanically.
- [ ] Rank by frozen success, delta, cost, wall time, and ID ordering.
- [ ] Persist selected record, commit, and source-record hashes.
- [ ] Report an empty arm honestly if it has no valid candidate.

### K1. Independent confirmation

- [ ] Freeze selected commits; no post-selection edits.
- [ ] Rerun each selected candidate on the common paired confirmation seeds.
- [ ] Use identical baseline, runtime, reset set, evaluator, and budgets.
- [ ] Reject candidate replacement, partial seeds, duplicate seeds, or science
  identity mismatch.
- [ ] Preserve confirmation failures and null outcomes.

Gate K: three valid confirmations exist, or missing/failed arms are explicitly
reported without substitution.

## 16. Workstream L: analysis, delivery, and closeout

- [ ] Produce canonical JSON and trial-level CSV.
- [ ] Produce readable Markdown and static HTML reports.
- [ ] Produce an artifact manifest with SHA-256 and byte counts.
- [ ] Verify every curated artifact independently.
- [ ] Report per-seed outcomes and frozen confidence calculations.
- [ ] Report wall time, GPU time/cost, LLM cost/tokens, invalid proposals,
  failures, retries, and human interventions.
- [ ] Separate engineering conclusions from scientific conclusions.
- [ ] Avoid general claims about agents from three engineering seeds.
- [ ] Update all stale repository documentation.
- [ ] Complete the Obsidian `MI5T8` summary, decisions, validation, and handoff.

Gate L: the final bundle is reproducible, internally reconciled, honestly
scoped, and understandable without chat history.

## 17. Deferred physical ENPIRE work

The following requires a separate protocol and approval after simulation:

- [ ] Real-robot safety envelope and emergency stop.
- [ ] Human-guided construction of rewards and verification.
- [ ] Automated reset reliability and intervention policy.
- [ ] Immutable environment API and restricted agent-visible tools.
- [ ] Hardware rollout provenance and video/sensor evidence.
- [ ] Robot utilization, token utilization, and fleet scheduling metrics.
- [ ] Physical transfer criteria and rollback.

No simulation result automatically authorizes real-hardware execution.

## 18. Immediate ordered checklist

These are the next actions in order:

1. [ ] Preserve and classify the current dirty-worktree files.
2. [ ] Create `integration/d1-d2-agentic-harness` in an isolated worktree.
3. [ ] Reconcile D2 into current D1 without importing stale evidence over the
   current pack.
4. [ ] Pass the combined offline suite and all demo verifiers.
5. [ ] Build the canonical versioned D1 Stage-7 evidence pack from tracked
   evidence.
6. [ ] Run evaluator replay and document the remaining scientific blockers.
7. [ ] Complete one real, tool-free Claude configuration-proposal acceptance
   without GPU execution.
8. [ ] Complete the configuration-mode D1 dry-run/fixture attachment gate.
9. [ ] Design and prove the live PyTorch actor-objective overlay.
10. [ ] Qualify one matched worker/runtime with a bounded Control/Candidate
    rehearsal.
11. [ ] Obtain approval for the final paired-seed D1 run matrix and budget.
12. [ ] Complete matched D1 evidence, open the integration gate, and only then
    activate the M8 live study.

## 19. Program definition of done

The reproducible agentic ENPIRE simulation program is complete only when:

- [ ] D1 and D2 coexist on a reviewed clean branch.
- [ ] The canonical D1 pack is tracked, hashed, and replay-equivalent.
- [ ] Configuration and code proposal modes both pass live attachment tests.
- [ ] Workers execute only immutable harness-owned contracts.
- [ ] Control and candidate evidence is matched across the approved seeds.
- [ ] The D1 gate returns `ready` without exceptions or weakened checks.
- [ ] The M8 study is activated before results and executed within its budget.
- [ ] Discovery, selection, and confirmation are complete for every viable arm.
- [ ] All failures, nulls, costs, tokens, and interventions are retained.
- [ ] Final artifacts rehash successfully from a clean checkout.
- [ ] Claims stay within the evidence.
- [ ] Obsidian task `MI5T8` contains a concise final handoff and links to the
  canonical repository artifacts.
