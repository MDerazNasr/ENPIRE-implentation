"""Preregistered D1 scientific keep/revert/inconclusive decision rule."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Literal, Sequence


D1Decision = Literal["keep", "revert", "inconclusive"]
T_975 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


@dataclass(frozen=True)
class D1DecisionResult:
    decision: D1Decision
    reason: str
    control_mean_success: float | None
    candidate_mean_success: float | None
    mean_success_delta: float | None
    success_delta_ci95: tuple[float, float] | None


def _valid_rates(values: Sequence[float], expected_count: int) -> bool:
    return len(values) == expected_count and all(
        math.isfinite(value) and 0 <= value <= 1 for value in values
    )


def _paired_interval(deltas: Sequence[float]) -> tuple[float, float] | None:
    if len(deltas) < 2:
        return None
    mean = statistics.fmean(deltas)
    standard_error = statistics.stdev(deltas) / math.sqrt(len(deltas))
    critical = T_975.get(len(deltas) - 1, 1.96)
    margin = critical * standard_error
    return mean - margin, mean + margin


def decide_d1_candidate(
    control_success: Sequence[float],
    candidate_success: Sequence[float],
    *,
    control_successful_episode_length: Sequence[float] | None = None,
    candidate_successful_episode_length: Sequence[float] | None = None,
    expected_seeds: int = 3,
) -> D1DecisionResult:
    """Apply the Stage-0 rule to paired per-seed aggregate outcomes."""

    if not _valid_rates(control_success, expected_seeds) or not _valid_rates(
        candidate_success, expected_seeds
    ):
        return D1DecisionResult(
            "inconclusive",
            "missing or invalid paired success values for the approved seeds",
            None,
            None,
            None,
            None,
        )
    control_mean = statistics.fmean(control_success)
    candidate_mean = statistics.fmean(candidate_success)
    deltas = [new - base for base, new in zip(control_success, candidate_success)]
    delta_mean = statistics.fmean(deltas)
    interval = _paired_interval(deltas)
    if interval is None:
        return D1DecisionResult(
            "inconclusive",
            "insufficient paired observations for a 95% interval",
            control_mean,
            candidate_mean,
            delta_mean,
            None,
        )

    if control_mean < 0.90:
        if delta_mean >= 0.05 and interval[0] > 0:
            decision, reason = "keep", "success improved by >=5 points with CI95 above zero"
        else:
            decision, reason = "revert", "candidate failed the below-ceiling success rule"
        return D1DecisionResult(
            decision, reason, control_mean, candidate_mean, delta_mean, interval
        )

    control_lengths = control_successful_episode_length
    candidate_lengths = candidate_successful_episode_length
    if (
        control_lengths is None
        or candidate_lengths is None
        or len(control_lengths) != expected_seeds
        or len(candidate_lengths) != expected_seeds
        or not all(
            math.isfinite(value) and value > 0
            for value in [*control_lengths, *candidate_lengths]
        )
    ):
        return D1DecisionResult(
            "inconclusive",
            "ceiling case requires positive successful-episode lengths for every seed",
            control_mean,
            candidate_mean,
            delta_mean,
            interval,
        )
    non_inferior = candidate_mean >= control_mean - 0.05
    control_length_mean = statistics.fmean(control_lengths)
    candidate_length_mean = statistics.fmean(candidate_lengths)
    efficient = candidate_length_mean <= 0.90 * control_length_mean
    if non_inferior and efficient:
        decision = "keep"
        reason = "success is non-inferior and successful episodes are >=10% shorter"
    else:
        decision, reason = "revert", "candidate failed the ceiling success/efficiency rule"
    return D1DecisionResult(
        decision, reason, control_mean, candidate_mean, delta_mean, interval
    )
