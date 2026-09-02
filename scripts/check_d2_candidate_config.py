#!/usr/bin/env python3
"""Harness-owned validation for the bounded D2 paid-acceptance config."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import build_d1_command, load_d1_config, resolve_d1_config  # noqa: E402
from supervisor.canonical import fingerprint  # noqa: E402
from supervisor.d1_backend import synchronize_d1_config  # noqa: E402


ENVIRONMENT = {
    "RLINF_HOME": "/opt/RLinf",
    "MODAL_ADAPTER_ROOT": "/opt/qualia",
    "STAGE1_CHECKPOINT": (
        "/private/tmp/enpire-d2-paid-acceptance/"
        "checkpoints/stage1-step-500-actor"
    ),
    "NORM_STATS_PATH": "/opt/qualia/norm_stats.json",
    "WANDB_PROJECT": "qualia-rlt-d2-acceptance",
    "D2_WANDB_DIR": (
        "/private/tmp/enpire-d2-paid-acceptance/"
        "wandb/d2-paid-config-attachment-v1"
    ),
    "D1_SEED": "2026",
}


def inspect(path: Path) -> dict:
    source = load_d1_config(path)
    scientific = source["scientific_values"]
    required = {
        "online_bc_weight": 2.25,
        "runner_steps": 1,
        "fixed_eval_trajectories": 1,
        "train_parallel_environments": 1,
        "eval_parallel_environments": 1,
        "episode_horizon": 20,
    }
    for field, expected in required.items():
        if scientific.get(field) != expected:
            raise ValueError(f"D2 acceptance {field} must equal {expected!r}")
    if source["budget"]["max_cost_usd"] != 1.5156:
        raise ValueError("D2 acceptance GPU cost cap must equal 1.5156")
    resolved = resolve_d1_config(
        synchronize_d1_config(source, seed=2026), ENVIRONMENT
    )
    command, cwd = build_d1_command(
        resolved, Path("/private/tmp/enpire-d2-paid-acceptance/results/check")
    )
    overrides = {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in resolved["hydra_overrides"]
    }
    if overrides["algorithm.actor_weight_schedule.online_bc_weight"] != "2.25":
        raise ValueError("D2 acceptance delta did not reach the RLinf command")
    if "runner.max_steps=1" not in command or "runner.val_check_interval=1" not in command:
        raise ValueError("D2 acceptance command is not bounded to one evaluated step")
    return {
        "schema_version": 1,
        "status": "passed",
        "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "resolved_config_hash": fingerprint(resolved),
        "logical_command_hash": fingerprint(command),
        "logical_cwd": str(cwd),
        "process_launched": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(inspect(arguments.config), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
