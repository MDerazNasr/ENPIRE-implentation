"""Structured proposal and provider-attempt contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from supervisor.budget import BudgetRequest
from supervisor.canonical import (
    ContractError,
    canonical_json,
    decimal_text,
    fingerprint,
    parse_decimal,
    parse_timestamp,
    require_exact_keys,
    require_git_commit,
    require_identifier,
    require_nonempty_text,
    require_safe_relative_path,
    require_sha256,
)
from supervisor.contracts import (
    SCHEMA_VERSION,
    CampaignSpec,
    EditMode,
    ParameterKind,
)


MAX_DIFF_BYTES = 65_536
MAX_HYPOTHESIS_CHARS = 4_096
MAX_TESTS = 16


class AttemptType(str, Enum):
    INITIAL = "initial"
    REPAIR = "repair"


class AttemptStatus(str, Enum):
    ACCEPTED = "accepted"
    INVALID = "invalid"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"


def _unique_identifiers(value: Any, field: str, *, minimum: int = 1) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ContractError(f"{field} must contain at least {minimum} item(s)")
    normalized = tuple(
        require_identifier(item, f"{field}[{index}]") for index, item in enumerate(value)
    )
    if len(set(normalized)) != len(normalized):
        raise ContractError(f"{field} must contain unique identifiers")
    return normalized


def _config_value(value: Any, field: str) -> str | int | float | bool:
    if not isinstance(value, (str, int, float, bool)) or value is None:
        raise ContractError(f"{field} must be a JSON scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{field} must be finite")
    return value


@dataclass(frozen=True)
class Proposal:
    schema_version: int
    proposal_id: str
    campaign_id: str
    arm_id: str
    base_commit: str
    edit_mode: EditMode
    hypothesis: str
    evidence_ids: tuple[str, ...]
    expected_effect: str
    falsification_condition: str
    rollback_condition: str
    changed_paths: tuple[str, ...]
    requested_tests: tuple[str, ...]
    estimated_budget: BudgetRequest
    config_overrides: Mapping[str, str | int | float | bool] | None
    unified_diff: str | None

    @classmethod
    def from_dict(cls, value: Any) -> "Proposal":
        required = {
            "schema_version",
            "proposal_id",
            "campaign_id",
            "arm_id",
            "base_commit",
            "edit_mode",
            "hypothesis",
            "evidence_ids",
            "expected_effect",
            "falsification_condition",
            "rollback_condition",
            "changed_paths",
            "requested_tests",
            "estimated_budget",
        }
        data = require_exact_keys(
            value,
            "proposal",
            required,
            {"config_overrides", "unified_diff"},
        )
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"proposal.schema_version must be {SCHEMA_VERSION}")
        try:
            edit_mode = EditMode(data["edit_mode"])
        except (TypeError, ValueError) as error:
            raise ContractError("proposal.edit_mode is unsupported") from error
        paths = data["changed_paths"]
        if not isinstance(paths, list) or not paths:
            raise ContractError("proposal.changed_paths must be a non-empty list")
        changed_paths = tuple(
            require_safe_relative_path(item, f"proposal.changed_paths[{index}]")
            for index, item in enumerate(paths)
        )
        if len(set(changed_paths)) != len(changed_paths):
            raise ContractError("proposal.changed_paths must be unique")
        tests = _unique_identifiers(data["requested_tests"], "proposal.requested_tests")
        if len(tests) > MAX_TESTS:
            raise ContractError(f"proposal.requested_tests may not exceed {MAX_TESTS}")
        raw_budget = require_exact_keys(
            data["estimated_budget"],
            "proposal.estimated_budget",
            {"wall_time_seconds", "gpu_cost_usd", "llm_cost_usd"},
        )
        budget = BudgetRequest.create(
            wall_time_seconds=raw_budget["wall_time_seconds"],
            gpu_cost_usd=raw_budget["gpu_cost_usd"],
            llm_cost_usd=raw_budget["llm_cost_usd"],
        )
        config_overrides: Mapping[str, str | int | float | bool] | None = None
        unified_diff: str | None = None
        if edit_mode == EditMode.CONFIG_ONLY:
            if "unified_diff" in data or "config_overrides" not in data:
                raise ContractError(
                    "config-only proposals require config_overrides and forbid unified_diff"
                )
            raw_overrides = data["config_overrides"]
            if not isinstance(raw_overrides, dict) or not raw_overrides:
                raise ContractError("proposal.config_overrides must be a non-empty object")
            config_overrides = MappingProxyType(
                {
                    require_identifier(name, "proposal.config_overrides key"): _config_value(
                        item, f"proposal.config_overrides.{name}"
                    )
                    for name, item in raw_overrides.items()
                }
            )
        else:
            if "config_overrides" in data or "unified_diff" not in data:
                raise ContractError(
                    "code proposals require unified_diff and forbid config_overrides"
                )
            unified_diff = require_nonempty_text(
                data["unified_diff"], "proposal.unified_diff", max_length=MAX_DIFF_BYTES
            )
            if len(unified_diff.encode("utf-8")) > MAX_DIFF_BYTES:
                raise ContractError(
                    f"proposal.unified_diff may not exceed {MAX_DIFF_BYTES} UTF-8 bytes"
                )
            if not unified_diff.startswith("diff --git "):
                raise ContractError("proposal.unified_diff must start with a Git diff header")
        return cls(
            schema_version=SCHEMA_VERSION,
            proposal_id=require_identifier(data["proposal_id"], "proposal.proposal_id"),
            campaign_id=require_identifier(data["campaign_id"], "proposal.campaign_id"),
            arm_id=require_identifier(data["arm_id"], "proposal.arm_id"),
            base_commit=require_git_commit(data["base_commit"], "proposal.base_commit"),
            edit_mode=edit_mode,
            hypothesis=require_nonempty_text(
                data["hypothesis"],
                "proposal.hypothesis",
                max_length=MAX_HYPOTHESIS_CHARS,
            ),
            evidence_ids=_unique_identifiers(
                data["evidence_ids"], "proposal.evidence_ids"
            ),
            expected_effect=require_nonempty_text(
                data["expected_effect"], "proposal.expected_effect"
            ),
            falsification_condition=require_nonempty_text(
                data["falsification_condition"], "proposal.falsification_condition"
            ),
            rollback_condition=require_nonempty_text(
                data["rollback_condition"], "proposal.rollback_condition"
            ),
            changed_paths=changed_paths,
            requested_tests=tests,
            estimated_budget=budget,
            config_overrides=config_overrides,
            unified_diff=unified_diff,
        )

    def _validate_parameter(self, campaign: CampaignSpec, name: str, value: Any) -> None:
        rule = campaign.allowed_parameters.get(name)
        if rule is None:
            raise ContractError(f"proposal parameter is not allowlisted: {name}")
        if rule.kind == ParameterKind.ENUM:
            if not isinstance(value, str) or value not in rule.choices:
                raise ContractError(f"proposal parameter {name!r} is outside enum choices")
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractError(f"proposal parameter {name!r} must be numeric")
        numeric = parse_decimal(value, f"proposal.config_overrides.{name}")
        minimum = parse_decimal(rule.minimum, f"campaign parameter {name} minimum")
        maximum = parse_decimal(rule.maximum, f"campaign parameter {name} maximum")
        if not minimum <= numeric <= maximum:
            raise ContractError(f"proposal parameter {name!r} is outside approved bounds")
        if rule.kind == ParameterKind.INTEGER and numeric != numeric.to_integral_value():
            raise ContractError(f"proposal parameter {name!r} must be integral")

    def validate_for_campaign(
        self,
        campaign: CampaignSpec,
        *,
        incumbent_commit: str,
    ) -> None:
        incumbent_commit = require_git_commit(incumbent_commit, "incumbent_commit")
        if self.campaign_id != campaign.campaign_id:
            raise ContractError("proposal campaign ID does not match campaign")
        if self.base_commit != incumbent_commit:
            raise ContractError("proposal base commit does not match the current incumbent")
        if self.edit_mode != campaign.edit_mode:
            raise ContractError("proposal edit mode does not match campaign")
        outside_scope = sorted(set(self.changed_paths) - set(campaign.editable_paths))
        if outside_scope:
            raise ContractError(
                f"proposal changed paths are outside campaign scope: {outside_scope}"
            )
        if self.config_overrides is not None:
            for name, value in self.config_overrides.items():
                self._validate_parameter(campaign, name, value)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "campaign_id": self.campaign_id,
            "arm_id": self.arm_id,
            "base_commit": self.base_commit,
            "edit_mode": self.edit_mode.value,
            "hypothesis": self.hypothesis,
            "evidence_ids": list(self.evidence_ids),
            "expected_effect": self.expected_effect,
            "falsification_condition": self.falsification_condition,
            "rollback_condition": self.rollback_condition,
            "changed_paths": list(self.changed_paths),
            "requested_tests": list(self.requested_tests),
            "estimated_budget": {
                "wall_time_seconds": self.estimated_budget.wall_time_seconds,
                "gpu_cost_usd": self.estimated_budget.gpu_cost_usd,
                "llm_cost_usd": self.estimated_budget.llm_cost_usd,
            },
        }
        if self.config_overrides is not None:
            data["config_overrides"] = dict(sorted(self.config_overrides.items()))
        else:
            data["unified_diff"] = self.unified_diff
        return data

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


def proposal_json_schema() -> dict[str, Any]:
    """Return the structured-output schema passed to Claude."""

    base_properties: dict[str, Any] = {
        "schema_version": {"const": SCHEMA_VERSION},
        "proposal_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "campaign_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "arm_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "base_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "edit_mode": {"enum": [mode.value for mode in EditMode]},
        "hypothesis": {"type": "string", "minLength": 1},
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "expected_effect": {"type": "string", "minLength": 1},
        "falsification_condition": {"type": "string", "minLength": 1},
        "rollback_condition": {"type": "string", "minLength": 1},
        "changed_paths": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "requested_tests": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_TESTS,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "estimated_budget": {
            "type": "object",
            "additionalProperties": False,
            "required": ["wall_time_seconds", "gpu_cost_usd", "llm_cost_usd"],
            "properties": {
                "wall_time_seconds": {"type": "integer", "minimum": 1},
                "gpu_cost_usd": {"type": "string", "pattern": "^[0-9]+(?:\\.[0-9]+)?$"},
                "llm_cost_usd": {"type": "string", "pattern": "^[0-9]+(?:\\.[0-9]+)?$"},
            },
        },
        "config_overrides": {"type": "object", "minProperties": 1},
        "unified_diff": {"type": "string", "minLength": 1},
    }
    common = [
        "schema_version",
        "proposal_id",
        "campaign_id",
        "arm_id",
        "base_commit",
        "edit_mode",
        "hypothesis",
        "evidence_ids",
        "expected_effect",
        "falsification_condition",
        "rollback_condition",
        "changed_paths",
        "requested_tests",
        "estimated_budget",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": base_properties,
        "oneOf": [
            {
                "required": [*common, "config_overrides"],
                "properties": {"edit_mode": {"const": EditMode.CONFIG_ONLY.value}},
                "not": {"required": ["unified_diff"]},
            },
            {
                "required": [*common, "unified_diff"],
                "properties": {
                    "edit_mode": {"const": EditMode.ACTOR_OBJECTIVE_CODE.value}
                },
                "not": {"required": ["config_overrides"]},
            },
        ],
    }


@dataclass(frozen=True)
class AttemptAudit:
    schema_version: int
    attempt_id: str
    proposal_slot_id: str
    attempt_number: int
    attempt_type: AttemptType
    provider: str
    model: str
    context_hash: str
    schema_hash: str
    started_at: str
    completed_at: str
    timeout_seconds: int
    max_budget_usd: str
    reported_cost_usd: str
    input_tokens: int | None
    output_tokens: int | None
    response_hash: str | None
    status: AttemptStatus
    validation_errors: tuple[str, ...]
    proposal_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "proposal_slot_id": self.proposal_slot_id,
            "attempt_number": self.attempt_number,
            "attempt_type": self.attempt_type.value,
            "provider": self.provider,
            "model": self.model,
            "context_hash": self.context_hash,
            "schema_hash": self.schema_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "timeout_seconds": self.timeout_seconds,
            "max_budget_usd": self.max_budget_usd,
            "reported_cost_usd": self.reported_cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "response_hash": self.response_hash,
            "status": self.status.value,
            "validation_errors": list(self.validation_errors),
            "proposal_hash": self.proposal_hash,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AttemptAudit":
        fields = {
            "schema_version",
            "attempt_id",
            "proposal_slot_id",
            "attempt_number",
            "attempt_type",
            "provider",
            "model",
            "context_hash",
            "schema_hash",
            "started_at",
            "completed_at",
            "timeout_seconds",
            "max_budget_usd",
            "reported_cost_usd",
            "input_tokens",
            "output_tokens",
            "response_hash",
            "status",
            "validation_errors",
            "proposal_hash",
        }
        data = require_exact_keys(value, "attempt", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"attempt.schema_version must be {SCHEMA_VERSION}")
        try:
            attempt_type = AttemptType(data["attempt_type"])
            status = AttemptStatus(data["status"])
        except (TypeError, ValueError) as error:
            raise ContractError("attempt type or status is unsupported") from error
        number = data["attempt_number"]
        timeout = data["timeout_seconds"]
        if isinstance(number, bool) or number not in (1, 2):
            raise ContractError("attempt.attempt_number must be 1 or 2")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise ContractError("attempt.timeout_seconds must be positive")
        if (number == 1) != (attempt_type == AttemptType.INITIAL):
            raise ContractError("attempt number and type do not agree")
        started = parse_timestamp(data["started_at"], "attempt.started_at")
        completed = parse_timestamp(data["completed_at"], "attempt.completed_at")
        if completed < started:
            raise ContractError("attempt.completed_at precedes started_at")
        errors = data["validation_errors"]
        if not isinstance(errors, list) or not all(
            isinstance(item, str) and item for item in errors
        ):
            raise ContractError("attempt.validation_errors must contain non-empty strings")

        def optional_tokens(raw: Any, field: str) -> int | None:
            if raw is None:
                return None
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise ContractError(f"{field} must be a non-negative integer or null")
            return raw

        response_hash = data["response_hash"]
        proposal_hash = data["proposal_hash"]
        if response_hash is not None:
            response_hash = require_sha256(response_hash, "attempt.response_hash")
        if proposal_hash is not None:
            proposal_hash = require_sha256(proposal_hash, "attempt.proposal_hash")
        max_budget = parse_decimal(data["max_budget_usd"], "attempt.max_budget_usd")
        reported_cost = parse_decimal(
            data["reported_cost_usd"], "attempt.reported_cost_usd"
        )
        if status != AttemptStatus.BUDGET_EXCEEDED and reported_cost > max_budget:
            raise ContractError("attempt reported cost exceeds its attempt budget")
        if status == AttemptStatus.ACCEPTED:
            if errors or response_hash is None or proposal_hash is None:
                raise ContractError(
                    "accepted attempts require response/proposal hashes and no errors"
                )
        elif status == AttemptStatus.INVALID:
            if not errors or response_hash is None:
                raise ContractError("invalid attempts require errors and a response hash")
        elif status in {AttemptStatus.PROVIDER_ERROR, AttemptStatus.TIMEOUT}:
            if not errors or proposal_hash is not None:
                raise ContractError(
                    "provider failures require errors and may not carry a proposal hash"
                )
        elif status == AttemptStatus.BUDGET_EXCEEDED:
            if not errors or response_hash is None:
                raise ContractError(
                    "budget-exceeded attempts require errors and a response hash"
                )
        return cls(
            schema_version=SCHEMA_VERSION,
            attempt_id=require_identifier(data["attempt_id"], "attempt.attempt_id"),
            proposal_slot_id=require_identifier(
                data["proposal_slot_id"], "attempt.proposal_slot_id"
            ),
            attempt_number=number,
            attempt_type=attempt_type,
            provider=require_identifier(data["provider"], "attempt.provider"),
            model=require_identifier(data["model"], "attempt.model"),
            context_hash=require_sha256(data["context_hash"], "attempt.context_hash"),
            schema_hash=require_sha256(data["schema_hash"], "attempt.schema_hash"),
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            timeout_seconds=timeout,
            max_budget_usd=decimal_text(max_budget),
            reported_cost_usd=decimal_text(reported_cost),
            input_tokens=optional_tokens(data["input_tokens"], "attempt.input_tokens"),
            output_tokens=optional_tokens(data["output_tokens"], "attempt.output_tokens"),
            response_hash=response_hash,
            status=status,
            validation_errors=tuple(errors),
            proposal_hash=proposal_hash,
        )

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


PROPOSAL_SCHEMA_HASH = fingerprint(proposal_json_schema())
PROPOSAL_SCHEMA_JSON = canonical_json(proposal_json_schema())
