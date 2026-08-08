# Stage 5D Trained Control B

Status: the fresh-chain transition-rate calibration completed successfully on
2026-08-08. The first Control B attempt launched under the cumulative `$130`
hard cap, crossed the replay gate, and then failed at the first subsequent
learner block because RLinf FSDP observed a CPU-resident sharded gradient.
The failed evidence is preserved locally; no retry is approved until the
offload interaction is validated. Candidate C remains blocked.

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

## First Control B attempt (failed, preserved)

Run `stage5d-control-b-h100-chain-100-seed2026-20260808` launched at 01:28 UTC
on the H100 and ran to global step `21/100`. It collected approximately 10,200
replay transitions, crossed the unchanged 10,000-transition gate, and completed
one learner block of 400 critic plus 100 actor updates. The next critic
backward failed with RLinf's unmodified FSDP assertion:
`Expects the sharded gradient to be on cuda:0 but got cpu`. The manifest reports
exit code 255, 20,213.9 seconds elapsed, and `$18.473247` run-attributed cost;
launcher cumulative cost reached about `$53.18`. This is an RLinf
offload/gradient-device failure, not a simulator or GPU-capacity failure.

Compact manifest, command, events, metrics, resources, and run log are
preserved at
`tmp/fresh-chain-20260807/evidence/stage5d-control-b-failed/`. The H100 GPU is
idle and residual Ray workers were stopped. The checked-in Control/Candidate
protocols now disable actor offloading on the 80 GB H100; this is the smallest
configuration-level fix and leaves RLinf's learner code unmodified. The
diagnostic profile `configs/d1/stage2_5d_offload_disabled_diagnostic.yaml`
runs two training steps with a diagnostic warm-up override and no evaluation,
exercising repeated learner blocks before another full paid retry. Its result
is runtime validation, not Control-B scientific evidence.

The diagnostic completed successfully on 2026-08-08: two runner steps in
2,018.4 seconds, `$1.844637`, with two learner blocks (800 critic and 200
actor updates) and no FSDP gradient-device assertion. Peak H100 usage remained
well below capacity. This validates disabling actor offload as the runtime fix;
it does not replace the full 100-step Control run.

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

The three runner steps recorded 472, 411, and 487 replay transitions: 1,370
total, or 456.7 per step on average. Their train-route success counts were
8/64, 11/64, and 6/64. The run correctly performed zero learner updates while
below the unchanged 10,000-transition gate. It completed with exit code zero
in 2,958.3 seconds and cost `$2.70`; cumulative launcher-tracked spend became
`$34.72`.

Using the minimum observed rate of 411 transitions per runner step, crossing
the replay gate requires at most 25 rollout steps. The upstream 30,000-update
warm-up then needs 75 update-bearing steps at the 400-update cap. Therefore 100
uninterrupted steps is the conservative minimum supported by the fresh-chain
measurements. Mean rollout time was 950.7 seconds per step. Including measured
learner overhead and the final fixed evaluation, Control B projects to about
27.7 hours and `$91` on the current `$3.29/hour` H100, bringing cumulative
launcher-tracked cost close to—but below—the `$130` cap.

`configs/d1/stage2_5d_update_throughput_calibration.yaml` is a separate,
non-scientific one-step calibration that schedules exactly 400 warm-up updates
after one normal rollout. It changes only the three bounded RLT schedule values
and runner-step count needed to measure learner throughput. Its output cannot
be used as Control-B evidence; the final Control B must retain every upstream
schedule value listed above.

That calibration completed with 431 replay transitions, 400 critic updates,
and 100 actor updates. Total step time was 283.4 seconds versus 271.5 seconds
spent receiving rollout trajectories, so the complete learner block added
approximately 11.9 seconds. It cost `$0.24`, bringing cumulative tracked spend
to `$9.54`. This confirms that the full run is rollout-bound.

`configs/d1/stage2_5d_control_h100_chain.yaml` is the launch-ready full
protocol: 100 uninterrupted runner steps, the unchanged upstream RLT schedule,
one final 256-fixed-ID evaluation, and a checkpoint at step 100. The bound is
derived from the conservative minimum transition rate plus the unchanged
upstream update schedule. It must run on the same live workspace so the
selected Stage-1 artifact, ledger, and resulting evidence remain together.

## Same-instance Stage 6 continuation

The fresh-workspace recovery plan does not stop after Control B. Once its
step-100 checkpoint and fixed-ID evaluation pass, launch Candidate C on the
same instance using the same selected step-500 Stage-1 actor and matched
protocol. Candidate C is an independent Stage-2 training run with only the
preregistered BC-schedule change; it must not inherit Control-B actor/critic
weights.

After both runs finish, apply the paired keep/revert rule and complete the
artifact export gate before terminating the instance. The required export is
the Stage-1 inference actor, norm stats, both final Stage-2 policies, resolved
configs, manifests, cost ledger, and compact logs/evidence. Stage 7 packaging
can then finish locally without GPU access.

Local preservation is progressive, not deferred to shutdown. Both Stage-1
inference actors must already be downloaded and verified before Control B;
Control B must be downloaded and verified before Candidate C; Candidate C must
be downloaded and verified before the shutdown gate. See
`docs/local-artifact-backup.md`. The large Stage-1 optimizer shards are
excluded because Stage 2 needs the inference actor and the local machine does
not have space for every reproducible training-state artifact.

## Resume limitation

Pinned RLinf checkpoints save the Stage-2 model, optimizers, target model, and
replay buffer. At this commit, they do not persist the RLT worker's
`update_step`, `total_transitions_added`, or warm-up-ready counters. Reloading
a checkpoint therefore resets the routing/update schedule even though replay
data is restored. Stage 5D must be treated as one uninterrupted run unless a
separately reviewed state-preservation mechanism is added. We will not modify
RLinf silently to bypass this constraint.

## Budget gate

The launcher now retains an explicit cumulative `$150` hard cap and reports
`$5` increments. This revised cap covers the preserved failed attempt, the
offload diagnostic, and one full Control retry with a small margin; the launcher
will terminate the retry if the cap is reached. Candidate C is expected to
require a second approximately `$91` run, so it remains outside this cap and
requires separate authorization. Provider auto-shutdown must be extended
beyond 30 hours because the launcher cannot alter the provider dashboard.
