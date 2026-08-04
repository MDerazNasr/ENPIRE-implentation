"""Deterministic CPU-only residual-policy task for the public supervisor demo."""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Any, Sequence

from supervisor.canonical import ContractError, fingerprint


TOY_POLICY_VERSION = "toy-residual-reacher-v1"
BASE_GAIN = 0.42
PLANT_DRIFT = (0.035, -0.025)
MAX_ACTION = 0.65
HORIZON = 3
SUCCESS_RADIUS = 0.075


class ToyPolicyError(ContractError):
    """Raised when the toy-policy demo receives an invalid contract."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToyPolicyError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ToyPolicyError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class TrainingConfig:
    exploration_std: float
    generations: int = 8
    population: int = 40
    elite_count: int = 8
    training_episodes: int = 64

    @classmethod
    def from_dict(cls, value: Any) -> "TrainingConfig":
        if not isinstance(value, dict) or set(value) != {
            "exploration_std",
            "generations",
            "population",
            "elite_count",
            "training_episodes",
        }:
            raise ToyPolicyError("training config has missing or unknown fields")
        exploration = _finite(value["exploration_std"], "exploration_std")
        if not 0.001 <= exploration <= 0.8:
            raise ToyPolicyError("exploration_std must be between 0.001 and 0.8")
        integers: dict[str, int] = {}
        for name in ("generations", "population", "elite_count", "training_episodes"):
            raw = value[name]
            if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
                raise ToyPolicyError(f"{name} must be a positive integer")
            integers[name] = raw
        if integers["elite_count"] >= integers["population"]:
            raise ToyPolicyError("elite_count must be smaller than population")
        return cls(exploration_std=exploration, **integers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exploration_std": self.exploration_std,
            "generations": self.generations,
            "population": self.population,
            "elite_count": self.elite_count,
            "training_episodes": self.training_episodes,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class ResidualPolicy:
    gain: float
    bias_x: float
    bias_y: float

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "ResidualPolicy":
        if len(values) != 3:
            raise ToyPolicyError("residual policy requires three parameters")
        return cls(*(_finite(value, "policy parameter") for value in values))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": TOY_POLICY_VERSION,
            "gain": self.gain,
            "bias_x": self.bias_x,
            "bias_y": self.bias_y,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class Reset:
    start: tuple[float, float]
    target: tuple[float, float]

    def to_dict(self) -> dict[str, list[float]]:
        return {"start": list(self.start), "target": list(self.target)}


@dataclass(frozen=True)
class Episode:
    reset: Reset
    path: tuple[tuple[float, float], ...]
    success: bool
    steps: int
    final_distance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reset": self.reset.to_dict(),
            "path": [list(point) for point in self.path],
            "success": self.success,
            "steps": self.steps,
            "final_distance": self.final_distance,
        }


@dataclass(frozen=True)
class EvaluationMetrics:
    success_rate: float
    mean_final_distance: float
    successful_episode_length: float
    episode_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_rate": self.success_rate,
            "mean_final_distance": self.mean_final_distance,
            "successful_episode_length": self.successful_episode_length,
            "episode_count": self.episode_count,
        }


@dataclass(frozen=True)
class GenerationRecord:
    generation: int
    best_score: float
    mean_score: float
    residual_gain: float
    residual_bias_x: float
    residual_bias_y: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "best_score": self.best_score,
            "mean_score": self.mean_score,
            "residual_gain": self.residual_gain,
            "residual_bias_x": self.residual_bias_x,
            "residual_bias_y": self.residual_bias_y,
        }


@dataclass(frozen=True)
class TrainingResult:
    seed: int
    config: TrainingConfig
    policy: ResidualPolicy
    trace: tuple[GenerationRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": TOY_POLICY_VERSION,
            "seed": self.seed,
            "config": self.config.to_dict(),
            "config_hash": self.config.fingerprint(),
            "policy": self.policy.to_dict(),
            "policy_hash": self.policy.fingerprint(),
            "trace": [record.to_dict() for record in self.trace],
        }


def make_resets(seed: int, count: int) -> tuple[Reset, ...]:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ToyPolicyError("reset seed must be a non-negative integer")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ToyPolicyError("reset count must be a positive integer")
    generator = random.Random(seed)
    resets: list[Reset] = []
    while len(resets) < count:
        start = (generator.uniform(-1.0, 1.0), generator.uniform(-1.0, 1.0))
        target = (generator.uniform(-0.35, 0.35), generator.uniform(-0.35, 0.35))
        if math.dist(start, target) >= 0.55:
            resets.append(Reset(start=start, target=target))
    return tuple(resets)


def _clip(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def rollout(policy: ResidualPolicy, reset: Reset) -> Episode:
    position = reset.start
    path = [position]
    success = False
    success_step = HORIZON
    for step in range(1, HORIZON + 1):
        error_x = reset.target[0] - position[0]
        error_y = reset.target[1] - position[1]
        action_x = (
            BASE_GAIN * error_x
            + PLANT_DRIFT[0]
            + policy.gain * error_x
            + policy.bias_x
        )
        action_y = (
            BASE_GAIN * error_y
            + PLANT_DRIFT[1]
            + policy.gain * error_y
            + policy.bias_y
        )
        position = (
            position[0] + _clip(action_x, -MAX_ACTION, MAX_ACTION),
            position[1] + _clip(action_y, -MAX_ACTION, MAX_ACTION),
        )
        path.append(position)
        if math.dist(position, reset.target) <= SUCCESS_RADIUS:
            success = True
            success_step = step
            break
    return Episode(
        reset=reset,
        path=tuple(path),
        success=success,
        steps=success_step,
        final_distance=math.dist(position, reset.target),
    )


def evaluate_policy(
    policy: ResidualPolicy,
    resets: Sequence[Reset],
) -> tuple[EvaluationMetrics, tuple[Episode, ...]]:
    if not resets:
        raise ToyPolicyError("evaluation requires at least one reset")
    episodes = tuple(rollout(policy, reset) for reset in resets)
    successes = tuple(episode for episode in episodes if episode.success)
    return (
        EvaluationMetrics(
            success_rate=len(successes) / len(episodes),
            mean_final_distance=statistics.fmean(
                episode.final_distance for episode in episodes
            ),
            successful_episode_length=(
                statistics.fmean(episode.steps for episode in successes)
                if successes
                else float(HORIZON)
            ),
            episode_count=len(episodes),
        ),
        episodes,
    )


def _training_score(policy: ResidualPolicy, resets: Sequence[Reset]) -> float:
    metrics, _ = evaluate_policy(policy, resets)
    regularizer = 0.01 * (
        policy.gain * policy.gain
        + policy.bias_x * policy.bias_x
        + policy.bias_y * policy.bias_y
    )
    return 2.0 * metrics.success_rate - metrics.mean_final_distance - regularizer


def _bounded_parameters(values: Sequence[float]) -> tuple[float, float, float]:
    return (
        _clip(values[0], -0.30, 0.80),
        _clip(values[1], -0.20, 0.20),
        _clip(values[2], -0.20, 0.20),
    )


def train_policy(config: TrainingConfig, seed: int) -> TrainingResult:
    if not isinstance(config, TrainingConfig):
        raise ToyPolicyError("training requires a TrainingConfig")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ToyPolicyError("training seed must be a non-negative integer")
    generator = random.Random(seed)
    resets = make_resets(seed + 10_000, config.training_episodes)
    mean = [0.0, 0.0, 0.0]
    deviations = [config.exploration_std] * 3
    minimum_std = max(0.002, config.exploration_std * 0.08)
    trace: list[GenerationRecord] = []
    best: tuple[float, ResidualPolicy] | None = None

    for generation in range(config.generations):
        population: list[tuple[float, ResidualPolicy]] = []
        for index in range(config.population):
            values = mean if index == 0 else [
                generator.gauss(mean[dimension], deviations[dimension])
                for dimension in range(3)
            ]
            policy = ResidualPolicy.from_sequence(_bounded_parameters(values))
            population.append((_training_score(policy, resets), policy))
        population.sort(
            key=lambda item: (
                item[0],
                -abs(item[1].gain),
                -abs(item[1].bias_x),
                -abs(item[1].bias_y),
            ),
            reverse=True,
        )
        elite = population[: config.elite_count]
        if best is None or elite[0][0] > best[0]:
            best = elite[0]
        elite_values = [
            (item[1].gain, item[1].bias_x, item[1].bias_y) for item in elite
        ]
        for dimension in range(3):
            mean[dimension] = statistics.fmean(
                values[dimension] for values in elite_values
            )
            deviations[dimension] = max(
                minimum_std,
                statistics.pstdev(values[dimension] for values in elite_values),
            )
        assert best is not None
        trace.append(
            GenerationRecord(
                generation=generation + 1,
                best_score=best[0],
                mean_score=statistics.fmean(item[0] for item in population),
                residual_gain=best[1].gain,
                residual_bias_x=best[1].bias_x,
                residual_bias_y=best[1].bias_y,
            )
        )

    assert best is not None
    return TrainingResult(
        seed=seed,
        config=config,
        policy=best[1],
        trace=tuple(trace),
    )
