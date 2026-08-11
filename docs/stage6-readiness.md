# Stage 6 Candidate-C Readiness Audit

Status on 2026-08-12: the scientific profile is matched and dry-resolves
correctly, but a paid Candidate-C launch is **not yet authorized or
operationally ready**. No GPU was launched during this audit.

## Scientific boundary

Candidate C is an independent Stage-2 run. Both Control B and Candidate C
load the same verified Stage-1 step-500 actor through
`rollout.rlt_feature_model.model_path=${STAGE1_CHECKPOINT}`. Candidate C does
not set `runner.resume_dir`, `runner.ckpt_path`, `actor.model.model_path`, or
`rollout.model.model_path`, so it cannot inherit the trained Control-B
actor/critic.

The complete Hydra-override comparison has exactly two differences:

| Field | Control B | Candidate C |
| --- | ---: | ---: |
| `algorithm.actor_weight_schedule.warmup_bc_weight` | `7.0` | `5.6` |
| `algorithm.actor_weight_schedule.online_bc_weight` | `2.5` | `2.0` |

Everything else is matched: pinned RLinf commit, seed 2026, upstream replay
and update schedules, Q weights, 100 runner steps, 64 train trajectories per
step, 256 fixed-ID evaluation trajectories, 500-step horizon, disabled expert
takeover, disabled actor offload, and CPU weight transport. This is the
preregistered 0.8x BC-schedule intervention; it is not a coding-agent change.

The upstream RLT guide supports this boundary: Stage 2 freezes the Stage-1
feature model and trains the compact actor/critic, while a scratch Stage-2 run
keeps its Stage-2 model path null and points `rollout.rlt_feature_model` at the
Stage-1 actor.

## Preserved inputs

The local Stage-1 input was reverified during this audit:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| Stage-1 step-500 `full_weights.pt` | `10,015,912,759` | `b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3` |
| Official dataset `norm_stats.json` | `2,149` | `d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd` |

The normalization statistics were restored from the official RLinf
`rlt-maniskill-PegInsertionSide-v1-400-succ` dataset at pinned dataset commit
`2b92d5ef3fe274d30219130133f9e34c7ab91ebf`; their hash matches the asset used
by the completed chain. The unrelated reconstructed file
`tmp/norm_stats_reconstructed.json` is not canonical and must not be used.

## Dry-run result

The exact Candidate-C profile dry-resolved with seed 2026, the local Stage-1
actor, 100 training steps, and 256 fixed evaluations. The launcher exited zero,
printed `DRY RUN ONLY`, and created no run directory. A paid launch still
requires both `--execute` and `--acknowledge-paid-run`, plus valid paths and an
exact pinned RLinf checkout.

The resolved Candidate config SHA-256 was
`33e5e4a020961b27ee211cc6c784dab47af18f2dfc13d7936322f86916bec500` at
project commit `32cbfb2fe65931668663b60bbece314767e5fbae`. This hash describes
the pre-authorization profile with the safe `$150` cap and will change if its
operational budget fields are explicitly updated.

## Launch blocker and cost decision

The preserved append-only ledger totals `$189.824932`. Candidate C still has
the earlier cumulative cap of `$150`. The launcher's pre-process cost check
therefore evaluates `189.824932 >= 150` and rejects the run before creating a
run directory or starting RLinf.

This is the correct safe behavior. Do not remove or raise the Candidate cap
without a fresh explicit spend decision. The matched Control B required
`27.96` hours and `$91.9730` on an H100 PCIe at `$3.29/hour`; using that as the
best observed estimate, one Candidate seed would bring tracked cumulative
spend to about `$281.80`. Provider uptime/setup may add cost not attributed by
the launcher.

Before a paid launch:

1. Mohamed approves the Candidate-C spend and cumulative cap.
2. Update only Candidate C's operational budget fields; do not change its
   scientific fields.
3. Provision a graphics-capable GPU workspace, restore and hash-check the two
   inputs above, pin RLinf to `c90951a0c799a750cb5294ed10587c61cc2af8bf`,
   and pass the live Vulkan/ManiSkill preflight.
4. Restore the `$189.824932` ledger, dry-run again, and launch exactly one
   seed-2026 Candidate run.
5. After completion, download and hash the Candidate policy and full compact
   evidence before releasing the workspace.

Seed 2026 can provide a matched provisional comparison with Control B. It
cannot produce the preregistered three-seed keep/revert conclusion by itself;
that result must remain `INCONCLUSIVE` until the approved seed set exists.
