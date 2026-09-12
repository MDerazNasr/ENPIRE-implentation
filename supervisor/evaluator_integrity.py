"""GPU-free integrity boundary for frozen evaluator inputs and replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    fingerprint,
    require_git_commit,
    require_identifier,
    require_sha256,
)
from supervisor.g0_decision import decide_g0_candidate


class EvaluatorIntegrityError(ContractError):
    """Raised when evaluator inputs or isolation boundaries are invalid."""


def _exact_mapping(value: Any, field: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise EvaluatorIntegrityError(f"{field} fields are invalid")
    return value


@dataclass(frozen=True)
class ResetSetArtifact:
    set_id: str
    role: str
    task_id: str
    simulator_hash: str
    generator_hash: str
    generator_seed: int
    reset_ids: tuple[int, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "ResetSetArtifact":
        data = _exact_mapping(
            value,
            "reset set",
            {
                "schema_version",
                "set_id",
                "role",
                "task_id",
                "simulator_hash",
                "generator_hash",
                "generator_seed",
                "reset_ids",
            },
        )
        if data["schema_version"] != 1:
            raise EvaluatorIntegrityError("reset-set schema version is unsupported")
        if data["role"] not in {"development", "final"}:
            raise EvaluatorIntegrityError("reset-set role must be development or final")
        seed = data["generator_seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise EvaluatorIntegrityError("reset-set generator seed is invalid")
        raw_ids = data["reset_ids"]
        if not isinstance(raw_ids, list) or len(raw_ids) != 256:
            raise EvaluatorIntegrityError("reset set must contain exactly 256 IDs")
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in raw_ids):
            raise EvaluatorIntegrityError("reset IDs must be non-negative integers")
        if len(set(raw_ids)) != len(raw_ids):
            raise EvaluatorIntegrityError("reset IDs must be unique")
        return cls(
            set_id=require_identifier(data["set_id"], "reset_set.set_id"),
            role=data["role"],
            task_id=require_identifier(data["task_id"], "reset_set.task_id"),
            simulator_hash=require_sha256(data["simulator_hash"], "reset_set.simulator_hash"),
            generator_hash=require_sha256(data["generator_hash"], "reset_set.generator_hash"),
            generator_seed=seed,
            reset_ids=tuple(raw_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "set_id": self.set_id,
            "role": self.role,
            "task_id": self.task_id,
            "simulator_hash": self.simulator_hash,
            "generator_hash": self.generator_hash,
            "generator_seed": self.generator_seed,
            "reset_ids": list(self.reset_ids),
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


def validate_reset_pair(
    development: ResetSetArtifact, final: ResetSetArtifact
) -> dict[str, Any]:
    if development.role != "development" or final.role != "final":
        raise EvaluatorIntegrityError("reset sets have incorrect roles")
    if development.set_id == final.set_id:
        raise EvaluatorIntegrityError("reset-set IDs must differ")
    if development.task_id != final.task_id:
        raise EvaluatorIntegrityError("reset sets use different tasks")
    if development.simulator_hash != final.simulator_hash:
        raise EvaluatorIntegrityError("reset sets use different simulators")
    if development.generator_hash != final.generator_hash:
        raise EvaluatorIntegrityError("reset sets use different generators")
    if development.generator_seed == final.generator_seed:
        raise EvaluatorIntegrityError("reset sets require independent generator seeds")
    overlap = set(development.reset_ids).intersection(final.reset_ids)
    if overlap:
        raise EvaluatorIntegrityError("development and final reset sets overlap")
    return {
        "development_count": 256,
        "final_count": 256,
        "overlap_count": 0,
        "development_sha256": development.fingerprint(),
        "final_sha256": final.fingerprint(),
    }


@dataclass(frozen=True)
class EpisodeBatch:
    trial_id: str
    condition: str
    seed: int
    candidate_commit: str
    reset_set_hash: str
    reset_ids: tuple[int, ...]
    success_once: tuple[bool, ...]

    @classmethod
    def create(
        cls,
        *,
        trial_id: str,
        condition: str,
        seed: int,
        candidate_commit: str,
        reset_set_hash: str,
        reset_ids: Sequence[int],
        success_once: Sequence[bool],
    ) -> "EpisodeBatch":
        if condition not in {"control", "candidate"}:
            raise EvaluatorIntegrityError("condition must be control or candidate")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise EvaluatorIntegrityError("episode batch seed is invalid")
        ids = tuple(reset_ids)
        outcomes = tuple(success_once)
        if len(ids) != len(outcomes):
            raise EvaluatorIntegrityError("reset IDs and outcomes differ in length")
        if any(not isinstance(value, bool) for value in outcomes):
            raise EvaluatorIntegrityError("success outcomes must be booleans")
        return cls(
            trial_id=require_identifier(trial_id, "episode_batch.trial_id"),
            condition=condition,
            seed=seed,
            candidate_commit=require_git_commit(candidate_commit, "episode_batch.candidate_commit"),
            reset_set_hash=require_sha256(reset_set_hash, "episode_batch.reset_set_hash"),
            reset_ids=ids,
            success_once=outcomes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "condition": self.condition,
            "seed": self.seed,
            "candidate_commit": self.candidate_commit,
            "reset_set_hash": self.reset_set_hash,
            "reset_ids": list(self.reset_ids),
            "success_once": list(self.success_once),
        }


def evaluate_episode_batches(
    *,
    reset_set: ResetSetArtifact,
    expected_seeds: Sequence[int],
    incumbent_commit: str,
    candidate_commit: str,
    batches: Sequence[EpisodeBatch],
    evaluator_version: str,
    evaluator_source_hash: str,
    evaluator_environment_hash: str,
) -> dict[str, Any]:
    seeds = tuple(expected_seeds)
    if len(seeds) != 3 or len(set(seeds)) != 3:
        raise EvaluatorIntegrityError("evaluator requires exactly three unique seeds")
    incumbent = require_git_commit(incumbent_commit, "evaluator incumbent")
    candidate = require_git_commit(candidate_commit, "evaluator candidate")
    version = require_identifier(evaluator_version, "evaluator version")
    source_hash = require_sha256(evaluator_source_hash, "evaluator source hash")
    environment_hash = require_sha256(evaluator_environment_hash, "evaluator environment hash")
    expected_hash = reset_set.fingerprint()
    by_key: dict[tuple[str, int], EpisodeBatch] = {}
    for batch in batches:
        key = (batch.condition, batch.seed)
        if key in by_key:
            raise EvaluatorIntegrityError("duplicate condition/seed batch")
        if batch.seed not in seeds:
            raise EvaluatorIntegrityError("unexpected training seed")
        if batch.reset_set_hash != expected_hash or batch.reset_ids != reset_set.reset_ids:
            raise EvaluatorIntegrityError("reset-set substitution, omission, or reordering")
        expected_commit = incumbent if batch.condition == "control" else candidate
        if batch.candidate_commit != expected_commit:
            raise EvaluatorIntegrityError("condition commit identity mismatch")
        by_key[key] = batch
    required = {(condition, seed) for condition in ("control", "candidate") for seed in seeds}
    if set(by_key) != required:
        raise EvaluatorIntegrityError("missing paired condition/seed batch")
    control = [sum(by_key[("control", seed)].success_once) / 256 for seed in seeds]
    candidate_values = [sum(by_key[("candidate", seed)].success_once) / 256 for seed in seeds]
    result = decide_g0_candidate(control, candidate_values)
    payload = {
        "schema_version": 1,
        "evaluator_version": version,
        "evaluator_source_sha256": source_hash,
        "evaluator_environment_sha256": environment_hash,
        "reset_set_sha256": expected_hash,
        "seeds": list(seeds),
        "control_success": control,
        "candidate_success": candidate_values,
        "decision": result.decision,
        "reason": result.reason,
        "control_mean_success": result.control_mean_success,
        "candidate_mean_success": result.candidate_mean_success,
        "mean_success_delta": result.mean_success_delta,
        "success_delta_ci95": list(result.success_delta_ci95) if result.success_delta_ci95 else None,
        "batch_hashes": [fingerprint(by_key[key].to_dict()) for key in sorted(by_key)],
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


FORBIDDEN_CONTEXT_KEYS = {
    "final_reset_ids",
    "final_trajectories",
    "evaluator_source",
    "evaluator_implementation",
}


def assert_final_inputs_excluded(value: Any) -> None:
    """Reject final evaluator material from any nested agent-context payload."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_CONTEXT_KEYS:
                raise EvaluatorIntegrityError("agent context contains final evaluator inputs")
            assert_final_inputs_excluded(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            assert_final_inputs_excluded(nested)
