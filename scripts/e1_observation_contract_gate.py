#!/usr/bin/env python3
"""Validate the frozen E1 observation contract without loading a policy."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


RLINF_HOME = Path(os.environ.get("RLINF_HOME", "/opt/RLinf"))
EXPECTED_KEYS = {
    "extra_view_images",
    "main_images",
    "states",
    "task_descriptions",
    "wrist_images",
}


def main() -> None:
    from hydra import compose, initialize_config_dir

    from envs.e1_frozen_development_env import (
        E1FrozenDevelopmentManiskillRLTEnv,
    )

    reset_path = Path(os.environ["QUALIA_DEVELOPMENT_RESET_PATH"])
    if not reset_path.is_file():
        raise FileNotFoundError(f"development reset file missing: {reset_path}")

    config_dir = RLINF_HOME / "examples/embodiment/config"
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(
            config_name="maniskill_rlt_stage2_ac_mlp",
            overrides=[
                "env.eval.total_num_envs=16",
                "env.eval.auto_reset=false",
                "env.eval.use_fixed_reset_state_ids=true",
                "env.eval.init_params.sim_backend=cpu",
                "+env.eval.init_params.render_backend=pci:0000:00:00.0",
                "env.eval.rlt_policy_switch.enable=false",
                "env.eval.rlt_policy_switch.expert_takeover.enable=false",
            ],
        )

    from rlinf.envs import get_env_cls

    resolved_env_class = get_env_cls("maniskill_rlt", cfg.env.eval)
    if resolved_env_class is not E1FrozenDevelopmentManiskillRLTEnv:
        raise RuntimeError(
            "runtime environment lookup did not select the frozen E1 adapter"
        )

    from scripts.run_g0_e1_checkpoint_evaluation import (
        configure_direct_openpi_policy,
    )

    cfg.rollout.rlt_feature_model.model_path = "/no-checkpoint-access/e1-stage1-actor"
    direct_cfg = configure_direct_openpi_policy(cfg)
    if direct_cfg.rollout.model.model_type != "openpi":
        raise RuntimeError("direct evaluation model is not OpenPI")
    if direct_cfg.rollout.rlt_feature_model is not None:
        raise RuntimeError("direct evaluation unexpectedly retained an RLT feature model")

    started = time.perf_counter()
    env = E1FrozenDevelopmentManiskillRLTEnv(
        cfg=cfg.env.eval,
        num_envs=16,
        seed_offset=0,
        total_num_processes=1,
        worker_info={"gate": "e1-observation-contract-v1"},
    )
    initialization_seconds = time.perf_counter() - started
    try:
        started = time.perf_counter()
        observation, info = env.reset()
        reset_seconds = time.perf_counter() - started

        observed_keys = set(observation)
        if observed_keys != EXPECTED_KEYS:
            raise RuntimeError(
                f"observation keys mismatch: {sorted(observed_keys)} != "
                f"{sorted(EXPECTED_KEYS)}"
            )
        expected_shapes = {
            "main_images": (16, 384, 384, 3),
            "states": (16, 9),
            "wrist_images": (16, 384, 384, 3),
        }
        observed_shapes = {
            key: tuple(observation[key].shape) for key in expected_shapes
        }
        if observed_shapes != expected_shapes:
            raise RuntimeError(
                f"observation shapes mismatch: {observed_shapes} != {expected_shapes}"
            )
        if len(observation["task_descriptions"]) != 16:
            raise RuntimeError("expected one task description per environment")

        result = {
            "status": "passed",
            "gate": "e1-observation-contract-v1",
            "environment_class": type(env).__name__,
            "runtime_lookup_class": resolved_env_class.__name__,
            "workers": 16,
            "simulator_steps": 0,
            "policy_loaded": False,
            "checkpoint_accessed": False,
            "metric_produced": False,
            "direct_openpi_policy": True,
            "rlt_feature_model_loaded": False,
            "initialization_seconds": initialization_seconds,
            "reset_seconds": reset_seconds,
            "observation_keys": sorted(observed_keys),
            "observation_shapes": {
                key: list(shape) for key, shape in observed_shapes.items()
            },
            "reset_info_keys": sorted(info),
        }
        print("QUALIA_E1_OBSERVATION_GATE=" + json.dumps(result, sort_keys=True))
    finally:
        env.close()


if __name__ == "__main__":
    main()
