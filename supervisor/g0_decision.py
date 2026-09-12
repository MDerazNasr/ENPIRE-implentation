"""Frozen G0 paired-seed decision rule, separate from historical D1 replay."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Literal, Sequence


G0Decision = Literal["keep", "revert", "inconclusive"]
T_CRITICAL_95_DF2 = 4.303
MINIMUM_EFFECT = 0.05


@dataclass(frozen=True)
class G0DecisionResult:
    decision: G0Decision
    reason: str
    control_mean_success: float | None
    candidate_mean_success: float | None
    mean_success_delta: float | None
    success_delta_ci95: tuple[float, float] | None


def _valid_rates(values: Sequence[float]) -> bool:
    return len(values) == 3 and all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
        for value in values
    )


def decide_g0_candidate(
    control_success: Sequence[float], candidate_success: Sequence[float]
) -> G0DecisionResult:
    """Apply the accepted G0 v1 primary-endpoint rule to three paired seeds."""

    if not _valid_rates(control_success) or not _valid_rates(candidate_success):
        return G0DecisionResult(
            "inconclusive",
            "missing or invalid paired success values for the three frozen seeds",
            None,
            None,
            None,
            None,
        )
    control_mean = statistics.fmean(control_success)
    candidate_mean = statistics.fmean(candidate_success)
    deltas = [candidate - control for control, candidate in zip(control_success, candidate_success)]
    delta_mean = statistics.fmean(deltas)
    standard_error = statistics.stdev(deltas) / math.sqrt(3)
    margin = T_CRITICAL_95_DF2 * standard_error
    interval = (delta_mean - margin, delta_mean + margin)
    if delta_mean >= MINIMUM_EFFECT and interval[0] > 0:
        decision = "keep"
        reason = "mean success improved by at least 5 points and paired CI95 is above zero"
    elif interval[1] < 0:
        decision = "revert"
        reason = "paired CI95 is below zero"
    else:
        decision = "inconclusive"
        reason = "valid evidence does not satisfy the frozen KEEP or REVERT boundary"
    return G0DecisionResult(
        decision,
        reason,
        control_mean,
        candidate_mean,
        delta_mean,
        interval,
    )
