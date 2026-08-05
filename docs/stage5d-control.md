# Stage 5D Trained Control B

Status: started on 2026-08-05 with a three-runner-step transition-rate
calibration. The full trained Control B has not launched yet.

## Objective

Train the unmodified RLinf Stage-2 RLT actor/critic from scratch using the
selected step-500 Stage-1 feature checkpoint. Stage 5D is complete only when
the run crosses the upstream replay warm-up, performs real actor and critic
updates, and evaluates the resulting policy on all 256 fixed reset-state IDs.

This is still Control B. It retains the upstream scheduled weights:

- warm-up BC/Q weights: `7.0` / `0.05`;
- online BC/Q weights: `2.5` / `0.45`;
- replay warm-up minimum: 10,000 transitions;
- post-collection warm-up: 30,000 critic updates;
- maximum updates per runner step: 400;
- online cadence: five transitions per five-update epoch.

Candidate C and the rule-based keep/revert comparison remain blocked until
this control exists.

## Calibration contract

`configs/d1/stage2_5d_transition_calibration.yaml` runs three training-only
runner steps with the selected checkpoint, 16 parallel environments x four
epochs, 500-step episodes, actor offload, CPU patch transport, and seed 2026.
It disables evaluation and checkpoint saves for the calibration only. It does
not override replay warm-up, update cadence, policy switching, or actor/critic
hyperparameters.

The calibration measures:

- replay transitions recorded per runner step;
- elapsed rollout time per runner step;
- peak GPU memory;
- whether the selected reference changes critical-phase reachability;
- revised uninterrupted warm-up time and cost.

## Resume limitation

Pinned RLinf checkpoints save the Stage-2 model, optimizers, target model, and
replay buffer. At this commit, they do not persist the RLT worker's
`update_step`, `total_transitions_added`, or warm-up-ready counters. Reloading
a checkpoint therefore resets the routing/update schedule even though replay
data is restored. Stage 5D must be treated as one uninterrupted run unless a
separately reviewed state-preservation mechanism is added. We will not modify
RLinf silently to bypass this constraint.

## Budget gate

The launcher retains the cumulative `$25` cap and reports `$5` increments.
The earlier authorization to exceed `$25` applied only to Stages 5A and 5B.
The calibration may run inside the current cap; the full uninterrupted Control
B must not launch if its revised projection crosses `$25` without explicit
approval.
