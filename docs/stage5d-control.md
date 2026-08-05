# Stage 5D Trained Control B

Status: the transition-rate calibration completed successfully on 2026-08-05.
The full trained Control B has not launched yet because the current-GPU
projection exceeds the cumulative `$25` approval boundary.

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

## Transition calibration result

The three runner steps recorded 255, 274, and 426 replay transitions: 955
total, or 318.3 per step on average. Their train-route success counts were
10/64, 7/64, and 10/64. The run reached the actor phase during rollout and
correctly performed zero learner updates while below the unchanged 10,000
transition gate. It completed with exit code zero in 939.9 seconds and cost
`$0.52`; cumulative tracked spend became `$9.29`.

At the measured mean, the replay gate is approximately 32 runner steps away.
The upstream 30,000-update warm-up then needs at least 75 update-bearing runner
steps at the 400-update cap, making approximately 107 steps the optimistic
minimum. Rollout time alone projects to about 8.1 hours and `$16.1` on the
current `$1.99/hour` RTX PRO 6000, before learner-update and final-evaluation
time. That would exceed the remaining `$15.71` budget.

`configs/d1/stage2_5d_update_throughput_calibration.yaml` is a separate,
non-scientific one-step calibration that schedules exactly 400 warm-up updates
after one normal rollout. It changes only the three bounded RLT schedule values
and runner-step count needed to measure learner throughput. Its output cannot
be used as Control-B evidence; the final Control B must retain every upstream
schedule value listed above.

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
