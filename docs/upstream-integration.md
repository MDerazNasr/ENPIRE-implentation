# Upstream RLinf integration record

## Validated environment

- RLinf commit: `c90951a0c799a750cb5294ed10587c61cc2af8bf`
- GPU: NVIDIA L40S
- Python: 3.11
- PyTorch: `2.6.0+cu124`
- Frozen model: `lerobot/pi05_base`
- Dataset: first eight episodes of
  `RLinf/rlt-maniskill-PegInsertionSide-v1-400-succ`, with metadata reduced to
  565 frames and the upstream `norm_stats.json`

The official installer completed with:

```bash
bash requirements/install.sh embodied \
  --model openpi \
  --env maniskill_libero \
  --torch 2.6.0 \
  --no-flash-attn \
  --no-apex \
  --install-rlinf
```

RLinf remained clean after installation and execution.

## Upstream smoke evidence

Stage 1 used upstream config `maniskill_rlt_stage1_sft_openpi_pi05` with only
bounded-run and local-path overrides: batch size 1, one optimizer step, no
checkpoint save, local model/dataset paths, and logging disabled except stdout.
The stock model settings remained `precision=null`, `train_expert_only=false`,
and gradient checkpointing disabled.

Visible Stage-1 metrics:

- `train/loss=4.23`
- `train/rlt_loss=4.17`
- `train/vla_loss=0.062`
- `train/grad_norm=2.37`

Stage 2 used upstream config `maniskill_rlt_stage2_ac_mlp`, one environment,
one short rollout, and `rollout.expert_model=null` because the checked-in expert
path is a placeholder. It emitted `success_once=0.0`, `return=0.0`, and
`episode_len=10.0`.

The upstream `runner.only_eval=true` path failed before rollout because it
attempted weight synchronization with a null rollout `weight_syncer`. Running
the same config for one normal iteration with `val_check_interval=1` produced
the evaluation table without modifying RLinf.

Raw evidence is stored under `results/upstream-smoke/`.

## Phase 1 wrapper smoke scope

The wrapper uses Stage-2 `algorithm.bc_weight` as reference regularization and
`actor.optim.lr` as learning rate. It forces the critical phase for a bounded
smoke run and lowers replay warmup to one transition so one actor/critic update
is visibly logged.

The 20-step budget is necessary: the first action chunk initializes routing;
the second supplies one replayable transition. A 10-step attempt correctly ran
the environment but yielded `transition_count=0` and was rejected as invalid.

For storage reasons this checkpoint uses the base pi0.5 directory as the RLT
feature-model smoke input. A scientific experiment must first save a trained
Stage-1 RLT checkpoint and point `rollout.rlt_feature_model.model_path` at its
`actor` directory, as required by the upstream RLT documentation.
