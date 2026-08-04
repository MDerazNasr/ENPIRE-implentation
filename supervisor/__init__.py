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
from supervisor.attempts import ProposalAttemptController, ProposalSessionResult
from supervisor.context import (
    ContextBundle,
    ContextRejected,
    PriorTrialSummary,
    SourceExcerpt,
    build_context,
)
from supervisor.proposals import (
    PROPOSAL_SCHEMA_HASH,
    AttemptAudit,
    AttemptStatus,
    AttemptType,
    Proposal,
    proposal_json_schema,
)
from supervisor.providers import (
    ClaudeCliProvider,
    FakeProposalProvider,
    ProposalProvider,
    ProviderCallResult,
    ProviderError,
    ProviderTimeout,
)
from supervisor.state import (
    CAMPAIGN_STATE_MACHINE,
    TRIAL_STATE_MACHINE,
    TransitionError,
)

__all__ = [
    "ApprovalEnvelope",
    "ArtifactRef",
    "AttemptAudit",
    "AttemptStatus",
    "AttemptType",
    "BudgetExceeded",
    "BudgetEnvelope",
    "BudgetRequest",
    "BudgetSnapshot",
    "BudgetTracker",
    "BudgetUsage",
    "CAMPAIGN_STATE_MACHINE",
    "CampaignSpec",
    "CampaignState",
    "ClaudeCliProvider",
    "ContractError",
    "ContextBundle",
    "ContextRejected",
    "Decision",
    "DecisionRecord",
    "EditMode",
    "EntityType",
    "EventLedger",
    "FakeProposalProvider",
    "LedgerCorruption",
    "LedgerEvent",
    "ParameterKind",
    "ParameterRule",
    "PriorTrialSummary",
    "PROPOSAL_SCHEMA_HASH",
    "Proposal",
    "ProposalAttemptController",
    "ProposalProvider",
    "ProposalSessionResult",
    "ProviderCallResult",
    "ProviderError",
    "ProviderTimeout",
    "SourceExcerpt",
    "TrialEvidence",
    "TrialState",
    "TrialStatus",
    "TRIAL_STATE_MACHINE",
    "TransitionError",
    "build_context",
    "proposal_json_schema",
]
