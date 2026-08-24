# Stage 6R: RLT Schedule-Resume Repair

Status on 2026-08-24: the strict RLT schedule-state repair is implemented,
locally regression-tested, and verified by a bounded two-process Modal gate.
The gate passed. This closes the resume-correctness blocker, but it is not a
Candidate-C result and does not change the `INCONCLUSIVE` decision for
Candidate r3.

## Root cause

Candidate r3 showed that RLinf's native checkpoint was sufficient to restore
the learned model, optimizers, learning-rate schedulers, target model, global
RNG state, and replay buffer, but not the RLT schedule's Python bookkeeping.
`RLTACFSDPPolicy` initialized those counters to zero in every new process, and
the native save/load path did not serialize them. Consequently, r3 resumed at
runner step 61 with `rlt/update_step=0` after ending step 60 at 16,400. The
resumed process started a second warm-up and never exercised the intended
online actor weights.

The repair leaves the pinned RLinf source at
`c90951a0c799a750cb5294ed10587c61cc2af8bf` unchanged. An opt-in runtime patch
wraps the synchronous RLT policy's native checkpoint methods when
`QUALIA_RLT_RESUME_STATE=1`. The native checkpoint is written or loaded first;
the project-owned sidecar then saves or restores only the missing RLT schedule
state.

## Exact state contract

Each actor rank writes an atomic JSON sidecar at:

```text
global_step_<n>/actor/sac_components/rlt_schedule_state/rank_<rank>.json
```

The sidecar contains the following eight counters exactly:

| Field | Meaning in the resume contract |
| --- | --- |
| `update_step` | Cumulative RLT optimizer-update count used by the actor-weight schedule |
| `transitions_since_train` | Transitions accumulated since the previous scheduled training event |
| `episodes_since_train` | Episodes accumulated since the previous scheduled training event |
| `total_transitions_added` | Cumulative transitions admitted to replay |
| `total_episodes_added` | Cumulative episodes admitted to replay |
| `_warmup_ready_total_transitions` | Transition-count anchor captured when warm-up first becomes ready; nullable |
| `_warmup_ready_total_episodes` | Episode-count anchor captured when warm-up first becomes ready; nullable |
| `pending_update_budget` | Scheduled updates not yet consumed |

It also records:

- schema version, checkpoint runner step, actor rank, and actor world size;
- the pinned RLinf commit;
- the schedule-defining configuration (`loss_type`, `update_epoch`,
  `critic_actor_ratio`, `rlt_schedule`, and `actor_weight_schedule`) and its
  SHA-256 fingerprint;
- the replay buffer's dedicated Torch generator state, encoded as base64.

Loading fails closed if the sidecar is missing or malformed, or if its schema,
checkpoint step, rank, world size, RLinf commit, schedule fingerprint, or
counter schema differs from the running job. A successful restore emits a
machine-readable `QUALIA_RLT_RESUME_STATE=...` marker. Existing checkpoints
created before this repair do not have enough information for an exact repair
and cannot be used as strict corrected-resume inputs.

## Bounded gate design

The integration gate intentionally used the smallest useful workload: one
training environment, one rollout epoch, a 20-step episode horizon, replay
minimum size one, and at most one optimizer update per runner step. It created
a source checkpoint at runner step 1, ended that process, and resumed a fresh
process to runner step 2. The actor schedule was reduced to one warm-up update
with no ramp so a reset would be unambiguous:

| Phase | Expected logged `update_step` | Expected BC / Q weights | Expected final sidecar |
| --- | ---: | ---: | ---: |
| Source step 1 | `0` before its update | `5.6 / 0.05` warm-up | `update_step=1` |
| Resumed step 2 | `1` before its update | `2.0 / 0.45` online | `update_step=2` |

This is a schedule-resume integration test only. It does not run the fixed
256-trajectory evaluation and must not be interpreted as policy-quality
evidence.

## Attempts r1 through r4

| Attempt | Outcome | Finding and action |
| --- | --- | --- |
| r1 | Failed safely before rollout | A stale Modal-volume/run-directory collision prevented a clean gate attempt; no training evidence was accepted. |
| r2 | Failed safely before rollout | Fresh run IDs removed the collision, but RLinf's in-process Ray startup timed out. |
| r3 | Failed the gate assertion | Explicitly starting and health-checking the Ray head fixed bootstrap. The rollout produced no RLT transition, however, so the saved sidecar correctly contained `update_step=0`. |
| r4 | Passed | Forcing the gate's train policy switch to `task_mode=critical_phase` and `trigger_mode=always_on` guaranteed one real replay transition plus one actor update and one critic update in each segment. |

The r1 collision and r2 Ray failure were execution problems separate from the
resume-state bug. The durable Ray fix runs `ray start --head`, checks
`ray status`, emits `QUALIA_RAY_HEAD=started-and-healthy`, and prints bounded
GCS/raylet diagnostics if startup fails.

## Passed r4 evidence

The source process logged:

- `rlt/update_step=0`, `rlt/ready_for_online=0`, and
  `actor/actor_weight_in_warmup=1`;
- `actor/bc_weight=5.6` and `actor/q_weight=0.05`;
- one admitted transition, one actor update, and one critic update, followed
  by a step-1 sidecar with `update_step=1`, `total_transitions_added=1`, and
  `total_episodes_added=1`.

The continuation process emitted an explicit restore marker with
`previous_update_step=0` and `restored_update_step=1`. It then logged:

- `rlt/update_step=1`, `rlt/ready_for_online=1`, and
  `actor/actor_weight_in_warmup=0`;
- `actor/bc_weight=2.0` and `actor/q_weight=0.45`;
- a second admitted transition, actor update, and critic update, followed by a
  step-2 sidecar with `update_step=2`, `total_transitions_added=2`, and
  `total_episodes_added=2`.

Both checkpoints included the native DCP metadata, actor weights, target
model, replay index, and the new rank-0 schedule sidecar. The schedule
fingerprint was
`dff74668a66b695a0e63c4d5a919b772fa88556b9287ca7978695eb982a91600`
in both processes. This proves that the schedule counter and warm-up-to-online
weight transition survive a real process boundary in the tested runtime.

The Modal workspace total moved from `$153.20` metered / `$123.08` billed
before this repair gate to `$154.11` metered / `$123.99` billed after the
r1-r4 attempts, a `$0.91` increase on both views. These are workspace-cycle
totals, not a provider-isolated cost attribution for r4 alone, and they must
not be added to Candidate r3's launcher estimate as though they were the same
accounting measure. Modal app `ap-qwHdysi3czho3XNEgCWafX` is stopped.

## Implementation provenance

The repair was developed in four small, pushed commits:

| Commit | Purpose |
| --- | --- |
| `b364e7b` | Add the strict sidecar, opt-in runtime patch, bounded gate profile, Modal assertions, and local tests |
| `693b7d0` | Retry with fresh gate run IDs so failed-attempt directories cannot be mistaken for new evidence |
| `8f3b6b7` | Start and health-check Ray explicitly in the Modal launcher |
| `b8e1908` | Force one real RLT transition/update and define the passing r4 run IDs |

The machine-readable result is retained on the `enpire-workspace` Modal
volume at `/workspace/results/stage6r-schedule-resume-gate.json`. The
corresponding run directories are:

```text
results/d1/stage6r-schedule-resume-source-seed2026-r4/
results/d1/stage6r-schedule-resume-continuation-seed2026-r4/
```

## Reproduction

From a checkout containing the four commits and with the Modal profile set to
the workspace owner:

```bash
git checkout b8e1908
python3 -m pytest -q
modal profile activate deraznasr776
modal run modal_stage6.py --target schedule-resume-gate
modal volume get enpire-workspace \
  results/stage6r-schedule-resume-gate.json \
  /tmp/stage6r-schedule-resume-gate.json --force
python3 -m json.tool /tmp/stage6r-schedule-resume-gate.json
```

Before spending GPU time, verify that `enpire-workspace` contains the
canonical Stage-1 actor at `/workspace/checkpoints/stage1-step-500-actor` with
SHA-256
`b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3`.
The launcher also requires the norm-stats file with SHA-256
`d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd`.

At this commit, `modal_stage6.py` embeds the norm-stats file and the recovered
Control-B ledger from paths under the untracked `tmp/` evidence tree. A truly
clean-clone reproduction therefore also requires restoring those two exact
inputs or refactoring them into tracked/bootstrap-managed artifacts. The
launcher verifies the large actor and norm-stats hashes before execution, but
this local-input dependency remains a packaging limitation.

## Remaining limitations and next action

- The patch is project-owned and opt-in; it has not been contributed to or
  validated against RLinf versions other than the pinned commit.
- The paid gate used one actor rank, one environment, two transitions, and two
  updates. It verifies continuity, not long-run learning behavior, simulator
  determinism, multi-rank state, or policy quality.
- The sidecar restores RLT counters and the replay buffer's dedicated Torch
  generator. It does not claim bitwise identity for simulator state across
  separate processes.
- Pre-repair r3 remains scientifically invalid, and one corrected seed would
  still be insufficient for the preregistered three-seed decision rule.

The next safe action is a fresh corrected Candidate-C r4 run from the
canonical Stage-1 actor. Segment 1 must create sidecar-equipped checkpoints;
segment 2 must refuse to start without a valid sidecar and must show a
non-zero restored `update_step` before the intended online actor weights are
evaluated.
