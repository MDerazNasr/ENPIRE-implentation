# Stage 5 Scientific Baseline Readiness

Status: Stage 5A and the Stage-5B execution probe are complete. Their original
250-step reference was degenerate. Stage 5C then trained a revised 500-step
checkpoint and measured `33/256` (`12.89%`) fixed-set Reference-A success. The
checkpoint is selected for a bounded, genuinely trained Control B; Stage 6
remains blocked until that control crosses warm-up and produces actor/critic
updates.

Stage 5A has since completed successfully. See
`docs/stage5a-reduced-checkpoint.md` for its measured result and checkpoint.
The representative A10 probe is documented in
`docs/stage5b-resource-probe.md`.
The revised checkpoint gate is documented in
`docs/stage5c-500-checkpoint.md`.

## Why the full profile cannot start silently

The checked-in `stage1_scientific.yaml` preserves the upstream Stage-1 values:
2,000 optimizer steps, micro batch 8, global batch 256, and a checkpoint every
250 steps. On one GPU, each optimizer step therefore requires 32 micro-batches.
The Stage-3 H100 pilot measured about 0.947 seconds per global-batch-8 step,
135.6 seconds of startup, and 59 seconds per full checkpoint.

At `$3.29/hour`, the evidence-based estimates are:

| Stage-1 horizon | Saves | Estimated time | Estimated GPU cost |
| ---: | ---: | ---: | ---: |
| 250 steps | final only | 2.16 hours | `$7.10` |
| 500 steps | final only | 4.26 hours | `$14.03` |
| 2,000 steps | final only | 16.89 hours | `$55.57` |
| 2,000 steps | every 250 | 17.00 hours | `$55.94` |

These estimates apply the required accumulation factor:
`global_batch / micro_batch = 256 / 8 = 32`. The earlier Stage-3 table omitted
that factor and is not valid for the upstream global-batch-256 scientific
profile. Provider setup time and storage/transfer charges remain additional.

The full profile exceeds the project's `$25` hard approval gate. It must not
start under the existing authorization.

## Recommended staged execution

1. **Stage 5A — reduced-budget Stage 1:** run seed 2026 for 250 steps on H100,
   save only the final complete checkpoint, and label it reduced-budget rather
   than upstream-complete. Expected compute is about `$7.10`.
2. **Preserve before shutdown:** put the approximately 10 GB inference actor
   weights in durable/object storage accessible to the A10. Do not repeat the
   slow live H100-to-A10 stream.
3. **Stage 5B — representative Stage-2 probe:** completed on L40S using 16
   parallel environments and sequential epochs while preserving 64 train and
   256 fixed-ID evaluation trajectories. Peak operating allocation was about
   25.2/46.1 GB.
4. **Reference A:** completed on the same fixed 256 IDs with zero success.
5. **Stage 5C revision:** the approved 500-step checkpoint produced `33/256`
   fixed-set success and is selected; no 1,000-step extension is needed before
   testing Stage 2.
6. **Control B gate:** the earlier one-step scratch-RLT probe performed zero
   updates and is not a trained Control B. The next run must retain the
   unchanged 10,000-transition warm-up, cross it, and record actual actor and
   critic updates before any candidate comparison.
7. Report at `$5`, `$10`, `$15`, `$20`, and every further `$5`; stop before
   crossing `$25` without Mohamed's approval.

The Stage-5C launcher ledger reached approximately `$8.77`, so the `$5`
notification threshold has been crossed and the `$10` threshold has not.
Provider-billed setup/idle time remains additional.

The infrastructure and reference-signal gates are resolved. The remaining
blocker is a genuinely trained Control B. At the observed 41 replay transitions
per step, unchanged warm-up would require roughly 244 comparable runner steps
before learning begins; the next protocol must budget for that explicitly.

## Scientific interpretation boundary

A 250-step Stage-1 checkpoint is a budget-limited discovery baseline. It may
be sufficient to reveal whether the downstream pipeline is non-degenerate,
but it is not equivalent to the upstream 2,000-step training contract. Any
comparison and manager update must state this deviation explicitly.

Stage 6 must remain blocked until the selected step-500 checkpoint produces a
non-degenerate, genuinely updated Control B and a defensible comparison signal.
