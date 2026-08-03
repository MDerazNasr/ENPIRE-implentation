# Stage 5 Scientific Baseline Readiness

Status: Stage 5A is complete. The Stage 5B A10 feasibility probe completed with
a measured camera-buffer allocation failure; Reference A and Control B have not
started.

Stage 5A has since completed successfully. See
`docs/stage5a-reduced-checkpoint.md` for its measured result and checkpoint.
The representative A10 probe is documented in
`docs/stage5b-resource-probe.md`.

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
3. **Stage 5B — representative Stage-2 probe (complete):** the A10 reached
   22,598/23,028 MiB sampled VRAM and failed while allocating the parallel
   evaluation camera group. It produced no rollout/performance metric and cost
   `$0.0180` in launcher-attributed time.
4. **Reference A:** evaluate the frozen Stage-1 reference on the fixed 256 IDs.
5. **Control B:** choose the Stage-2 training horizon only after the
   representative probe. Run seed 2026 first; add seeds only after checking
   whether the baseline is non-degenerate and the projected cumulative spend.
6. Report at `$5`, `$10`, `$15`, `$20`, and every further `$5`; stop before
   crossing `$25` without Mohamed's approval.

The retained D1 run manifests now total `$5.7241`, so the `$5` notification
threshold has been crossed. Provider-billed setup/idle time remains additional.

The smallest tier proven insufficient for the unchanged Stage-2 environment
scale is now 24 GB. Re-run the same bounded probe on an A100 40 GB or larger
before choosing the Control-B horizon. A reduced-parallelism A10 profile would
be a separate, preregistered cost experiment rather than a transparent retry.

## Scientific interpretation boundary

A 250-step Stage-1 checkpoint is a budget-limited discovery baseline. It may
be sufficient to reveal whether the downstream pipeline is non-degenerate,
but it is not equivalent to the upstream 2,000-step training contract. Any
comparison and manager update must state this deviation explicitly.

Stage 6 must remain blocked until Reference A and Control B have comparable,
fixed-ID evidence and Control B is non-degenerate enough to supply a tuning
signal.
