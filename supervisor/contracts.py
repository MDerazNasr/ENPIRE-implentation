"""Versioned public data contracts for the coding-agent supervisor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from supervisor.canonical import (
    ContractError,
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


SCHEMA_VERSION = 1
ZERO_HASH = "0" * 64


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class EditMode(StringEnum):
    CONFIG_ONLY = "config_only"
    ACTOR_OBJECTIVE_CODE = "actor_objective_code"


class CampaignState(StringEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrialState(StringEnum):
    PROPOSING = "proposing"
    PROPOSAL_VALIDATED = "proposal_validated"
    QUEUED = "queued"
    RUNNING = "running"
    RECORDED = "recorded"
    EVALUATED = "evaluated"
    KEPT = "kept"
    REVERTED = "reverted"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Decision(StringEnum):
    KEEP = "keep"
    REVERT = "revert"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class TrialStatus(StringEnum):
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ParameterKind(StringEnum):
    NUMBER = "number"
    INTEGER = "integer"
    ENUM = "enum"


def _enum_value(enum_type: type[StringEnum], value: Any, field: str) -> StringEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ContractError(f"{field} must be one of: {allowed}") from error


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class ParameterRule:
    kind: ParameterKind
    minimum: str | None = None
    maximum: str | None = None
    choices: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Any, field: str) -> "ParameterRule":
        data = require_exact_keys(
            value,
            field,
            {"kind"},
            {"minimum", "maximum", "choices"},
        )
        kind = _enum_value(ParameterKind, data["kind"], f"{field}.kind")
        if kind == ParameterKind.ENUM:
            choices = data.get("choices")
            if (
                not isinstance(choices, list)
                or not choices
                or not all(isinstance(item, str) and item for item in choices)
                or len(set(choices)) != len(choices)
            ):
                raise ContractError(f"{field}.choices must be unique non-empty strings")
            if "minimum" in data or "maximum" in data:
                raise ContractError(f"{field}: enum rules may not define numeric bounds")
            return cls(kind=kind, choices=tuple(choices))
        if "choices" in data:
            raise ContractError(f"{field}: numeric rules may not define choices")
        minimum = parse_decimal(data.get("minimum"), f"{field}.minimum")
        maximum = parse_decimal(data.get("maximum"), f"{field}.maximum")
        if minimum > maximum:
            raise ContractError(f"{field}.minimum may not exceed maximum")
        if kind == ParameterKind.INTEGER and (
            minimum != minimum.to_integral_value()
            or maximum != maximum.to_integral_value()
        ):
            raise ContractError(f"{field}: integer bounds must be integral")
        return cls(
            kind=kind,
            minimum=decimal_text(minimum),
            maximum=decimal_text(maximum),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind.value}
        if self.kind == ParameterKind.ENUM:
            data["choices"] = list(self.choices)
        else:
            data.update(minimum=self.minimum, maximum=self.maximum)
        return data


@dataclass(frozen=True)
class BudgetEnvelope:
    max_trials: int
    max_wall_time_seconds: int
    max_gpu_cost_usd: str
    max_llm_cost_usd: str

    @classmethod
    def from_dict(cls, value: Any, field: str = "budget") -> "BudgetEnvelope":
        data = require_exact_keys(
            value,
            field,
            {
                "max_trials",
                "max_wall_time_seconds",
                "max_gpu_cost_usd",
                "max_llm_cost_usd",
            },
        )
        return cls(
            max_trials=_positive_int(data["max_trials"], f"{field}.max_trials"),
            max_wall_time_seconds=_positive_int(
                data["max_wall_time_seconds"], f"{field}.max_wall_time_seconds"
            ),
            max_gpu_cost_usd=decimal_text(
                parse_decimal(
                    data["max_gpu_cost_usd"],
                    f"{field}.max_gpu_cost_usd",
                    allow_zero=False,
                )
            ),
            max_llm_cost_usd=decimal_text(
                parse_decimal(
                    data["max_llm_cost_usd"],
                    f"{field}.max_llm_cost_usd",
                    allow_zero=False,
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_trials": self.max_trials,
            "max_wall_time_seconds": self.max_wall_time_seconds,
            "max_gpu_cost_usd": self.max_gpu_cost_usd,
            "max_llm_cost_usd": self.max_llm_cost_usd,
        }

    def gpu_cost(self) -> Decimal:
        return parse_decimal(self.max_gpu_cost_usd, "max_gpu_cost_usd")

    def llm_cost(self) -> Decimal:
        return parse_decimal(self.max_llm_cost_usd, "max_llm_cost_usd")


@dataclass(frozen=True)
class CampaignSpec:
    schema_version: int
    campaign_id: str
    research_question: str
    baseline_commit: str
    rlinf_commit: str
    edit_mode: EditMode
    editable_paths: tuple[str, ...]
    allowed_parameters: Mapping[str, ParameterRule]
    seeds: tuple[int, ...]
    reset_set_hash: str
    evaluator_version: str
    training_budget_steps: int
    evaluation_trajectories: int
    max_concurrency: int
    artifact_namespace: str
    created_at: str
    budget: BudgetEnvelope

    @classmethod
    def from_dict(cls, value: Any) -> "CampaignSpec":
        fields = {
            "schema_version",
            "campaign_id",
            "research_question",
            "baseline_commit",
            "rlinf_commit",
            "edit_mode",
            "editable_paths",
            "allowed_parameters",
            "seeds",
            "reset_set_hash",
            "evaluator_version",
            "training_budget_steps",
            "evaluation_trajectories",
            "max_concurrency",
            "artifact_namespace",
            "created_at",
            "budget",
        }
        data = require_exact_keys(value, "campaign", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"campaign.schema_version must be {SCHEMA_VERSION}")
        paths = data["editable_paths"]
        if not isinstance(paths, list) or not paths:
            raise ContractError("campaign.editable_paths must be a non-empty list")
        normalized_paths = tuple(
            require_safe_relative_path(item, f"campaign.editable_paths[{index}]")
            for index, item in enumerate(paths)
        )
        if len(set(normalized_paths)) != len(normalized_paths):
            raise ContractError("campaign.editable_paths must be unique")
        raw_parameters = data["allowed_parameters"]
        if not isinstance(raw_parameters, dict):
            raise ContractError("campaign.allowed_parameters must be an object")
        parameters = {
            require_identifier(name, "campaign.allowed_parameters key"): ParameterRule.from_dict(
                rule, f"campaign.allowed_parameters.{name}"
            )
            for name, rule in raw_parameters.items()
        }
        seeds = data["seeds"]
        if (
            not isinstance(seeds, list)
            or not seeds
            or not all(
                isinstance(seed, int) and not isinstance(seed, bool) and seed >= 0
                for seed in seeds
            )
            or len(set(seeds)) != len(seeds)
        ):
            raise ContractError("campaign.seeds must be unique non-negative integers")
        edit_mode = _enum_value(EditMode, data["edit_mode"], "campaign.edit_mode")
        if edit_mode == EditMode.CONFIG_ONLY and not parameters:
            raise ContractError("config-only campaigns require allowed_parameters")
        created_at = data["created_at"]
        parse_timestamp(created_at, "campaign.created_at")
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(data["campaign_id"], "campaign.campaign_id"),
            research_question=require_nonempty_text(
                data["research_question"], "campaign.research_question"
            ),
            baseline_commit=require_git_commit(
                data["baseline_commit"], "campaign.baseline_commit"
            ),
            rlinf_commit=require_git_commit(data["rlinf_commit"], "campaign.rlinf_commit"),
            edit_mode=edit_mode,
            editable_paths=normalized_paths,
            allowed_parameters=MappingProxyType(parameters),
            seeds=tuple(seeds),
            reset_set_hash=require_sha256(
                data["reset_set_hash"], "campaign.reset_set_hash"
            ),
            evaluator_version=require_identifier(
                data["evaluator_version"], "campaign.evaluator_version"
            ),
            training_budget_steps=_positive_int(
                data["training_budget_steps"], "campaign.training_budget_steps"
            ),
            evaluation_trajectories=_positive_int(
                data["evaluation_trajectories"], "campaign.evaluation_trajectories"
            ),
            max_concurrency=_positive_int(
                data["max_concurrency"], "campaign.max_concurrency"
            ),
            artifact_namespace=require_identifier(
                data["artifact_namespace"], "campaign.artifact_namespace"
            ),
            created_at=created_at,
            budget=BudgetEnvelope.from_dict(data["budget"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "research_question": self.research_question,
            "baseline_commit": self.baseline_commit,
            "rlinf_commit": self.rlinf_commit,
            "edit_mode": self.edit_mode.value,
            "editable_paths": list(self.editable_paths),
            "allowed_parameters": {
                name: rule.to_dict() for name, rule in sorted(self.allowed_parameters.items())
            },
            "seeds": list(self.seeds),
            "reset_set_hash": self.reset_set_hash,
            "evaluator_version": self.evaluator_version,
            "training_budget_steps": self.training_budget_steps,
            "evaluation_trajectories": self.evaluation_trajectories,
            "max_concurrency": self.max_concurrency,
            "artifact_namespace": self.artifact_namespace,
            "created_at": self.created_at,
            "budget": self.budget.to_dict(),
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class ApprovalEnvelope:
    schema_version: int
    campaign_id: str
    campaign_spec_hash: str
    approved_by: str
    approved_at: str
    expires_at: str
    edit_mode: EditMode
    max_concurrency: int
    budget: BudgetEnvelope

    @classmethod
    def from_dict(cls, value: Any) -> "ApprovalEnvelope":
        fields = {
            "schema_version",
            "campaign_id",
            "campaign_spec_hash",
            "approved_by",
            "approved_at",
            "expires_at",
            "edit_mode",
            "max_concurrency",
            "budget",
        }
        data = require_exact_keys(value, "approval", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"approval.schema_version must be {SCHEMA_VERSION}")
        approved_at = parse_timestamp(data["approved_at"], "approval.approved_at")
        expires_at = parse_timestamp(data["expires_at"], "approval.expires_at")
        if expires_at <= approved_at:
            raise ContractError("approval.expires_at must be after approved_at")
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(data["campaign_id"], "approval.campaign_id"),
            campaign_spec_hash=require_sha256(
                data["campaign_spec_hash"], "approval.campaign_spec_hash"
            ),
            approved_by=require_nonempty_text(
                data["approved_by"], "approval.approved_by", max_length=256
            ),
            approved_at=data["approved_at"],
            expires_at=data["expires_at"],
            edit_mode=_enum_value(EditMode, data["edit_mode"], "approval.edit_mode"),
            max_concurrency=_positive_int(
                data["max_concurrency"], "approval.max_concurrency"
            ),
            budget=BudgetEnvelope.from_dict(data["budget"], "approval.budget"),
        )

    def validate_for(self, campaign: CampaignSpec, at: datetime) -> None:
        if self.campaign_id != campaign.campaign_id:
            raise ContractError("approval campaign ID does not match campaign")
        if self.campaign_spec_hash != campaign.fingerprint():
            raise ContractError("approval does not match the exact campaign specification")
        if self.edit_mode != campaign.edit_mode:
            raise ContractError("approval edit mode does not match campaign")
        if self.max_concurrency > campaign.max_concurrency:
            raise ContractError("approval concurrency exceeds campaign")
        if self.budget.max_trials > campaign.budget.max_trials:
            raise ContractError("approval trial cap exceeds campaign")
        if self.budget.max_wall_time_seconds > campaign.budget.max_wall_time_seconds:
            raise ContractError("approval wall-time cap exceeds campaign")
        if self.budget.gpu_cost() > campaign.budget.gpu_cost():
            raise ContractError("approval GPU cap exceeds campaign")
        if self.budget.llm_cost() > campaign.budget.llm_cost():
            raise ContractError("approval LLM cap exceeds campaign")
        if at.tzinfo is None:
            raise ContractError("approval validation time must be timezone-aware")
        approved_at = parse_timestamp(self.approved_at, "approval.approved_at")
        expires_at = parse_timestamp(self.expires_at, "approval.expires_at")
        if at < approved_at or at >= expires_at:
            raise ContractError("approval is not active at the requested time")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "campaign_spec_hash": self.campaign_spec_hash,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "edit_mode": self.edit_mode.value,
            "max_concurrency": self.max_concurrency,
            "budget": self.budget.to_dict(),
        }


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    uri: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_dict(cls, value: Any, field: str) -> "ArtifactRef":
        data = require_exact_keys(
            value, field, {"artifact_id", "kind", "uri", "sha256", "size_bytes"}
        )
        return cls(
            artifact_id=require_identifier(data["artifact_id"], f"{field}.artifact_id"),
            kind=require_identifier(data["kind"], f"{field}.kind"),
            uri=require_nonempty_text(data["uri"], f"{field}.uri", max_length=2048),
            sha256=require_sha256(data["sha256"], f"{field}.sha256"),
            size_bytes=_nonnegative_int(data["size_bytes"], f"{field}.size_bytes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "uri": self.uri,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def _finite_metrics(value: Any, field: str) -> Mapping[str, float]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    metrics: dict[str, float] = {}
    for name, raw in value.items():
        require_nonempty_text(name, f"{field} key", max_length=256)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ContractError(f"{field}.{name} must be numeric")
        numeric = float(raw)
        if not math.isfinite(numeric):
            raise ContractError(
                f"{field}.{name} must be finite; record non-finite values in metric_errors"
            )
        metrics[name] = numeric
    return MappingProxyType(metrics)


@dataclass(frozen=True)
class TrialEvidence:
    schema_version: int
    campaign_id: str
    trial_id: str
    arm_id: str
    parent_commit: str
    candidate_commit: str
    rlinf_commit: str
    config_hash: str
    command_hash: str
    seed: int
    reset_set_hash: str
    evaluator_version: str
    started_at: str
    finished_at: str
    status: TrialStatus
    exit_code: int | None
    elapsed_seconds: float
    gpu_cost_usd: str
    llm_cost_usd: str
    metrics: Mapping[str, float]
    metric_errors: tuple[str, ...]
    artifacts: tuple[ArtifactRef, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "TrialEvidence":
        fields = {
            "schema_version",
            "campaign_id",
            "trial_id",
            "arm_id",
            "parent_commit",
            "candidate_commit",
            "rlinf_commit",
            "config_hash",
            "command_hash",
            "seed",
            "reset_set_hash",
            "evaluator_version",
            "started_at",
            "finished_at",
            "status",
            "exit_code",
            "elapsed_seconds",
            "gpu_cost_usd",
            "llm_cost_usd",
            "metrics",
            "metric_errors",
            "artifacts",
        }
        data = require_exact_keys(value, "trial_evidence", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"trial_evidence.schema_version must be {SCHEMA_VERSION}")
        started = parse_timestamp(data["started_at"], "trial_evidence.started_at")
        finished = parse_timestamp(data["finished_at"], "trial_evidence.finished_at")
        if finished < started:
            raise ContractError("trial_evidence.finished_at precedes started_at")
        exit_code = data["exit_code"]
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            raise ContractError("trial_evidence.exit_code must be an integer or null")
        status = _enum_value(TrialStatus, data["status"], "trial_evidence.status")
        if status == TrialStatus.COMPLETE and exit_code != 0:
            raise ContractError("complete trial evidence requires exit_code 0")
        if status == TrialStatus.FAILED and (exit_code is None or exit_code == 0):
            raise ContractError("failed trial evidence requires a non-zero exit_code")
        elapsed = data["elapsed_seconds"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or float(elapsed) < 0
        ):
            raise ContractError("trial_evidence.elapsed_seconds must be finite and non-negative")
        errors = data["metric_errors"]
        if not isinstance(errors, list) or not all(
            isinstance(item, str) and item for item in errors
        ):
            raise ContractError("trial_evidence.metric_errors must contain non-empty strings")
        raw_artifacts = data["artifacts"]
        if not isinstance(raw_artifacts, list):
            raise ContractError("trial_evidence.artifacts must be a list")
        artifacts = tuple(
            ArtifactRef.from_dict(item, f"trial_evidence.artifacts[{index}]")
            for index, item in enumerate(raw_artifacts)
        )
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(data["campaign_id"], "trial_evidence.campaign_id"),
            trial_id=require_identifier(data["trial_id"], "trial_evidence.trial_id"),
            arm_id=require_identifier(data["arm_id"], "trial_evidence.arm_id"),
            parent_commit=require_git_commit(
                data["parent_commit"], "trial_evidence.parent_commit"
            ),
            candidate_commit=require_git_commit(
                data["candidate_commit"], "trial_evidence.candidate_commit"
            ),
            rlinf_commit=require_git_commit(data["rlinf_commit"], "trial_evidence.rlinf_commit"),
            config_hash=require_sha256(data["config_hash"], "trial_evidence.config_hash"),
            command_hash=require_sha256(data["command_hash"], "trial_evidence.command_hash"),
            seed=_nonnegative_int(data["seed"], "trial_evidence.seed"),
            reset_set_hash=require_sha256(
                data["reset_set_hash"], "trial_evidence.reset_set_hash"
            ),
            evaluator_version=require_identifier(
                data["evaluator_version"], "trial_evidence.evaluator_version"
            ),
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            status=status,
            exit_code=exit_code,
            elapsed_seconds=float(elapsed),
            gpu_cost_usd=decimal_text(
                parse_decimal(data["gpu_cost_usd"], "trial_evidence.gpu_cost_usd")
            ),
            llm_cost_usd=decimal_text(
                parse_decimal(data["llm_cost_usd"], "trial_evidence.llm_cost_usd")
            ),
            metrics=_finite_metrics(data["metrics"], "trial_evidence.metrics"),
            metric_errors=tuple(errors),
            artifacts=artifacts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "trial_id": self.trial_id,
            "arm_id": self.arm_id,
            "parent_commit": self.parent_commit,
            "candidate_commit": self.candidate_commit,
            "rlinf_commit": self.rlinf_commit,
            "config_hash": self.config_hash,
            "command_hash": self.command_hash,
            "seed": self.seed,
            "reset_set_hash": self.reset_set_hash,
            "evaluator_version": self.evaluator_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed_seconds,
            "gpu_cost_usd": self.gpu_cost_usd,
            "llm_cost_usd": self.llm_cost_usd,
            "metrics": dict(sorted(self.metrics.items())),
            "metric_errors": list(self.metric_errors),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class DecisionRecord:
    schema_version: int
    campaign_id: str
    decision_id: str
    trial_ids: tuple[str, ...]
    evaluator_version: str
    decision: Decision
    reason: str
    decided_at: str
    evidence_hashes: tuple[str, ...]
    incumbent_before: str
    incumbent_after: str

    @classmethod
    def from_dict(cls, value: Any) -> "DecisionRecord":
        fields = {
            "schema_version",
            "campaign_id",
            "decision_id",
            "trial_ids",
            "evaluator_version",
            "decision",
            "reason",
            "decided_at",
            "evidence_hashes",
            "incumbent_before",
            "incumbent_after",
        }
        data = require_exact_keys(value, "decision", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"decision.schema_version must be {SCHEMA_VERSION}")
        trial_ids = data["trial_ids"]
        if not isinstance(trial_ids, list) or not trial_ids:
            raise ContractError("decision.trial_ids must be a non-empty list")
        normalized_trials = tuple(
            require_identifier(item, f"decision.trial_ids[{index}]")
            for index, item in enumerate(trial_ids)
        )
        if len(set(normalized_trials)) != len(normalized_trials):
            raise ContractError("decision.trial_ids must be unique")
        hashes = data["evidence_hashes"]
        if not isinstance(hashes, list) or len(hashes) != len(normalized_trials):
            raise ContractError("decision requires one evidence hash per trial")
        parse_timestamp(data["decided_at"], "decision.decided_at")
        decision = _enum_value(Decision, data["decision"], "decision.decision")
        before = require_git_commit(data["incumbent_before"], "decision.incumbent_before")
        after = require_git_commit(data["incumbent_after"], "decision.incumbent_after")
        if decision != Decision.KEEP and after != before:
            raise ContractError("non-keep decisions may not change the incumbent")
        if decision == Decision.KEEP and after == before:
            raise ContractError("keep decisions must promote a new incumbent")
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(data["campaign_id"], "decision.campaign_id"),
            decision_id=require_identifier(data["decision_id"], "decision.decision_id"),
            trial_ids=normalized_trials,
            evaluator_version=require_identifier(
                data["evaluator_version"], "decision.evaluator_version"
            ),
            decision=decision,
            reason=require_nonempty_text(data["reason"], "decision.reason"),
            decided_at=data["decided_at"],
            evidence_hashes=tuple(
                require_sha256(item, f"decision.evidence_hashes[{index}]")
                for index, item in enumerate(hashes)
            ),
            incumbent_before=before,
            incumbent_after=after,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "decision_id": self.decision_id,
            "trial_ids": list(self.trial_ids),
            "evaluator_version": self.evaluator_version,
            "decision": self.decision.value,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "evidence_hashes": list(self.evidence_hashes),
            "incumbent_before": self.incumbent_before,
            "incumbent_after": self.incumbent_after,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())
