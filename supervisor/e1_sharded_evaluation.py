"""Fail-closed helpers for the four-shard E1 development evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


SHARD_COUNT = 4
SHARD_SIZE = 64
PARALLEL_ENVIRONMENTS = 16
TOTAL_TRAJECTORIES = SHARD_COUNT * SHARD_SIZE
EVALUATOR_CONTRACT_PATHS = (
    "configs/d1/e1_checkpoint_evaluation_shard.yaml",
    "envs/e1_frozen_development_env.py",
    "envs/frozen_development_resets.py",
    "scripts/run_g0_e1_checkpoint_evaluation.py",
    "supervisor/e1_sharded_evaluation.py",
)

_ARRAY_METRIC = re.compile(
    r"'eval/(?P<key>reward|success_once|episode_len|return)': "
    r"array\((?P<value>[-+0-9.eE]+), dtype=float32\)"
)
_TRAJECTORIES = re.compile(r"'eval/num_trajectories': (?P<value>\d+)")


class E1ShardError(ValueError):
    """Raised when a shard contract, metric, or receipt is invalid."""


def evaluator_contract_sha256(root: Path) -> str:
    """Hash the exact evaluator contract files with path-bound canonical JSON."""

    values = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in EVALUATOR_CONTRACT_PATHS
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ShardSpec:
    index: int
    offset: int
    count: int = SHARD_SIZE
    total_trajectories: int = TOTAL_TRAJECTORIES

    def to_dict(self) -> dict[str, int]:
        return {
            "count": self.count,
            "index": self.index,
            "offset": self.offset,
            "total_trajectories": self.total_trajectories,
        }


def shard_spec(index: int) -> ShardSpec:
    if isinstance(index, bool) or not isinstance(index, int):
        raise E1ShardError("shard index must be an integer")
    if not 0 <= index < SHARD_COUNT:
        raise E1ShardError(f"shard index must be between 0 and {SHARD_COUNT - 1}")
    return ShardSpec(index=index, offset=index * SHARD_SIZE)


def parse_final_eval_metrics(
    log_text: str,
    *,
    expected_trajectories: int = SHARD_SIZE,
) -> dict[str, float | int | str]:
    """Parse the final RLinf evaluation dictionary and validate exact counts."""

    candidates: list[dict[str, float | int]] = []
    for line in log_text.splitlines():
        values = {
            match.group("key"): float(match.group("value"))
            for match in _ARRAY_METRIC.finditer(line)
        }
        count_match = _TRAJECTORIES.search(line)
        if count_match:
            values["num_trajectories"] = int(count_match.group("value"))
        if set(values) == {
            "reward",
            "success_once",
            "episode_len",
            "return",
            "num_trajectories",
        }:
            candidates.append(values)
    if len(candidates) != 1:
        raise E1ShardError("exactly one complete final evaluation metric is required")

    metric = candidates[0]
    count = int(metric["num_trajectories"])
    if count != expected_trajectories:
        raise E1ShardError(
            f"expected {expected_trajectories} trajectories, received {count}"
        )
    for key in ("reward", "success_once", "episode_len", "return"):
        if not math.isfinite(float(metric[key])):
            raise E1ShardError(f"eval/{key} must be finite")
    success = float(metric["success_once"])
    if not 0.0 <= success <= 1.0:
        raise E1ShardError("eval/success_once must be in [0, 1]")
    successes_float = success * count
    successes = round(successes_float)
    if not math.isclose(successes_float, successes, abs_tol=1e-6):
        raise E1ShardError("eval/success_once is not an exact trajectory fraction")

    return {
        "episode_len_mean": float(metric["episode_len"]),
        "num_successes": successes,
        "num_trajectories": count,
        "primary_metric": "eval/success_once",
        "return_mean": float(metric["return"]),
        "reward_mean": float(metric["reward"]),
        "success_once": success,
    }


def aggregate_shard_receipts(
    receipts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Combine exactly four disjoint complete shard receipts into one metric."""

    if len(receipts) != SHARD_COUNT:
        raise E1ShardError(f"exactly {SHARD_COUNT} shard receipts are required")
    by_index: dict[int, Mapping[str, object]] = {}
    identity: tuple[object, ...] | None = None
    for receipt in receipts:
        if receipt.get("status") != "complete_valid_development_shard":
            raise E1ShardError("every shard receipt must be complete and valid")
        authority = receipt.get("authority")
        if not isinstance(authority, Mapping) or not authority or any(authority.values()):
            raise E1ShardError("shard receipts must be explicitly non-authorizing")
        shard = receipt.get("shard")
        checkpoint = receipt.get("checkpoint")
        metric = receipt.get("metric")
        if not isinstance(shard, Mapping) or not isinstance(checkpoint, Mapping):
            raise E1ShardError("shard and checkpoint identities are required")
        if not isinstance(metric, Mapping):
            raise E1ShardError("shard metric is required")
        try:
            index = int(shard["index"])
        except (KeyError, TypeError, ValueError) as error:
            raise E1ShardError("invalid shard index") from error
        spec = shard_spec(index)
        if dict(shard) != spec.to_dict():
            raise E1ShardError("shard boundaries do not match the frozen partition")
        if index in by_index:
            raise E1ShardError("duplicate shard index")
        current_identity = (
            checkpoint.get("step"),
            checkpoint.get("sha256"),
            checkpoint.get("version_id"),
            receipt.get("reset_set_sha256"),
            receipt.get("evaluator_source_sha256"),
        )
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise E1ShardError("shard receipts disagree on frozen identities")
        if metric.get("num_trajectories") != SHARD_SIZE:
            raise E1ShardError("each shard must contain exactly 64 trajectories")
        by_index[index] = receipt
    if set(by_index) != set(range(SHARD_COUNT)):
        raise E1ShardError("shard coverage must be exactly indices 0 through 3")

    ordered_metrics = [by_index[index]["metric"] for index in range(SHARD_COUNT)]
    successes = sum(int(metric["num_successes"]) for metric in ordered_metrics)

    def weighted_mean(key: str) -> float:
        weighted_total = sum(
            float(metric[key]) * SHARD_SIZE for metric in ordered_metrics
        )
        return weighted_total / TOTAL_TRAJECTORIES

    return {
        "authority": {
            "additional_evaluation_authorized": False,
            "e2_authorized": False,
            "final_reset_access_authorized": False,
            "policy_promotion_authorized": False,
        },
        "checkpoint": {
            "sha256": identity[1],
            "step": identity[0],
            "version_id": identity[2],
        },
        "evaluator_source_sha256": identity[4],
        "metric": {
            "episode_len_mean": weighted_mean("episode_len_mean"),
            "num_successes": successes,
            "num_trajectories": TOTAL_TRAJECTORIES,
            "primary_metric": "eval/success_once",
            "return_mean": weighted_mean("return_mean"),
            "reward_mean": weighted_mean("reward_mean"),
            "success_once": successes / TOTAL_TRAJECTORIES,
        },
        "reset_set_sha256": identity[3],
        "shard_indices": list(range(SHARD_COUNT)),
        "status": "complete_valid_development_baseline",
    }
