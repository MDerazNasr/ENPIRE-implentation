#!/usr/bin/env python3
"""Capture the pinned ManiSkill episode-seed expansion without running a policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_g0_reset_sets import EXTRACTOR_ID
from supervisor.canonical import canonical_json, fingerprint

RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
MANISKILL_COMMIT = "33967b9e3ead1f841eec57cc9f31d0d8b8cf0907"
TASK_ID = "peg-insertion-side-wide-clearance-v1"
SOURCE_PATHS = {
    "rlinf_environment": "rlinf/envs/maniskill/maniskill_env.py",
    "rlinf_config": "examples/embodiment/config/maniskill_rlt_stage2_ac_mlp.yaml",
    "rlinf_task_variant": "rlinf/envs/maniskill/peg_insertion_side_variants.py",
}
MANISKILL_SOURCE_PATHS = {
    "maniskill_base_env": "mani_skill/envs/sapien_env.py",
    "maniskill_task": "mani_skill/envs/tasks/tabletop/peg_insertion_side.py",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def episode_seeds(seed: int) -> list[int]:
    # Exact BaseEnv._set_main_rng/_set_episode_rng scalar expansion at v3.0.0b22.
    return [seed, *np.random.RandomState(seed).randint(2**31, size=255).tolist()]


def build_capture(rlinf_root: Path, maniskill_root: Path) -> dict:
    if np.__version__ != "1.26.4":
        raise ValueError("capture requires NumPy 1.26.4")
    if _git(rlinf_root, "rev-parse", "HEAD") != RLINF_COMMIT or _git(rlinf_root, "status", "--short"):
        raise ValueError("RLinf source is not the exact clean pinned commit")
    if _git(maniskill_root, "rev-parse", "HEAD") != MANISKILL_COMMIT or _git(maniskill_root, "status", "--short"):
        raise ValueError("ManiSkill source is not the exact clean pinned commit")
    hashes = {"project_multiprocess_adapter": _hash(ROOT / "envs/modal_multiprocess_rlt_env.py")}
    hashes.update({name: _hash(rlinf_root / relative) for name, relative in SOURCE_PATHS.items()})
    hashes.update({name: _hash(maniskill_root / relative) for name, relative in MANISKILL_SOURCE_PATHS.items()})
    generator_hash = fingerprint({
        "algorithm": "maniskill-baseenv-scalar-seed-expansion-v3.0.0b22",
        "numpy_version": np.__version__,
        "source_hashes": hashes,
    })
    simulator_hash = fingerprint({
        "maniskill_commit": MANISKILL_COMMIT,
        "task_source_sha256": hashes["maniskill_task"],
        "rlinf_variant_sha256": hashes["rlinf_task_variant"],
    })
    def artifact(role: str, seed: int) -> dict:
        return {
            "schema_version": 1,
            "set_id": f"g0-{role}-v1",
            "role": role,
            "task_id": TASK_ID,
            "simulator_hash": simulator_hash,
            "generator_hash": generator_hash,
            "generator_seed": seed,
            "reset_ids": episode_seeds(seed),
        }
    return {
        "schema_version": 1,
        "extractor_id": EXTRACTOR_ID,
        "rlinf_commit": RLINF_COMMIT,
        "maniskill_commit": MANISKILL_COMMIT,
        "numpy_version": np.__version__,
        "source_hashes": hashes,
        "development": artifact("development", 2026),
        "final": artifact("final", 2027),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rlinf-root", type=Path, required=True)
    parser.add_argument("--maniskill-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    capture = build_capture(args.rlinf_root.resolve(), args.maniskill_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(capture) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": fingerprint(capture)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
