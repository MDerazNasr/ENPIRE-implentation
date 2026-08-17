"""Validate the exact 16-worker Modal adapter against RLinf's RLT task."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


RLINF_HOME = Path(os.environ.get("RLINF_HOME", "/opt/RLinf"))


def main() -> None:
    import torch
    from hydra import compose, initialize_config_dir

    from envs.modal_multiprocess_rlt_env import (
        ModalMultiprocessManiskillRLTEnv,
    )

    config_dir = RLINF_HOME / "examples/embodiment/config"
    with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
        cfg = compose(
            config_name="maniskill_rlt_stage2_ac_mlp",
            overrides=[
                "env.train.total_num_envs=16",
                "env.train.rollout_epoch=4",
                "env.train.auto_reset=false",
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
        worker_info={"gate": True},
    )
    init_seconds = time.perf_counter() - started
    try:
        started = time.perf_counter()
        observation, info = env.reset()
        reset_seconds = time.perf_counter() - started
        actions = torch.zeros((16, 10, 8), dtype=torch.float32)
        started = time.perf_counter()
        obs_list, rewards, terminations, truncations, infos_list = env.chunk_step(
            actions
        )
        chunk_seconds = time.perf_counter() - started

        expected = {
            "main_images": (16, 384, 384, 3),
            "wrist_images": (16, 384, 384, 3),
            "states": (16, 9),
        }
        observed = {
            key: tuple(observation[key].shape) for key in expected
        }
        if observed != expected:
            raise RuntimeError(f"observation shape mismatch: {observed} != {expected}")
        if len(observation["task_descriptions"]) != 16:
            raise RuntimeError("expected one task description per environment")
        if len(obs_list) != 10 or len(infos_list) != 10:
            raise RuntimeError("expected ten upstream action-chunk results")
        for label, value in (
            ("rewards", rewards),
            ("terminations", terminations),
            ("truncations", truncations),
        ):
            if tuple(value.shape) != (16, 10):
                raise RuntimeError(f"{label} shape mismatch: {tuple(value.shape)}")
        if tuple(obs_list[-1]["main_images"].shape) != (16, 384, 384, 3):
            raise RuntimeError("post-step image batch mismatch")
        if "episode" not in infos_list[-1]:
            raise RuntimeError("upstream episode metrics are missing")

        result = {
            "status": "passed",
            "workers": 16,
            "upstream_env_class_per_worker": "ManiskillRLTEnv",
            "sim_backend": "cpu",
            "render_backend": "pci:0000:00:00.0 (llvmpipe)",
            "initialization_seconds": init_seconds,
            "reset_seconds": reset_seconds,
            "ten_step_chunk_seconds": chunk_seconds,
            "observation_shapes": {
                key: list(value) for key, value in observed.items()
            },
            "reward_shape": list(rewards.shape),
            "rlt_switch_flags_present": "rlt_switch_flags" in infos_list[-1],
            "episode_metrics_present": True,
            "reset_info_keys": sorted(info.keys()),
        }
        print("QUALIA_MODAL_ADAPTER_GATE=" + json.dumps(result, sort_keys=True))
    finally:
        env.close()


if __name__ == "__main__":
    main()
