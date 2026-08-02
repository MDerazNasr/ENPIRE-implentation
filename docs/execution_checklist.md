# D1 Gated Execution Checklist

Only one stage may be active at a time. The next stage begins after its evidence
gate is reviewed. Paid compute is prohibited in Stages 0 and 1.

## Stage 0 — Freeze contract

- [x] Create `experiment/d1-rlt-baseline` from the known-good Phase-1 commit.
- [x] State the exploratory hypothesis and non-goals.
- [x] Define Reference A, Control B, and Candidate C.
- [x] Preregister primary/secondary metrics.
- [x] Define `KEEP`, `REVERT`, and `INCONCLUSIVE`.
- [x] Disable unsupported expert takeover consistently.
- [x] Record smallest-instance and spending policies.
- [ ] Mohamed reviews and approves the experiment contract.

Gate: all Stage-0 documents are internally consistent, and Mohamed can explain
why the conditions, primary endpoint, and decision rule answer the D1 question.

## Stage 1 — No-GPU infrastructure

- [ ] Add separate pilot/scientific condition configs.
- [ ] Add config/path/placeholder validation and dry-run command output.
- [ ] Add immutable run manifest and local/W&B linkage schema.
- [ ] Add fixed-evaluation specification.
- [ ] Add resource and cumulative-cost monitoring.
- [ ] Add unit tests for commands, provenance, rules, and budget gates.

Gate: all tests pass; Candidate differs from Control only in scheduled BC
weights; dry-run cannot launch paid work.

## Stage 2 — Assets and environment

- [ ] Provision the smallest suitable >=24 GB NVIDIA instance.
- [ ] Record GPU model, hourly price, storage, and launch timestamp.
- [ ] Install/pin RLinf and verify its tree remains unmodified.
- [ ] Verify full model, dataset, norm stats, task, and disk use.
- [ ] Authenticate W&B directly on the pod.
- [ ] Validate CUDA and ManiSkill reset/step.
- [ ] Re-run bounded upstream Stage-1/Stage-2 logging smoke.

Gate: required assets resolve and unmodified upstream metrics appear in W&B and
local evidence.

## Stage 3 — Representative Stage-1 pilot

- [ ] Run bounded checkpoint-producing training.
- [ ] Capture startup and steady-state timing separately.
- [ ] Capture peak VRAM/RAM and disk use.
- [ ] Verify saved actor checkpoint and reload.
- [ ] Project 250/500/1000/2000-step and full-D1 cost.
- [ ] Report each crossed `$5` spending threshold; stop at pilot cap.

Gate: return a valid checkpoint, measured resource profile, and cost proposal;
obtain approval before long training.

## Stage 4 — Stage-2 checkpoint contract smoke

- [ ] Load the pilot Stage-1 checkpoint without fallback.
- [ ] Run bounded fixed-ID training/rollout/evaluation.
- [ ] Verify actor/reference paths and complete metric capture.
- [ ] Link config, manifest, raw log, W&B, JSONL, and checkpoint.

Gate: end-to-end contract passes; label result as smoke only.

## Stage 5 — Scientific reference/control baseline

- [ ] Obtain explicit training/cost approval.
- [ ] Train the approved Stage-1 checkpoint budget.
- [ ] Evaluate Reference A on the fixed set.
- [ ] Train/evaluate Control B across approved seeds.
- [ ] Compute per-seed results and uncertainty.

Gate: baseline is reproducible and non-degenerate, or stop with an honest
failure/null report.

## Stage 6 — One-factor controller experiment

- [ ] Run Candidate C using the matched protocol.
- [ ] Compute paired candidate-minus-control evidence.
- [ ] Apply the preregistered decision rule.
- [ ] Preserve both accepted and rejected artifacts.

Gate: immutable evidence supports `KEEP`, `REVERT`, or `INCONCLUSIVE`.

## Stage 7 — D1 evidence pack

- [ ] Publish commands, configs, tracker/artifact links, run table, and plots.
- [ ] Publish cost/resource accounting and limitations.
- [ ] Write one honest conclusion line.
- [ ] Mark a reproducible known-good commit.

Gate: another engineer can reproduce and audit D1 without live explanation.

## Later, separately approved

- Stage 8 / D2: coding-agent edit boundary, lifecycle, verification, and rollback
  contract.
- Stage 9 / D3-D4: independent multi-GPU coordinator, then bounded coding-agent
  comparison.

