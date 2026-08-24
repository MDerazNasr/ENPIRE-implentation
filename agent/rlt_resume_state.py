"""Strict, opt-in persistence for RLinf RLT schedule counters.

Pinned RLinf persists model, optimizer, scheduler, RNG, target-model, and
replay-buffer state, but its RLT schedule bookkeeping is plain Python state.
This module patches only the synchronous RLT worker at runtime and writes a
small per-rank sidecar beside the native checkpoint.  RLinf source remains
unchanged.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
STATE_DIRECTORY = "sac_components/rlt_schedule_state"
COUNTER_FIELDS = (
    "update_step",
    "transitions_since_train",
    "episodes_since_train",
    "total_transitions_added",
    "total_episodes_added",
    "_warmup_ready_total_transitions",
    "_warmup_ready_total_episodes",
    "pending_update_budget",
)
NULLABLE_FIELDS = {
    "_warmup_ready_total_transitions",
    "_warmup_ready_total_episodes",
}


class RLTResumeStateError(RuntimeError):
    """Raised when an RLT schedule sidecar is absent or inconsistent."""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping) or hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def schedule_contract(cfg: Any) -> dict[str, Any]:
    """Return only the config fields that define RLT schedule semantics."""

    algorithm = cfg.algorithm
    return {
        "loss_type": str(algorithm.get("loss_type", "")),
        "update_epoch": int(algorithm.get("update_epoch", 1)),
        "critic_actor_ratio": int(algorithm.get("critic_actor_ratio", 1)),
        "rlt_schedule": _plain(algorithm.get("rlt_schedule", {}) or {}),
        "actor_weight_schedule": _plain(
            algorithm.get("actor_weight_schedule", {}) or {}
        ),
    }


def schedule_fingerprint(cfg: Any) -> str:
    encoded = json.dumps(
        schedule_contract(cfg), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_step(checkpoint_actor_path: str | Path) -> int:
    name = Path(checkpoint_actor_path).parent.name
    if not name.startswith("global_step_"):
        raise RLTResumeStateError(
            f"checkpoint actor path must be under global_step_<n>: {checkpoint_actor_path}"
        )
    try:
        return int(name.removeprefix("global_step_"))
    except ValueError as error:
        raise RLTResumeStateError(f"invalid checkpoint step directory: {name}") from error


def sidecar_path(checkpoint_actor_path: str | Path, rank: int) -> Path:
    return Path(checkpoint_actor_path) / STATE_DIRECTORY / f"rank_{rank}.json"


def _validated_counter(name: str, value: Any) -> int | None:
    if value is None and name in NULLABLE_FIELDS:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RLTResumeStateError(f"{name} must be a non-negative integer")
    return value


def _capture_replay_rng(worker: Any) -> str | None:
    generator = getattr(getattr(worker, "replay_buffer", None), "random_generator", None)
    if generator is None:
        return None
    state = generator.get_state().cpu().numpy().tobytes()
    return base64.b64encode(state).decode("ascii")


def capture_state(worker: Any, step: int) -> dict[str, Any]:
    counters = {
        name: _validated_counter(name, getattr(worker, name))
        for name in COUNTER_FIELDS
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "rlinf_commit": RLINF_COMMIT,
        "checkpoint_step": int(step),
        "rank": int(worker._rank),
        "world_size": int(worker._world_size),
        "schedule_contract": schedule_contract(worker.cfg),
        "schedule_fingerprint": schedule_fingerprint(worker.cfg),
        "counters": counters,
        "replay_generator_state_b64": _capture_replay_rng(worker),
    }


def atomic_write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def save_worker_state(worker: Any, checkpoint_actor_path: str | Path, step: int) -> Path:
    if checkpoint_step(checkpoint_actor_path) != int(step):
        raise RLTResumeStateError("checkpoint path and save step disagree")
    path = sidecar_path(checkpoint_actor_path, int(worker._rank))
    atomic_write_state(path, capture_state(worker, step))
    return path


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RLTResumeStateError(f"RLT schedule sidecar missing: {path}")
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RLTResumeStateError(f"invalid RLT schedule sidecar: {path}") from error
    if not isinstance(state, dict):
        raise RLTResumeStateError("RLT schedule sidecar must contain an object")
    return state


def audit_state_file(
    path: Path,
    *,
    expected_step: int,
    expected_rank: int = 0,
    expected_world_size: int = 1,
    require_replay_rng: bool = True,
) -> dict[str, Any]:
    """Deep-validate a saved sidecar without constructing an RLinf worker."""

    state = load_state(path)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "rlinf_commit": RLINF_COMMIT,
        "checkpoint_step": expected_step,
        "rank": expected_rank,
        "world_size": expected_world_size,
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise RLTResumeStateError(
                f"RLT schedule sidecar {key} mismatch: {state.get(key)!r} != {value!r}"
            )
    contract = state.get("schedule_contract")
    if not isinstance(contract, dict):
        raise RLTResumeStateError("RLT schedule sidecar schedule contract missing")
    encoded_contract = json.dumps(
        contract, sort_keys=True, separators=(",", ":")
    ).encode()
    fingerprint = hashlib.sha256(encoded_contract).hexdigest()
    if state.get("schedule_fingerprint") != fingerprint:
        raise RLTResumeStateError("RLT schedule sidecar fingerprint is not self-consistent")
    counters = state.get("counters")
    if not isinstance(counters, dict) or set(counters) != set(COUNTER_FIELDS):
        raise RLTResumeStateError("RLT schedule sidecar counter schema mismatch")
    validated = {
        name: _validated_counter(name, counters[name]) for name in COUNTER_FIELDS
    }
    replay_rng = state.get("replay_generator_state_b64")
    if require_replay_rng and not replay_rng:
        raise RLTResumeStateError("RLT schedule sidecar replay generator state missing")
    if replay_rng is not None:
        if not isinstance(replay_rng, str):
            raise RLTResumeStateError("replay generator state must be base64 text")
        try:
            base64.b64decode(replay_rng, validate=True)
        except (ValueError, binascii.Error) as error:
            raise RLTResumeStateError("invalid replay generator base64 state") from error
    return {
        "schema_version": state["schema_version"],
        "rlinf_commit": state["rlinf_commit"],
        "checkpoint_step": state["checkpoint_step"],
        "rank": state["rank"],
        "world_size": state["world_size"],
        "schedule_fingerprint": fingerprint,
        "counters": validated,
        "replay_generator_state_present": replay_rng is not None,
    }


def _restore_replay_rng(worker: Any, encoded: Any) -> None:
    if encoded is None:
        return
    if not isinstance(encoded, str):
        raise RLTResumeStateError("replay generator state must be base64 text")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise RLTResumeStateError("invalid replay generator base64 state") from error
    try:
        import torch

        tensor = torch.frombuffer(bytearray(raw), dtype=torch.uint8).clone()
        worker.replay_buffer.random_generator.set_state(tensor)
    except Exception as error:
        raise RLTResumeStateError("could not restore replay generator state") from error


def validate_state(
    state: dict[str, Any],
    *,
    worker: Any,
    expected_step: int,
) -> dict[str, int | None]:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "rlinf_commit": RLINF_COMMIT,
        "checkpoint_step": expected_step,
        "rank": int(worker._rank),
        "world_size": int(worker._world_size),
        "schedule_fingerprint": schedule_fingerprint(worker.cfg),
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise RLTResumeStateError(
                f"RLT schedule sidecar {key} mismatch: {state.get(key)!r} != {value!r}"
            )
    counters = state.get("counters")
    if not isinstance(counters, dict) or set(counters) != set(COUNTER_FIELDS):
        raise RLTResumeStateError("RLT schedule sidecar counter schema mismatch")
    return {
        name: _validated_counter(name, counters[name]) for name in COUNTER_FIELDS
    }


def restore_worker_state(worker: Any, checkpoint_actor_path: str | Path) -> dict[str, Any]:
    step = checkpoint_step(checkpoint_actor_path)
    path = sidecar_path(checkpoint_actor_path, int(worker._rank))
    state = load_state(path)
    counters = validate_state(state, worker=worker, expected_step=step)
    previous = int(worker.update_step)
    for name, value in counters.items():
        setattr(worker, name, value)
    _restore_replay_rng(worker, state.get("replay_generator_state_b64"))
    marker = {
        "checkpoint_step": step,
        "rank": int(worker._rank),
        "previous_update_step": previous,
        "restored_update_step": int(worker.update_step),
        "schedule_fingerprint": state["schedule_fingerprint"],
        "sidecar": str(path),
    }
    print(f"QUALIA_RLT_RESUME_STATE={json.dumps(marker, sort_keys=True)}", flush=True)
    return marker


def install_patch() -> bool:
    """Patch the pinned synchronous RLT worker once in the current process."""

    from rlinf.workers.actor.fsdp_rlt_ac_policy_worker import RLTACFSDPPolicy

    if getattr(RLTACFSDPPolicy, "_qualia_resume_state_patch", False):
        return False
    original_save = RLTACFSDPPolicy.save_checkpoint
    original_load = RLTACFSDPPolicy.load_checkpoint

    def save_checkpoint(self, save_base_path, step):
        result = original_save(self, save_base_path, step)
        save_worker_state(self, save_base_path, step)
        return result

    def load_checkpoint(self, load_base_path):
        result = original_load(self, load_base_path)
        restore_worker_state(self, load_base_path)
        return result

    RLTACFSDPPolicy.save_checkpoint = save_checkpoint
    RLTACFSDPPolicy.load_checkpoint = load_checkpoint
    RLTACFSDPPolicy._qualia_resume_state_patch = True
    return True
