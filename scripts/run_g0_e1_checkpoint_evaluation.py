#!/usr/bin/env python3
"""Evaluate one E1 checkpoint without constructing any training actor worker."""

from __future__ import annotations

import json
import os

import hydra
import torch.multiprocessing as mp
from omegaconf import OmegaConf, open_dict

from envs.e1_frozen_development_env import install_e1_frozen_development_adapter
from rlinf.config import validate_cfg
from rlinf.runners.embodied_eval_runner import EmbodiedEvalRunner
from rlinf.scheduler import Cluster
from rlinf.utils.placement import HybridComponentPlacement
from rlinf.workers.env.env_worker import EnvWorker
from rlinf.workers.rollout.hf.huggingface_worker import MultiStepRolloutWorker
from supervisor.e1_sharded_evaluation import SHARD_SIZE, shard_spec


mp.set_start_method("spawn", force=True)
install_e1_frozen_development_adapter()


def configure_direct_openpi_policy(cfg):
    """Evaluate a Stage-1 OpenPI checkpoint directly, without an RLT actor."""

    source = OmegaConf.to_container(
        cfg.rollout.rlt_feature_model,
        resolve=True,
    )
    if source.get("model_type") != "openpi":
        raise ValueError("E1 checkpoint evaluation requires an OpenPI source model")
    if not source.get("model_path"):
        raise ValueError("E1 checkpoint evaluation requires an OpenPI checkpoint path")
    policy_setup = cfg.actor.model.get("policy_setup")
    if not policy_setup:
        raise ValueError("E1 checkpoint evaluation requires an action policy setup")
    source["policy_setup"] = policy_setup
    with open_dict(cfg.rollout):
        cfg.rollout.model = OmegaConf.create(source)
        cfg.rollout.rlt_feature_model = None
    return cfg


@hydra.main(version_base="1.1", config_path=None)
def main(cfg) -> None:
    cfg = configure_direct_openpi_policy(cfg)
    cfg = validate_cfg(cfg)
    if cfg.runner.get("task_type") != "embodied_eval":
        raise ValueError("E1 checkpoint evaluation requires task_type=embodied_eval")
    if cfg.runner.get("only_eval") is not True:
        raise ValueError("E1 checkpoint evaluation requires only_eval=true")
    if cfg.get("env", {}).get("train") is not None:
        raise ValueError("E1 checkpoint evaluation forbids a training environment")
    if cfg.rollout.model.model_type != "openpi":
        raise ValueError("E1 checkpoint evaluation must load the OpenPI checkpoint")
    if cfg.rollout.model.policy_setup != cfg.actor.model.policy_setup:
        raise ValueError("E1 checkpoint evaluation action policy setup mismatch")
    if cfg.rollout.get("rlt_feature_model") is not None:
        raise ValueError("E1 checkpoint evaluation forbids an RLT feature model")
    if cfg.rollout.get("expert_model") is not None:
        raise ValueError("E1 checkpoint evaluation forbids an expert model")
    if cfg.env.eval.use_fixed_reset_state_ids is not True:
        raise ValueError("E1 checkpoint evaluation requires frozen reset IDs")
    offset_value = os.environ.get("QUALIA_DEVELOPMENT_RESET_OFFSET")
    count_value = os.environ.get("QUALIA_DEVELOPMENT_RESET_COUNT")
    if (offset_value is None) != (count_value is None):
        raise ValueError("E1 shard offset and count must be provided together")
    shard = None
    expected_outcomes = 256
    if offset_value is not None and count_value is not None:
        try:
            offset = int(offset_value)
            count = int(count_value)
        except ValueError as error:
            raise ValueError("E1 shard offset and count must be integers") from error
        if count != SHARD_SIZE or offset % SHARD_SIZE:
            raise ValueError("E1 shard must be one frozen contiguous 64-reset slice")
        shard = shard_spec(offset // SHARD_SIZE)
        if shard.offset != offset:
            raise ValueError("E1 shard offset does not match its frozen index")
        expected_outcomes = shard.count
    if cfg.env.eval.total_num_envs * cfg.env.eval.rollout_epoch != expected_outcomes:
        raise ValueError(
            f"E1 checkpoint evaluation requires exactly {expected_outcomes} outcomes"
        )

    print(
        "QUALIA_E1_EVALUATION_CONTRACT="
        + json.dumps(
            {
                "development_only": True,
                "evaluation_outcomes": expected_outcomes,
                "expert_model_loaded": False,
                "direct_openpi_policy": True,
                "policy_training_enabled": False,
                "rlt_feature_model_loaded": False,
                "promotion_authorized": False,
                "task_type": "embodied_eval",
                "shard": None if shard is None else shard.to_dict(),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    print(json.dumps(OmegaConf.to_container(cfg, resolve=True), indent=2))

    cluster = Cluster(
        cluster_cfg=cfg.cluster,
        distributed_log_dir=cfg.runner.per_worker_log_path,
    )
    placement = HybridComponentPlacement(cfg, cluster)
    rollout = MultiStepRolloutWorker.create_group(cfg).launch(
        cluster,
        name=cfg.rollout.group_name,
        placement_strategy=placement.get_strategy("rollout"),
    )
    env = EnvWorker.create_group(cfg).launch(
        cluster,
        name=cfg.env.group_name,
        placement_strategy=placement.get_strategy("env"),
    )
    runner = EmbodiedEvalRunner(cfg=cfg, rollout=rollout, env=env)
    runner.init_workers()
    runner.run()


if __name__ == "__main__":
    main()
