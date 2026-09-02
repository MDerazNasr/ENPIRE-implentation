"""Deterministic campaign and trial lifecycle validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterable, Mapping, TypeVar

from supervisor.canonical import ContractError
from supervisor.contracts import CampaignState, StringEnum, TrialState


StateT = TypeVar("StateT", bound=StringEnum)


class TransitionError(ContractError):
    """Raised when a lifecycle transition is not allowed."""


@dataclass(frozen=True)
class StateMachine(Generic[StateT]):
    name: str
    initial: StateT
    transitions: Mapping[StateT, frozenset[StateT]]

    def transition(self, current: StateT, target: StateT) -> StateT:
        allowed = self.transitions.get(current, frozenset())
        if target not in allowed:
            options = ", ".join(sorted(state.value for state in allowed)) or "none"
            raise TransitionError(
                f"invalid {self.name} transition {current.value!r} -> "
                f"{target.value!r}; allowed: {options}"
            )
        return target

    def replay(self, transitions: Iterable[tuple[StateT, StateT]]) -> StateT:
        current = self.initial
        for declared_from, target in transitions:
            if declared_from != current:
                raise TransitionError(
                    f"{self.name} transition declares {declared_from.value!r}, "
                    f"but replay state is {current.value!r}"
                )
            current = self.transition(current, target)
        return current


CAMPAIGN_STATE_MACHINE = StateMachine(
    name="campaign",
    initial=CampaignState.DRAFT,
    transitions={
        CampaignState.DRAFT: frozenset(
            {CampaignState.VALIDATED, CampaignState.CANCELLED}
        ),
        CampaignState.VALIDATED: frozenset(
            {CampaignState.APPROVED, CampaignState.CANCELLED}
        ),
        CampaignState.APPROVED: frozenset(
            {CampaignState.ACTIVE, CampaignState.CANCELLED}
        ),
        CampaignState.ACTIVE: frozenset(
            {
                CampaignState.COMPLETED,
                CampaignState.FAILED,
                CampaignState.CANCELLED,
            }
        ),
        CampaignState.COMPLETED: frozenset(),
        CampaignState.FAILED: frozenset(),
        CampaignState.CANCELLED: frozenset(),
    },
)


TRIAL_STATE_MACHINE = StateMachine(
    name="trial",
    initial=TrialState.PROPOSING,
    transitions={
        TrialState.PROPOSING: frozenset(
            {
                TrialState.PROPOSAL_VALIDATED,
                TrialState.FAILED,
                TrialState.CANCELLED,
            }
        ),
        TrialState.PROPOSAL_VALIDATED: frozenset(
            {TrialState.QUEUED, TrialState.FAILED, TrialState.CANCELLED}
        ),
        TrialState.QUEUED: frozenset(
            {TrialState.RUNNING, TrialState.FAILED, TrialState.CANCELLED}
        ),
        TrialState.RUNNING: frozenset(
            {TrialState.EVALUATED, TrialState.FAILED, TrialState.CANCELLED}
        ),
        TrialState.EVALUATED: frozenset(
            {
                TrialState.KEPT,
                TrialState.REVERTED,
                TrialState.INCONCLUSIVE,
                TrialState.FAILED,
            }
        ),
        TrialState.KEPT: frozenset(),
        TrialState.REVERTED: frozenset(),
        TrialState.INCONCLUSIVE: frozenset(),
        TrialState.FAILED: frozenset(),
        TrialState.CANCELLED: frozenset(),
    },
)
