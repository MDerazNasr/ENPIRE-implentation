#!/usr/bin/env python3
"""Evaluate one E1 checkpoint without constructing any training actor worker."""

from __future__ import annotations

import json

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
    if cfg.rollout.get("rlt_feature_model") is not None:
        raise ValueError("E1 checkpoint evaluation forbids an RLT feature model")
    if cfg.rollout.get("expert_model") is not None:
        raise ValueError("E1 checkpoint evaluation forbids an expert model")
    if cfg.env.eval.use_fixed_reset_state_ids is not True:
        raise ValueError("E1 checkpoint evaluation requires frozen reset IDs")
    if cfg.env.eval.total_num_envs * cfg.env.eval.rollout_epoch != 256:
        raise ValueError("E1 checkpoint evaluation requires exactly 256 outcomes")

    print(
        "QUALIA_E1_EVALUATION_CONTRACT="
        + json.dumps(
            {
                "development_only": True,
                "evaluation_outcomes": 256,
                "expert_model_loaded": False,
                "direct_openpi_policy": True,
                "policy_training_enabled": False,
                "rlt_feature_model_loaded": False,
                "promotion_authorized": False,
                "task_type": "embodied_eval",
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
