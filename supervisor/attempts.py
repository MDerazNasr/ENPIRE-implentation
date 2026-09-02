"""Bounded initial/repair orchestration for structured proposals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from supervisor.canonical import (
    ContractError,
    canonical_json,
    decimal_text,
    fingerprint,
    parse_decimal,
    require_identifier,
    timestamp_text,
)
from supervisor.context import ContextBundle
from supervisor.contracts import SCHEMA_VERSION, CampaignSpec
from supervisor.proposals import (
    PROPOSAL_SCHEMA_HASH,
    AttemptAudit,
    AttemptStatus,
    AttemptType,
    Proposal,
)
from supervisor.providers import (
    ProposalProvider,
    ProviderCallResult,
    ProviderError,
    ProviderTimeout,
)


@dataclass(frozen=True)
class ProposalSessionResult:
    proposal_slot_id: str
    accepted: bool
    proposal: Proposal | None
    attempts: tuple[AttemptAudit, ...]
    total_cost_usd: str

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "proposal_slot_id": self.proposal_slot_id,
            "accepted": self.accepted,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "total_cost_usd": self.total_cost_usd,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


def _repair_feedback(payload: dict, errors: tuple[str, ...]) -> str:
    feedback = {
        "validation_errors": list(errors),
        "invalid_response": payload,
    }
    try:
        rendered = canonical_json(feedback)
    except ContractError:
        rendered = canonical_json(
            {
                "validation_errors": list(errors),
                "invalid_response": "omitted: response was not canonical JSON",
            }
        )
    if len(rendered.encode("utf-8")) > 12_288:
        rendered = canonical_json(
            {
                "validation_errors": list(errors),
                "invalid_response_hash": fingerprint(payload),
                "invalid_response": "omitted: response exceeded repair context limit",
            }
        )
    return rendered


class ProposalAttemptController:
    def __init__(
        self,
        *,
        campaign: CampaignSpec,
        context: ContextBundle,
        incumbent_commit: str,
        provider: ProposalProvider,
        model: str,
        proposal_slot_id: str,
        max_total_cost_usd: str,
        timeout_seconds: int = 600,
        clock: Callable | None = None,
    ) -> None:
        from datetime import datetime, timezone

        self.campaign = campaign
        self.context = context
        self.incumbent_commit = incumbent_commit
        self.provider = provider
        self.model = require_identifier(model, "attempt_controller.model")
        self.proposal_slot_id = require_identifier(
            proposal_slot_id, "attempt_controller.proposal_slot_id"
        )
        self.max_total_cost = parse_decimal(
            max_total_cost_usd,
            "attempt_controller.max_total_cost_usd",
            allow_zero=False,
        )
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise ContractError("attempt_controller.timeout_seconds must be an integer")
        if not 1 <= timeout_seconds <= 600:
            raise ContractError("attempt_controller.timeout_seconds must be 1-600")
        if context.campaign_hash != campaign.fingerprint():
            raise ContractError("context does not match campaign")
        if context.incumbent_commit != incumbent_commit:
            raise ContractError("context does not match incumbent")
        self.timeout_seconds = timeout_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _audit(
        self,
        *,
        number: int,
        attempt_type: AttemptType,
        started_at: str,
        completed_at: str,
        max_budget: Decimal,
        reported_cost: Decimal,
        status: AttemptStatus,
        response_hash: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        errors: tuple[str, ...],
        proposal_hash: str | None,
    ) -> AttemptAudit:
        attempt_id = f"{self.proposal_slot_id[:110]}.a{number}"
        return AttemptAudit.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "attempt_id": attempt_id,
                "proposal_slot_id": self.proposal_slot_id,
                "attempt_number": number,
                "attempt_type": attempt_type.value,
                "provider": require_identifier(self.provider.name, "provider.name"),
                "model": self.model,
                "context_hash": self.context.context_hash,
                "schema_hash": PROPOSAL_SCHEMA_HASH,
                "started_at": started_at,
                "completed_at": completed_at,
                "timeout_seconds": self.timeout_seconds,
                "max_budget_usd": decimal_text(max_budget),
                "reported_cost_usd": decimal_text(reported_cost),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "response_hash": response_hash,
                "status": status.value,
                "validation_errors": list(errors),
                "proposal_hash": proposal_hash,
            }
        )

    def run(self) -> ProposalSessionResult:
        attempts: list[AttemptAudit] = []
        total_cost = Decimal(0)
        repair_feedback: str | None = None
        for number in (1, 2):
            attempt_type = AttemptType.INITIAL if number == 1 else AttemptType.REPAIR
            remaining = self.max_total_cost - total_cost
            if remaining <= 0:
                break
            started_fallback = timestamp_text(self.clock())
            try:
                result = self.provider.generate(
                    self.context,
                    model=self.model,
                    max_budget_usd=decimal_text(remaining),
                    timeout_seconds=self.timeout_seconds,
                    repair_feedback=repair_feedback,
                )
                if not isinstance(result, ProviderCallResult):
                    raise ProviderError("provider returned an unsupported result type")
                if result.provider != self.provider.name or result.model != self.model:
                    raise ProviderError("provider result identity does not match request")
            except ProviderTimeout as error:
                completed = timestamp_text(self.clock())
                attempts.append(
                    self._audit(
                        number=number,
                        attempt_type=attempt_type,
                        started_at=started_fallback,
                        completed_at=completed,
                        max_budget=remaining,
                        reported_cost=Decimal(0),
                        status=AttemptStatus.TIMEOUT,
                        response_hash=None,
                        input_tokens=None,
                        output_tokens=None,
                        errors=(str(error),),
                        proposal_hash=None,
                    )
                )
                break
            except ProviderError as error:
                completed = timestamp_text(self.clock())
                attempts.append(
                    self._audit(
                        number=number,
                        attempt_type=attempt_type,
                        started_at=started_fallback,
                        completed_at=completed,
                        max_budget=remaining,
                        reported_cost=Decimal(0),
                        status=AttemptStatus.PROVIDER_ERROR,
                        response_hash=None,
                        input_tokens=None,
                        output_tokens=None,
                        errors=(str(error),),
                        proposal_hash=None,
                    )
                )
                break
            cost = parse_decimal(result.reported_cost_usd, "provider reported cost")
            total_cost += cost
            if cost > remaining:
                attempts.append(
                    self._audit(
                        number=number,
                        attempt_type=attempt_type,
                        started_at=result.started_at,
                        completed_at=result.completed_at,
                        max_budget=remaining,
                        reported_cost=cost,
                        status=AttemptStatus.BUDGET_EXCEEDED,
                        response_hash=result.response_hash,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        errors=("provider reported cost exceeded remaining session budget",),
                        proposal_hash=None,
                    )
                )
                break
            proposal: Proposal | None = None
            errors: tuple[str, ...] = ()
            try:
                proposal = Proposal.from_dict(dict(result.proposal_payload))
                proposal.validate_for_campaign(
                    self.campaign, incumbent_commit=self.incumbent_commit
                )
            except ContractError as error:
                errors = (str(error),)
            if not errors and proposal is not None:
                attempts.append(
                    self._audit(
                        number=number,
                        attempt_type=attempt_type,
                        started_at=result.started_at,
                        completed_at=result.completed_at,
                        max_budget=remaining,
                        reported_cost=cost,
                        status=AttemptStatus.ACCEPTED,
                        response_hash=result.response_hash,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        errors=(),
                        proposal_hash=proposal.fingerprint(),
                    )
                )
                return ProposalSessionResult(
                    proposal_slot_id=self.proposal_slot_id,
                    accepted=True,
                    proposal=proposal,
                    attempts=tuple(attempts),
                    total_cost_usd=decimal_text(total_cost),
                )
            attempts.append(
                self._audit(
                    number=number,
                    attempt_type=attempt_type,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    max_budget=remaining,
                    reported_cost=cost,
                    status=AttemptStatus.INVALID,
                    response_hash=result.response_hash,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    errors=errors,
                    proposal_hash=proposal.fingerprint() if proposal else None,
                )
            )
            if number == 1:
                repair_feedback = _repair_feedback(
                    dict(result.proposal_payload), errors
                )
        return ProposalSessionResult(
            proposal_slot_id=self.proposal_slot_id,
            accepted=False,
            proposal=None,
            attempts=tuple(attempts),
            total_cost_usd=decimal_text(total_cost),
        )
