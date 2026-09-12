#!/usr/bin/env python3
"""Run CPU-only pinned task resets and emit a no-policy hash receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _list_hash(values: list[int]) -> str:
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rlinf-root", type=Path, required=True)
    parser.add_argument("--maniskill-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    sys.path[:0] = [str(args.project_root), str(args.rlinf_root), str(args.maniskill_root)]
    from envs.modal_multiprocess_rlt_env import expand_maniskill_seed
    from rlinf.envs.maniskill.peg_insertion_side_variants import (
        register_rlinf_peg_insertion_side_variants,
    )

    versions = {
        "numpy": np.__version__,
        "torch": torch.__version__,
        "sapien": importlib.metadata.version("sapien"),
        "gymnasium": importlib.metadata.version("gymnasium"),
        "maniskill": "3.0.0b22",
    }
    if versions != {
        "numpy": "1.26.4", "torch": "2.8.0+cpu", "sapien": "3.0.1",
        "gymnasium": "0.29.1", "maniskill": "3.0.0b22",
    }:
        raise ValueError("runtime versions do not match the confirmation contract")
    register_rlinf_peg_insertion_side_variants()
    env = gym.make(
        "PegInsertionSideWideClearance-v1", num_envs=1,
        reconfiguration_freq=0, obs_mode="state",
        control_mode="pd_joint_delta_pos", reward_mode="sparse",
        render_mode=None, render_backend="none", sim_backend="cpu",
    )
    reports = {}
    observed_sets = {}
    try:
        for seed, role in ((2026, "development"), (2027, "final")):
            expected = expand_maniskill_seed(seed, 256)
            observed = []
            for episode_seed in expected:
                env.reset(seed=int(episode_seed))
                observed.append(int(env.unwrapped._episode_seed[0]))
            observed_sets[role] = observed
            reports[role] = {
                "count": len(observed),
                "unique_count": len(set(observed)),
                "matches_source_derived": observed == expected,
                "ordered_ids_sha256": _list_hash(observed),
            }
    finally:
        env.close()
    payload = {
        "schema_version": 1,
        "status": "pass",
        "method": "sequential-single-worker-equivalence-for-multiprocess-cpu-adapter",
        "task_id": "PegInsertionSideWideClearance-v1",
        "versions": versions,
        "results": reports,
        "overlap_count": len(set(observed_sets["development"]) & set(observed_sets["final"])),
        "policy_loaded": False,
        "policy_evaluation_executed": False,
        "gpu_used": False,
        "promotion_executed": False,
        "ordered_final_ids_emitted": False,
    }
    if any(not report["matches_source_derived"] or report["count"] != 256 or report["unique_count"] != 256 for report in reports.values()) or payload["overlap_count"]:
        raise ValueError("live reset confirmation failed")
    receipt = {"payload": payload, "sha256": _fingerprint(payload)}
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
