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

Fresh-workspace recovery contract: execute Stages 5A--5D and Stage 6 on the
same paid instance before the final export gate. Stage 6 is part of this
uninterrupted chain because Candidate C needs the same selected step-500
Stage-1 actor. It does not initialize from Control-B weights.
The progressive local-download gates in `docs/local-artifact-backup.md` are
mandatory; a remote-only checkpoint is not preserved.

- [x] Obtain explicit approval for the reduced Stage-1 budget.
- [x] Train and verify the 250-step reduced-budget Stage-1 checkpoint.
- [x] Probe upstream-scale Stage-2 environment feasibility on the A10; record
  the measured camera-buffer/VRAM failure without changing the contract.
- [x] Retry the unchanged probe on H100; record the low-VRAM `ErrorDeviceLost`
  camera-group failure without claiming a hardware-capacity result.
- [x] Reject the first batched attempt after a one-environment preflight proves
  the H100 Vulkan device remained lost; require a provider-level restart.
- [x] Reject an A100 40 GB after CUDA passes but NVIDIA Vulkan and SAPIEN's CPU
  rendering fallback both fail before RLinf launch.
- [x] Repeat 64 parallel environments x 4 epochs on a clean A10; record the
  measured 21,979/23,028 MiB camera-buffer failure before rollout.
- [x] Reject 32 parallel environments x 8 epochs after it reaches the same A10
  camera-buffer boundary with all 64 training environments retained.
- [x] Repeat the bounded probe on a graphics-capable 48 GB GPU (prefer A6000;
  L40/L40S or RTX 6000 Ada are acceptable) before Reference A or Control B.
- [x] Evaluate Reference A on the fixed 256-ID set; record `0/256` success.
- [x] Execute the bounded scratch-RLT control probe; record `1/256` success,
  41/10,000 replay transitions, and zero actor/critic updates.
- [x] Apply the non-degenerate-baseline gate and stop with an honest null
  result.
- [x] Run the explicitly revised 500-step Stage-1 checkpoint gate and verify
  its complete actor artifact.
- [x] Evaluate the step-500 Reference A on all 256 fixed IDs; record `33/256`
  success with zero Stage-2 actor/critic updates.
- [x] Select step 500 for the bounded Control-B readiness run; do not extend to
  1,000 steps before testing the remaining Stage-2 uncertainty.
- [x] Download and hash-verify the rebuilt step-250 and step-500 inference
  actors locally before starting long Control-B training.
- [ ] Train/evaluate Control B across approved seeds. Not started because the
  revised reference gate passed, but Control B must first cross the unchanged
  10,000-transition warm-up and demonstrate real actor/critic updates.
- [ ] Download and hash-verify the completed Control-B policy and evidence
  locally before starting Candidate C.
- [ ] Compute per-seed results and uncertainty. Not applicable until a valid
  trained Control B exists.

Gate outcome: the original 250-step reference was degenerate, while the fresh
500-step reference is measurable at `35/256` (`13.67%`). Stage 5 can proceed to
a bounded, genuinely trained Control B. Stage 6 remains blocked until that
control exists.

## Stage 6 — One-factor controller experiment

- [ ] Start from the same verified step-500 Stage-1 actor used by Control B;
  do not initialize Candidate C from the trained Control-B actor/critic.
- [ ] Run Candidate C using the matched protocol.
- [ ] Compute paired candidate-minus-control evidence.
- [ ] Apply the preregistered decision rule.
- [ ] Preserve both accepted and rejected artifacts.
- [ ] Download and hash-verify the completed Candidate-C policy and evidence
  locally.
- [ ] Export and hash the Stage-1 actor, Control-B and Candidate-C policies,
  norm stats, configs, manifests, ledger, and compact raw evidence before the
  shared instance is terminated.

Gate: immutable evidence supports `KEEP`, `REVERT`, or `INCONCLUSIVE`.
The GPU/workspace may be released only after the export hashes match.

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
