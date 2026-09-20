# E1 Checkpoint Evaluation Preflight

Status: **review-only; evaluation and paid execution are not authorized**

Obsidian task: `MI5T8`

## Purpose

Finish the development-only portion of G0 E1 by evaluating the approved
seed-2026 Stage-1 checkpoints at steps 250, 500, 1000, and 2000. Each
checkpoint receives exactly 256 outcomes from the frozen development reset
artifact. Final resets are forbidden.

This preflight does not evaluate a checkpoint, download private checkpoint
bytes, contact a provider, launch an instance, select a baseline, enter E2, or
promote a policy.

## Frozen execution shape

- One freshly qualified H100 PCIe worker, used sequentially.
- Four evaluation runs in the order `250`, `500`, `1000`, `2000`.
- Exactly 16 parallel environments and 16 rollout epochs per checkpoint.
- Exactly 256 development outcomes per checkpoint, at a 500-step horizon.
- No training environment, expert model, policy switch, final reset, or retry.
- Each checkpoint must be downloaded by a harness-owned command from its exact
  versioned S3 objects and must pass all recorded size and SHA-256 checks before
  loading.
- The worker writes raw evaluation evidence only. It cannot select a baseline.
- After all four runs are terminal, the create-only deterministic selector may
  consume their frozen evidence under a distinct selection authorization.

## Provisional budget

The existing frozen evaluation configuration caps one checkpoint at `$10`.
This preflight therefore proposes a maximum of 3 hours and `$10` for each of
four sequential runs: 12 aggregate GPU-hours and `$40` aggregate provider
compute. There is no retry allowance. The previously observed Lambda H100 PCIe
rate of `$3.29/hour` is a planning input only and must be read back from the
new instance before approval and launch.

The operator must provision at least 250 GiB of free local storage: about
149.27 GiB for the four checkpoint directories plus image, source, runtime,
logs, and reconciliation margin. Downloads and evidence writes must be
create-only. No model artifact may leave the approved evaluator-account
evidence path except to the explicitly approved worker.

## Required prelaunch gates

1. Bind a new instance ID, IP, region, hourly price, auto-shutdown time, GPU,
   driver, Docker runtime, free storage, and exact image ID.
2. Verify zero pre-existing containers and zero GPU compute processes.
3. Verify source commit `907ce489d669ef12aa32f7eca819331ad6b448bc`,
   RLinf commit `c90951a0c799a750cb5294ed10587c61cc2af8bf`, the
   evaluation config, runner, frozen reset adapter, normalization statistics,
   and development reset hashes.
4. Under a download-only role, enumerate exactly the 16 recorded checkpoint
   object versions and download only those versions. Verify every byte count
   and SHA-256 before use.
5. Compose the four commands without launching them and prove that each binds
   one checkpoint, the development reset artifact, 256 outcomes, and the
   evaluation-only runner.
6. Confirm the evidence destinations are empty and create-only.
7. Obtain a separate exact authorization naming the finalized preflight hash,
   instance, four runs, 12-hour/`$40` aggregate caps, and no retry.

## Terminal requirements

Every run must retain its resolved configuration, command, checkpoint file
manifest, reset/evaluator/runtime identities, raw per-outcome evidence,
normalized metric, start/finish times, exit code, telemetry, cost, logs, and a
SHA-256 manifest. Failed, interrupted, partial, and inconclusive runs remain in
the ledger. Missing or duplicate outcomes, fallback loading, identity drift,
or any final-reset reference makes E1 inconclusive.

## Claim boundary

Successful completion may show which checkpoint has the highest frozen
development success and whether any checkpoint clears the `0.05`
non-degeneracy floor. Under single-operator protected mode, that is preliminary
development evidence only. It does not establish independent evaluation,
Control/Candidate improvement, agent value, E2 readiness without a separate
gate, or promotion authority.

## Authorization form for the later execution step

Do not use this text until a fresh instance-specific preflight has replaced all
bracketed fields:

> I approve four sequential E1 development checkpoint evaluations on instance
> `[INSTANCE_ID]`, bound to preflight `[FINAL_PREFLIGHT_SHA256]`, source
> `907ce489d669ef12aa32f7eca819331ad6b448bc`, and checkpoints 250, 500,
> 1000, and 2000. Each run may evaluate exactly 256 frozen development outcomes
> with a maximum of 3 hours and $10; the aggregate maximum is 12 GPU-hours and
> $40, with no retry. I approve download of only the recorded checkpoint object
> versions to that worker and create-only upload of evaluation evidence to the
> reviewed evidence prefix. This does not authorize final-reset access,
> checkpoint selection, E2, additional training, policy promotion, or any other
> provider or infrastructure action.

