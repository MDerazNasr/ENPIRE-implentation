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

- [x] Add separate pilot/scientific condition configs.
- [x] Add config/path/placeholder validation and dry-run command output.
- [x] Add immutable run manifest and local/W&B linkage schema.
- [x] Add fixed-evaluation specification.
- [x] Add resource and cumulative-cost monitoring.
- [x] Add unit tests for commands, provenance, rules, and budget gates.

Gate: all tests pass; Candidate differs from Control only in scheduled BC
weights; dry-run cannot launch paid work.

## Stage 2 — Assets and environment

- [x] Audit all profiles against a fresh checkout of the pinned RLinf commit.
- [x] Correct Stage-1 SFT versus Stage-2 embodiment launch boundaries.
- [x] Verify Hydra override paths and Reference-A routing semantics in source.
- [x] Provision the smallest suitable >=24 GB NVIDIA instance.
- [x] Record GPU model, hourly price, storage, and launch timestamp.
- [x] Install/pin RLinf and verify its tree remains unmodified.
- [x] Verify full model, dataset, norm stats, task, and disk use.
- [x] Authenticate W&B directly on the pod.
- [x] Validate CUDA and ManiSkill reset/step.
- [x] Re-run bounded upstream logging smoke and preserve its metrics.

Gate: required assets resolve and unmodified upstream metrics appear in W&B and
local evidence.

## Stage 3 — Representative Stage-1 pilot

- [x] Test the declared profile on the minimum 24 GB tier; A10 failed during
  AdamW-state initialization with measured OOM evidence.
- [x] Run bounded checkpoint-producing training.
- [x] Capture startup and steady-state timing separately.
- [x] Capture peak VRAM/RAM and disk use.
- [x] Verify saved actor checkpoint and reload.
- [x] Project reduced and full Stage-1 budgets with accumulation/save overhead.
- [x] Capture launcher-attributed cost; no Stage-3 `$5` threshold was crossed.

Gate: return a valid checkpoint, measured resource profile, and cost proposal;
obtain approval before long training.

## Stage 4 — Stage-2 checkpoint contract smoke

- [x] Load the pilot Stage-1 checkpoint without fallback.
- [x] Run bounded fixed-ID training/rollout/evaluation.
- [x] Verify actor/reference paths and complete metric capture.
- [x] Link config, manifest, raw log, local ledger, and checkpoint.

Gate: end-to-end contract passes; label result as smoke only.

## Stage 5 — Scientific reference/control baseline

- [x] Obtain explicit approval for the reduced Stage-1 budget.
- [x] Train and verify the 250-step reduced-budget Stage-1 checkpoint.
- [x] Probe upstream-scale Stage-2 environment feasibility on the A10; record
  the measured camera-buffer/VRAM failure without changing the contract.
- [x] Retry the unchanged probe on H100; record the low-VRAM `ErrorDeviceLost`
  camera-group failure without claiming a hardware-capacity result.
- [x] Reject the first batched attempt after a one-environment preflight proves
  the H100 Vulkan device remained lost; require a provider-level restart.
- [ ] Validate 256 fixed-ID evaluations as 64 parallel environments x 4 epochs.
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
