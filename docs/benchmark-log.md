# Benchmark log

## Phase 1 checkpoint — 2026-07-16

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA L40S, 46 GB usable VRAM
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Budget per run: one 20-step training episode, one actor/critic update, and one
  20-step evaluation episode
- Primary comparison metric: evaluation `success_once`

| Run | Config | Success | Actor loss | BC loss | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `run_000_baseline` | LR `1e-4`, `bc_weight=1.0` | 0.0 | -0.119 | 0.064 | Selected |
| `run_001_adjusted` | LR `1e-4`, `bc_weight=0.8` | 0.0 | -0.109 | 0.067 | Reverted |

The wrapper triggered because baseline success was below the `0.85` target and
reduced reference regularization by 20%. The adjusted run did not improve
success, so the keep-or-revert rule restored the baseline configuration.

**Honest result:** reducing `bc_weight` from `1.0` to `0.8` produced no
meaningful difference in this one-transition smoke test; both evaluations had
zero success.

The actor losses are recorded for observability but are not used to break the
success tie because changing `bc_weight` changes the actor objective itself.
These runs validate orchestration and logging only; they are not a performance
claim.

Artifacts: `results/checkpoint-20260716c/`.

## D1 Stage-5B baseline gate — 2026-08-04

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA L40S, 46,068 MiB usable VRAM, `$0.99/hour`
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Evaluation: 256 fixed reset-state IDs, 500-step horizon, seed 2026
- Execution batching: 16 train environments x 4 epochs; 16 evaluation
  environments x 16 epochs

| Run | Policy route | Train success | Eval success | RLT updates | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `stage5b-l40s-batched16-probe-seed2026-20260804` | Scratch residual actor | `0/64` | `1/256` | `0` | Degenerate probe |
| `stage5b-reference-a-l40s-seed2026-20260804-r2` | Frozen Stage-1 reference | `0/64` | `0/256` | Not applicable | Degenerate reference |

The residual probe recorded only 41 replay transitions against the unchanged
10,000-transition warm-up threshold, so neither actor nor critic trained.

**Honest result:** the L40S profile proves reproducible RLinf/RLT execution,
but the reduced-budget Stage-1 checkpoint and one-step scratch-RLT probe do not
provide a meaningful success signal. Stage 6 was not launched.

Artifacts: `results/stage5b-l40s/`.
Reference-A W&B run: [fmfb666c](https://wandb.ai/mderaznasr-n-a/qualia-rlt-d1/runs/fmfb666c).

## D1 Stage-5C checkpoint gate — 2026-08-04

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA RTX PRO 6000 Blackwell Server Edition, `$1.99/hour`
- Task: ManiSkill `PegInsertionSideWideClearance-v1`
- Stage-1 horizon: 500 optimizer steps, seed 2026
- Evaluation: 256 fixed reset-state IDs, 500-step horizon

| Run | Policy route | Train success | Eval success | RLT updates | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `stage5c-step500-reference-a-seed2026-20260804` | Frozen step-500 reference | `6/64` (`9.38%`) | `33/256` (`12.89%`) | Not applicable | Checkpoint selected |

The run completed in 1,494.47 seconds and cost `$0.8261`; peak sampled VRAM
was 26,286 MiB. Policy switching was disabled and actor/critic update counts
were zero, so this is a clean frozen-reference measurement.

**Honest result:** extending the budget-limited Stage-1 model to 500 steps
produced a non-degenerate but still low `12.89%` fixed-set success rate. This
is sufficient to select the checkpoint for a bounded Stage-2 baseline, but it
is not evidence of Stage-2 RLT improvement and is not equivalent to upstream
2,000-step Stage-1 training.

Detailed evidence: `docs/stage5c-500-checkpoint.md`.

## D1 Stage-5D trained Control B — 2026-08-10

- Run: `stage5d-control-b-h100-recovery-offload-disabled-seed2026-20260809-r2`
- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Project commit: `59bd897a4d2c64cf7fc2b3c3fa8024d31d449c67`
- Hardware: NVIDIA H100 PCIe 80 GB, `$3.29/hour`
- Stage-2 horizon: 100 runner steps, seed 2026
- Evaluation: 256 fixed reset-state IDs, 500-step horizon

| Run | Stage-2 updates | Final train success | Fixed eval success | Runtime | Cost |
| --- | --- | ---: | ---: | ---: | ---: |
| Control B, seed 2026 | Warm-up crossed; 400 critic + 100 actor on final step | `4/64` (`6.25%`) | `18/256` (`7.03%`) | `27.96 h` | `$91.9730` |

The final replay contained approximately 45,000 transitions,
`update_step=30,800`, and `ready_for_online=1`. Fixed-evaluation mean episode
length was `470.30`; the Wilson 95% success interval was `4.49%`--`10.84%`.
The matched fresh-chain Reference A scored `35/256` (`13.67%`), so this Control
was `-6.64` percentage points and 17 successes lower.

**Honest result:** Control B is now a reproducible, genuinely trained baseline,
but seed 2026 provides no evidence that upstream scheduled Stage-2 RLT improves
the frozen reference. Candidate C can test the preregistered BC-weight change,
but one matched seed cannot satisfy the final across-seed keep rule.

Local evidence archive SHA-256:
`c399ebad392c82bb7c13e0be91955c7e5bc72a980ab0fefcab46672a0a978dfc`.
Final compact policy SHA-256:
`0090d1f6c9fb1feb43ea459570872d93eeed92e9c2e1cff871ba3e6050cafd34`.

## D1 Stage-6 Candidate C — 2026-08-24

- Run: `stage6-candidate-c-modal-multiprocess-seed2026-r3`
- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Hardware: NVIDIA RTX PRO 6000 Blackwell Server Edition on Modal
- Stage-2 horizon: segmented `1--60` plus native resume `61--100`, seed 2026
- Evaluation: 256 fixed reset-state IDs, 500-step horizon

| Condition | Fixed eval success | Difference from Control B | Decision |
| --- | ---: | ---: | --- |
| Control B | `18/256` (`7.03%`) | -- | Baseline |
| Candidate C r3 | `32/256` (`12.50%`) | `+5.47` points | `INCONCLUSIVE`; do not promote |

Candidate C completed and its final checkpoint is verified, but the native
resume reset `rlt/update_step` from `16,400` at step 60 to `0` at step 61. It
ended at `15,600` with `ready_for_online=0`, so it never exercised the intended
online BC weight `2.0`. The run also has only one seed and uses a different
runtime/simulator path from Control B.

**Honest result:** the observed `+5.47`-point success difference is promising
but cannot support `KEEP`. The executed schedule was not matched and the
preregistered three-seed interval is missing, so the formal outcome is
`INCONCLUSIVE` and the previous configuration remains the operational default.

Detailed evidence: `docs/stage6-result.md`.

## D1 Stage-6 Corrected Candidate C — 2026-09-01

- Final segment: `stage6-candidate-c-modal-multiprocess-seed2026-r19-resume-96-to-100-eval256`
- Modal app: `ap-803If8zMw4XookkyW9q99S` (completed and stopped)
- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- Final state: step 100, `update_step=31,200`, `ready_for_online=1`
- Evaluation: 256 fixed reset-state IDs, 500-step horizon

| Condition | Fixed eval success | Difference from Control B | Decision |
| --- | ---: | ---: | --- |
| Control B | `18/256` (`7.03%`) | -- | Baseline |
| Corrected Candidate C | `17/256` (`6.64%`) | `-0.39` points | `INCONCLUSIVE` |

The corrected chain preserved the RLT schedule counter through strict audited
sidecars and exercised the intended online route. The final checkpoint has
47,754 exact replay entries/files, 582 episodes, and valid DCP, policy, target,
sidecar, and replay RNG assets. r19 ran 10,818.85 seconds and cost `$9.1059`.

**Honest result:** the 0.8x BC-regularization adjustment produced no meaningful
observed improvement for seed 2026. The preregistered three-paired-seed rule is
not satisfiable yet, so the formal outcome remains `INCONCLUSIVE`. The result
is also provisional because Candidate and Control used different runtime,
simulator, renderer, and batching paths.

Final compact evidence:
`results/d1-evidence-pack/raw/candidate-c-corrected-final-summary.json`.
