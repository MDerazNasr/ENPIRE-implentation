from __future__ import annotations

import json
import time
from pathlib import Path


RLINF_HOME = Path("/opt/RLinf")


def shape(value):
    if value is None:
        return "NoneType"
    if isinstance(value, list):
        return [type(item).__name__ for item in value]
    return list(value.shape)


def main() -> None:
    from hydra import compose, initialize_config_dir
    from envs.modal_multiprocess_rlt_env import ModalMultiprocessManiskillRLTEnv

    config_dir = RLINF_HOME / "examples/embodiment/config"
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(
            config_name="maniskill_rlt_stage2_ac_mlp",
            overrides=[
                "env.train.total_num_envs=16",
                "env.train.rollout_epoch=4",
                "env.train.auto_reset=false",
                "env.train.seed=2026",
                "env.train.init_params.sim_backend=cpu",
                "+env.train.init_params.render_backend=pci:0000:00:00.0",
                "env.train.rlt_policy_switch.expert_takeover.enable=false",
            ],
        )

    started = time.perf_counter()
    env = ModalMultiprocessManiskillRLTEnv(
        cfg=cfg.env.train,
        num_envs=16,
        seed_offset=0,
        total_num_processes=1,
        worker_info={"no_outcome_probe": True},
    )
    try:
        observation, info = env.reset()
        result = {
            "action_step_executed": False,
            "elapsed_seconds": time.perf_counter() - started,
            "info_shapes": {key: shape(value) for key, value in info.items()},
            "num_envs": env.num_envs,
            "observation_shapes": {
                key: shape(value) for key, value in observation.items()
            },
            "policy_loaded": False,
            "promotion_executed": False,
            "scientific_evaluation_executed": False,
            "seed": env.seed,
            "status": "pass",
            "task": cfg.env.train.init_params.id,
        }
        assert result["seed"] == 2026
        assert result["observation_shapes"]["main_images"] == [16, 384, 384, 3]
        assert result["observation_shapes"]["wrist_images"] == [16, 384, 384, 3]
        assert result["observation_shapes"]["states"] == [16, 9]
        assert result["info_shapes"]["success"] == [16]
        print(json.dumps(result, sort_keys=True))
    finally:
        env.close()


if __name__ == "__main__":
    main()
