"""Audited outer-loop supervisor for bounded RLT improvement campaigns."""

from supervisor.canonical import ContractError
from supervisor.budget import (
    BudgetExceeded,
    BudgetRequest,
    BudgetSnapshot,
    BudgetTracker,
    BudgetUsage,
)
from supervisor.contracts import (
    ApprovalEnvelope,
    ArtifactRef,
    BudgetEnvelope,
    CampaignSpec,
    CampaignState,
    Decision,
    DecisionRecord,
    EditMode,
    ParameterKind,
    ParameterRule,
    TrialEvidence,
    TrialState,
    TrialStatus,
)
from supervisor.ledger import EntityType, EventLedger, LedgerCorruption, LedgerEvent
from supervisor.state import (
    CAMPAIGN_STATE_MACHINE,
    TRIAL_STATE_MACHINE,
    TransitionError,
)

__all__ = [
    "ApprovalEnvelope",
    "ArtifactRef",
    "BudgetExceeded",
    "BudgetEnvelope",
    "BudgetRequest",
    "BudgetSnapshot",
    "BudgetTracker",
    "BudgetUsage",
    "CAMPAIGN_STATE_MACHINE",
    "CampaignSpec",
    "CampaignState",
    "ContractError",
    "Decision",
    "DecisionRecord",
    "EditMode",
    "EntityType",
    "EventLedger",
    "LedgerCorruption",
    "LedgerEvent",
    "ParameterKind",
    "ParameterRule",
    "TrialEvidence",
    "TrialState",
    "TrialStatus",
    "TRIAL_STATE_MACHINE",
    "TransitionError",
]
