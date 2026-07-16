"""Transparent Phase 1 tuning and keep/revert/continue decisions."""

from __future__ import annotations

import math
from typing import Any, Literal

from agent.metrics import summarize_metrics


Decision = Literal["keep", "revert"]


# Rule constants stay in code so configs/phase1_overrides.yaml contains only
# the four experiment fields that this checkpoint explicitly allows changing.
SUCCESS_TARGET = 0.85
SUCCESS_EPSILON = 1e-9
REGULARIZATION_FACTOR = 0.8
LEARNING_RATE_FACTOR = 0.5
PLATEAU_WINDOW = 3
MIN_RELATIVE_LOSS_IMPROVEMENT = 0.01
USE_LOSS_TIEBREAKER = False


def propose_adjustment(
    parameters: dict[str, float],
    metrics: dict[str, list[float]],
) -> tuple[dict[str, float], str | None]:
    """Propose one bounded change, or return ``None`` to continue unchanged."""

    proposed = dict(parameters)
    summary = summarize_metrics(metrics)
    loss = summary["loss"]
    success = summary["success"]

    if loss is not None and not math.isfinite(loss):
        proposed["learning_rate"] *= LEARNING_RATE_FACTOR
        return proposed, "non-finite loss; reduced learning rate"

    if success is not None and success < SUCCESS_TARGET:
        proposed["regularization_strength"] *= REGULARIZATION_FACTOR
        return proposed, "evaluation success below target; relaxed reference regularization"

    loss_values = metrics.get(summary["loss_key"] or "", [])
    if len(loss_values) >= PLATEAU_WINDOW:
        start = loss_values[-PLATEAU_WINDOW]
        end = loss_values[-1]
        improvement = (start - end) / max(abs(start), 1e-12)
        if improvement < MIN_RELATIVE_LOSS_IMPROVEMENT:
            proposed["learning_rate"] *= LEARNING_RATE_FACTOR
            return proposed, "loss plateau; reduced learning rate"

    return proposed, None


def compare_runs(
    baseline: dict[str, Any], adjusted: dict[str, Any]
) -> tuple[Decision, str]:
    """Keep a success improvement; otherwise explicitly revert."""

    base_success = baseline.get("success")
    new_success = adjusted.get("success")
    if base_success is not None and new_success is not None:
        if new_success > base_success + SUCCESS_EPSILON:
            return "keep", "evaluation success improved"
        if new_success < base_success - SUCCESS_EPSILON:
            return "revert", "evaluation success regressed"
        if not USE_LOSS_TIEBREAKER:
            return "revert", "evaluation success tied; reverted to baseline"

    base_loss = baseline.get("loss")
    new_loss = adjusted.get("loss")
    if (
        base_loss is not None
        and new_loss is not None
        and math.isfinite(base_loss)
        and math.isfinite(new_loss)
    ):
        relative_drop = (base_loss - new_loss) / max(abs(base_loss), 1e-12)
        if relative_drop >= MIN_RELATIVE_LOSS_IMPROVEMENT:
            return "keep", f"success tied; loss improved by {relative_drop:.2%}"
        return "revert", f"no meaningful improvement (loss change {relative_drop:.2%})"

    return "revert", "insufficient comparable metrics; reverted"
