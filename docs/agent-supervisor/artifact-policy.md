# Evidence, Artifact, and Documentation Policy

Status: Milestone 0 contract.

## 1. Goals

The evidence system must make it possible to reconstruct what was proposed,
what actually ran, what it cost, what happened, and why a deterministic
decision was made. It must also prevent large artifacts, credentials, and
private transcripts from being committed accidentally.

## 2. Evidence tiers

### Tier 1 — compact records tracked in Git

- schema and protocol versions;
- campaign specification and approval record, excluding secrets;
- proposal and context hashes plus compact approved context summary;
- project, incumbent, candidate, and RLinf commits;
- patch/config and resolved-command hashes;
- run manifest and terminal status;
- normalized per-seed metrics and evaluator decision;
- resource/cost/token summary;
- artifact index containing W&B/object-store identifiers and checksums;
- milestone report, limitations, and honest conclusion.

Tier-1 records are append-only once a run reaches a terminal state. Corrections
are new superseding records; historical files are not silently overwritten.

### Tier 2 — experiment tracker or artifact storage

- full structured metric time series;
- raw stdout/stderr and environment diagnostics;
- complete resolved configuration;
- plots and rollout videos;
- checkpoints and replay buffers when retention is approved;
- resource samples and profiler output.

W&B is the primary hosted index for the initial system. A local artifact index
and hashes remain sufficient to detect a missing or mismatched hosted object.

### Tier 3 — ephemeral

- disposable worktrees;
- dependency/build caches;
- intermediate downloads;
- incomplete checkpoints that are not required for failure analysis;
- raw unbounded LLM scratch output not included in the structured response.

Tier-3 material may be removed after its terminal manifest and necessary
failure evidence are preserved.

## 3. Required run record

Every real run must include:

- campaign/trial/arm IDs and parent incumbent;
- timestamps, host, GPU, software and driver/runtime identifiers;
- exact command, working directory, commits, config, seed, task, reset-set hash,
  checkpoint/model/dataset identifiers, and evaluator version;
- status, exit code, elapsed and billable time;
- primary/secondary metrics and missing-data flags;
- peak VRAM/RAM/disk and cost;
- agent provider/model, proposal latency, token count, and LLM cost;
- tests, scope validation, and integrity checks;
- decision, reason, promotion/reversion record, and artifact links/hashes.

An LLM-written summary is optional metadata and never substitutes for these
fields.

## 4. Privacy and secrets

Never place the following in Git, agent context, W&B notes, reports, or demo
recordings:

- SSH private keys, API tokens, W&B credentials, provider tokens, or cookies;
- private addresses, contract documents, or unrelated personal information;
- raw meeting/Discord transcripts;
- private infrastructure URLs or host details not needed for reproducibility.

Requirements derived from private discussions are paraphrased and dated. Local
paths shown in public reports are normalized to logical asset identifiers.

## 5. Decision and process documentation

For every milestone:

1. update the requirements matrix when coverage changes;
2. add an ADR before reversing an established architecture decision;
3. record files changed, tests run, results, unresolved risks, and actual effort;
4. update the Obsidian task note with a concise resume-ready handoff;
5. stop for Mohamed's review before starting the next milestone.

For every experiment campaign:

1. preregister the question, arms, budgets, metrics, and evaluator;
2. preserve all valid, invalid, failed, negative, and null trials;
3. generate reports mechanically from evidence;
4. distinguish discovery, confirmation, smoke, replay, and synthetic results;
5. state one conclusion no stronger than the evidence permits.

## 6. Retention

- Keep compact manifests, results, decisions, and provenance indefinitely in
  the project history.
- Keep promoted checkpoints and all confirmation evidence.
- Keep failed-run diagnostics sufficient to explain the failure.
- Replay buffers and large discovery checkpoints may be pruned only after their
  retention decision and hashes are recorded.
- Never delete or hide a negative result to simplify the final comparison.

## 7. Report outputs

The final deliverable will generate:

- machine-readable JSON and CSV tables;
- a Markdown report suitable for repository review;
- a static HTML report/dashboard for the demo;
- plots of policy, systems, cost, and agent-efficiency metrics;
- an artifact and reproducibility index;
- a recorded demo fallback linked to the same campaign IDs.
