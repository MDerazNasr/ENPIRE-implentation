"""Harness-owned boundary around the editable actor-objective function."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from supervisor.canonical import ContractError
from supervisor.objectives.actor_objective import combine_actor_objective


class ObjectiveError(ContractError):
    """Raised when an actor-objective plugin returns an invalid value."""


def frozen_reference_objective(actor_loss, bc_loss, bc_weight):
    """Pinned algebraic reference used by pre-integration equivalence fixtures."""

    return actor_loss + bc_weight * bc_loss


@dataclass(frozen=True)
class ActorObjectiveAdapter:
    plugin: Callable[[Any, Any, Any], Any] = combine_actor_objective

    def combine(self, actor_loss, bc_loss, bc_weight):
        result = self.plugin(actor_loss, bc_loss, bc_weight)
        if result is None:
            raise ObjectiveError("actor-objective plugin returned null")
        if isinstance(result, (int, float)) and not math.isfinite(float(result)):
            raise ObjectiveError("actor-objective plugin returned a non-finite scalar")
        return result
