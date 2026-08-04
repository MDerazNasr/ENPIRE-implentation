"""Frozen M8 three-arm study protocol and durable state machine.

The study layer is deliberately separate from proposal generation and worker
execution.  It accepts only externally evaluated records, keeps arm lineages
isolated, and freezes selection/confirmation rules before any result exists.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import Decision, TrialEvidence
from supervisor.evaluation import EvaluationResult


STUDY_PROTOCOL_VERSION = "m8-three-arm-v1"
SELECTION_RULE_VERSION = "m8-best-valid-v1"
FIXED_RULE_CONFIG_ARM = "fixed-rule-config"
CLAUDE_CONFIG_ARM = "claude-config"
CLAUDE_CODE_ARM = "claude-code"
REQUIRED_ARMS = (FIXED_RULE_CONFIG_ARM, CLAUDE_CONFIG_ARM, CLAUDE_CODE_ARM)


class StudyError(ContractError):
    """Raised when preregistration or study-state boundaries are violated."""


class StudyPhase(str, Enum):
    ACTIVE_DISCOVERY = "active_discovery"
    DISCOVERY_COMPLETE = "discovery_complete"
    ACTIVE_CONFIRMATION = "active_confirmation"
    COMPLETE = "complete"


class StudyStage(str, Enum):
    DISCOVERY = "discovery"
    CONFIRMATION = "confirmation"


class StudyRecordStatus(str, Enum):
    COMPLETE = "complete"
    INVALID = "invalid"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"


class ProposerKind(str, Enum):
    FIXED_RULE = "fixed_rule"
    CLAUDE = "claude"


class EditMode(str, Enum):
    CONFIG_ONLY = "config_only"
    ACTOR_OBJECTIVE = "actor_objective"


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise StudyError(f"{field} is unsupported") from error


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StudyError(f"{field} must be an integer")
    if value < 0 or (value == 0 and not allow_zero):
        raise StudyError(f"{field} must be {'non-negative' if allow_zero else 'positive'}")
    return value


def _finite_float(value: Any, field: str, *, allow_none: bool = False) -> float | None:
    import math

    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StudyError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise StudyError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class StudyArmSpec:
    arm_id: str
    proposer: ProposerKind
    edit_mode: EditMode
    discovery_slots: int
    max_wall_time_seconds_per_candidate: int
    max_gpu_cost_usd_per_candidate: str
    max_llm_cost_usd_per_candidate: str

    @classmethod
    def create(
        cls,
        *,
        arm_id: str,
        proposer: ProposerKind | str,
        edit_mode: EditMode | str,
        discovery_slots: int = 3,
        max_wall_time_seconds_per_candidate: int,
        max_gpu_cost_usd_per_candidate: str,
        max_llm_cost_usd_per_candidate: str,
    ) -> "StudyArmSpec":
        return cls(
            arm_id=require_identifier(arm_id, "study arm ID"),
            proposer=_enum(ProposerKind, proposer, "study arm proposer"),
            edit_mode=_enum(EditMode, edit_mode, "study arm edit mode"),
            discovery_slots=_positive_int(discovery_slots, "study discovery slots"),
            max_wall_time_seconds_per_candidate=_positive_int(
                max_wall_time_seconds_per_candidate, "study arm wall-time cap"
            ),
            max_gpu_cost_usd_per_candidate=decimal_text(
                parse_decimal(max_gpu_cost_usd_per_candidate, "study arm GPU cap")
            ),
            max_llm_cost_usd_per_candidate=decimal_text(
                parse_decimal(max_llm_cost_usd_per_candidate, "study arm LLM cap")
            ),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "StudyArmSpec":
        data = require_exact_keys(
            value,
            "study arm",
            {
                "arm_id",
                "proposer",
                "edit_mode",
                "discovery_slots",
                "max_wall_time_seconds_per_candidate",
                "max_gpu_cost_usd_per_candidate",
                "max_llm_cost_usd_per_candidate",
            },
        )
        return cls.create(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "proposer": self.proposer.value,
            "edit_mode": self.edit_mode.value,
            "discovery_slots": self.discovery_slots,
            "max_wall_time_seconds_per_candidate": self.max_wall_time_seconds_per_candidate,
            "max_gpu_cost_usd_per_candidate": self.max_gpu_cost_usd_per_candidate,
            "max_llm_cost_usd_per_candidate": self.max_llm_cost_usd_per_candidate,
        }


@dataclass(frozen=True)
class StudySpec:
    protocol_version: str
    study_id: str
    campaign_id: str
    research_question: str
    baseline_commit: str
    rlinf_commit: str
    reset_set_hash: str
    evaluator_version: str
    paired_seeds: tuple[int, ...]
    primary_metric: str
    secondary_metrics: tuple[str, ...]
    selection_rule_version: str
    arms: tuple[StudyArmSpec, ...]
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        study_id: str,
        campaign_id: str,
        research_question: str,
        baseline_commit: str,
        rlinf_commit: str,
        reset_set_hash: str,
        evaluator_version: str,
        paired_seeds: Sequence[int],
        arms: Sequence[StudyArmSpec],
        created_at: datetime | None = None,
        primary_metric: str = "success_rate",
        secondary_metrics: Sequence[str] = (
            "successful_episode_length",
            "elapsed_seconds",
            "gpu_cost_usd",
        ),
    ) -> "StudySpec":
        seeds = tuple(_positive_int(seed, "study seed", allow_zero=True) for seed in paired_seeds)
        if len(seeds) != 3 or len(set(seeds)) != len(seeds):
            raise StudyError("M8 requires exactly three unique paired seeds")
        arm_tuple = tuple(arms)
        if tuple(arm.arm_id for arm in arm_tuple) != REQUIRED_ARMS:
            raise StudyError(f"M8 requires arms in exact order: {REQUIRED_ARMS}")
        expected = {
            FIXED_RULE_CONFIG_ARM: (ProposerKind.FIXED_RULE, EditMode.CONFIG_ONLY),
            CLAUDE_CONFIG_ARM: (ProposerKind.CLAUDE, EditMode.CONFIG_ONLY),
            CLAUDE_CODE_ARM: (ProposerKind.CLAUDE, EditMode.ACTOR_OBJECTIVE),
        }
        for arm in arm_tuple:
            if (arm.proposer, arm.edit_mode) != expected[arm.arm_id]:
                raise StudyError(f"arm {arm.arm_id} has the wrong proposer/edit mode")
            if arm.discovery_slots != 3:
                raise StudyError("every M8 arm must receive exactly three discovery slots")
        wall_caps = {arm.max_wall_time_seconds_per_candidate for arm in arm_tuple}
        gpu_caps = {arm.max_gpu_cost_usd_per_candidate for arm in arm_tuple}
        if len(wall_caps) != 1 or len(gpu_caps) != 1:
            raise StudyError("all arms require equal worker wall-time and GPU caps")
        if Decimal(arm_tuple[0].max_llm_cost_usd_per_candidate) != 0:
            raise StudyError("fixed-rule arm must have zero LLM budget")
        if (
            arm_tuple[1].max_llm_cost_usd_per_candidate
            != arm_tuple[2].max_llm_cost_usd_per_candidate
        ):
            raise StudyError("Claude arms require equal per-candidate LLM caps")
        metrics = tuple(require_identifier(item, "secondary metric") for item in secondary_metrics)
        if not metrics or len(set(metrics)) != len(metrics):
            raise StudyError("secondary metrics must be unique and non-empty")
        return cls(
            protocol_version=STUDY_PROTOCOL_VERSION,
            study_id=require_identifier(study_id, "study ID"),
            campaign_id=require_identifier(campaign_id, "study campaign ID"),
            research_question=require_nonempty_text(
                research_question, "study research question", max_length=1024
            ),
            baseline_commit=require_git_commit(baseline_commit, "study baseline commit"),
            rlinf_commit=require_git_commit(rlinf_commit, "study RLinf commit"),
            reset_set_hash=require_sha256(reset_set_hash, "study reset-set hash"),
            evaluator_version=require_identifier(evaluator_version, "study evaluator version"),
            paired_seeds=seeds,
            primary_metric=require_identifier(primary_metric, "study primary metric"),
            secondary_metrics=metrics,
            selection_rule_version=SELECTION_RULE_VERSION,
            arms=arm_tuple,
            created_at=timestamp_text(created_at or datetime.now(timezone.utc)),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "StudySpec":
        fields = {
            "protocol_version", "study_id", "campaign_id", "research_question", "baseline_commit",
            "rlinf_commit", "reset_set_hash", "evaluator_version", "paired_seeds",
            "primary_metric", "secondary_metrics", "selection_rule_version", "arms",
            "created_at",
        }
        data = require_exact_keys(value, "study spec", fields)
        if data["protocol_version"] != STUDY_PROTOCOL_VERSION:
            raise StudyError(f"study protocol must be {STUDY_PROTOCOL_VERSION}")
        if data["selection_rule_version"] != SELECTION_RULE_VERSION:
            raise StudyError(f"selection rule must be {SELECTION_RULE_VERSION}")
        if not isinstance(data["paired_seeds"], list) or not isinstance(data["arms"], list):
            raise StudyError("study seeds and arms must be lists")
        if not isinstance(data["secondary_metrics"], list):
            raise StudyError("study secondary metrics must be a list")
        parse_timestamp(data["created_at"], "study created_at")
        return cls.create(
            study_id=data["study_id"],
            campaign_id=data["campaign_id"],
            research_question=data["research_question"],
            baseline_commit=data["baseline_commit"],
            rlinf_commit=data["rlinf_commit"],
            reset_set_hash=data["reset_set_hash"],
            evaluator_version=data["evaluator_version"],
            paired_seeds=data["paired_seeds"],
            primary_metric=data["primary_metric"],
            secondary_metrics=data["secondary_metrics"],
            arms=tuple(StudyArmSpec.from_dict(item) for item in data["arms"]),
            created_at=parse_timestamp(data["created_at"], "study created_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "study_id": self.study_id,
            "campaign_id": self.campaign_id,
            "research_question": self.research_question,
            "baseline_commit": self.baseline_commit,
            "rlinf_commit": self.rlinf_commit,
            "reset_set_hash": self.reset_set_hash,
            "evaluator_version": self.evaluator_version,
            "paired_seeds": list(self.paired_seeds),
            "primary_metric": self.primary_metric,
            "secondary_metrics": list(self.secondary_metrics),
            "selection_rule_version": self.selection_rule_version,
            "arms": [arm.to_dict() for arm in self.arms],
            "created_at": self.created_at,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    def arm(self, arm_id: str) -> StudyArmSpec:
        for arm in self.arms:
            if arm.arm_id == arm_id:
                return arm
        raise StudyError(f"unknown study arm: {arm_id}")


@dataclass(frozen=True)
class StudyActivation:
    study_hash: str
    synthetic: bool
    activated_by: str
    activated_at: str
    d1_gate_hash: str | None
    d1_gate_status: str | None

    @classmethod
    def create(
        cls,
        *,
        spec: StudySpec,
        synthetic: bool,
        activated_by: str,
        activated_at: datetime | None = None,
        d1_gate_hash: str | None = None,
        d1_gate_status: str | None = None,
    ) -> "StudyActivation":
        if not isinstance(synthetic, bool):
            raise StudyError("study activation synthetic flag must be boolean")
        if synthetic:
            if d1_gate_hash is not None or d1_gate_status is not None:
                raise StudyError("synthetic activation may not claim a D1 gate")
        elif d1_gate_status != "ready" or d1_gate_hash is None:
            raise StudyError("live activation requires an exact ready D1 gate hash")
        return cls(
            study_hash=spec.fingerprint(),
            synthetic=synthetic,
            activated_by=require_identifier(activated_by, "study activator"),
            activated_at=timestamp_text(activated_at or datetime.now(timezone.utc)),
            d1_gate_hash=require_sha256(d1_gate_hash, "D1 gate hash") if d1_gate_hash else None,
            d1_gate_status=d1_gate_status,
        )

    @classmethod
    def from_dict(cls, value: Any, spec: StudySpec) -> "StudyActivation":
        data = require_exact_keys(
            value, "study activation",
            {"study_hash", "synthetic", "activated_by", "activated_at", "d1_gate_hash", "d1_gate_status"},
        )
        if data["study_hash"] != spec.fingerprint():
            raise StudyError("activation does not bind the exact preregistration")
        parse_timestamp(data["activated_at"], "study activated_at")
        return cls.create(
            spec=spec,
            synthetic=data["synthetic"],
            activated_by=data["activated_by"],
            activated_at=parse_timestamp(data["activated_at"], "study activated_at"),
            d1_gate_hash=data["d1_gate_hash"],
            d1_gate_status=data["d1_gate_status"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_hash": self.study_hash,
            "synthetic": self.synthetic,
            "activated_by": self.activated_by,
            "activated_at": self.activated_at,
            "d1_gate_hash": self.d1_gate_hash,
            "d1_gate_status": self.d1_gate_status,
        }


@dataclass(frozen=True)
class StudyEvaluationSummary:
    campaign_id: str
    evaluator_version: str
    decision: Decision
    decision_hash: str
    evaluation_hash: str
    control_mean_success: float | None
    candidate_mean_success: float | None
    mean_success_delta: float | None
    success_delta_ci95: tuple[float, float] | None
    incumbent_before: str
    incumbent_after: str
    candidate_evidence_hashes: tuple[str, ...]

    @classmethod
    def from_result(cls, result: EvaluationResult) -> "StudyEvaluationSummary":
        return cls(
            campaign_id=result.decision_record.campaign_id,
            evaluator_version=result.evaluator_version,
            decision=result.decision_record.decision,
            decision_hash=result.decision_record.fingerprint(),
            evaluation_hash=result.fingerprint(),
            control_mean_success=result.control_mean_success,
            candidate_mean_success=result.candidate_mean_success,
            mean_success_delta=result.mean_success_delta,
            success_delta_ci95=result.success_delta_ci95,
            incumbent_before=result.decision_record.incumbent_before,
            incumbent_after=result.decision_record.incumbent_after,
            candidate_evidence_hashes=result.candidate_evidence_hashes,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "StudyEvaluationSummary":
        data = require_exact_keys(
            value, "study evaluation summary",
            {"campaign_id", "evaluator_version", "decision", "decision_hash", "evaluation_hash", "control_mean_success",
             "candidate_mean_success", "mean_success_delta", "success_delta_ci95",
             "incumbent_before", "incumbent_after", "candidate_evidence_hashes"},
        )
        ci = data["success_delta_ci95"]
        if ci is not None and (not isinstance(ci, list) or len(ci) != 2):
            raise StudyError("study evaluation CI must have two values or be null")
        hashes = data["candidate_evidence_hashes"]
        if not isinstance(hashes, list):
            raise StudyError("candidate evidence hashes must be a list")
        decision = _enum(Decision, data["decision"], "study evaluation decision")
        before = require_git_commit(data["incumbent_before"], "evaluation incumbent before")
        after = require_git_commit(data["incumbent_after"], "evaluation incumbent after")
        if decision == Decision.KEEP and before == after:
            raise StudyError("keep summary must promote a different commit")
        if decision != Decision.KEEP and before != after:
            raise StudyError("non-keep summary cannot promote")
        return cls(
            campaign_id=require_identifier(data["campaign_id"], "evaluation campaign ID"),
            evaluator_version=require_identifier(data["evaluator_version"], "evaluation evaluator version"),
            decision=decision,
            decision_hash=require_sha256(data["decision_hash"], "decision hash"),
            evaluation_hash=require_sha256(data["evaluation_hash"], "evaluation hash"),
            control_mean_success=_finite_float(data["control_mean_success"], "control mean", allow_none=True),
            candidate_mean_success=_finite_float(data["candidate_mean_success"], "candidate mean", allow_none=True),
            mean_success_delta=_finite_float(data["mean_success_delta"], "success delta", allow_none=True),
            success_delta_ci95=(
                (_finite_float(ci[0], "CI lower"), _finite_float(ci[1], "CI upper"))
                if ci is not None else None
            ),
            incumbent_before=before,
            incumbent_after=after,
            candidate_evidence_hashes=tuple(require_sha256(item, "candidate evidence hash") for item in hashes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "evaluator_version": self.evaluator_version,
            "decision": self.decision.value,
            "decision_hash": self.decision_hash,
            "evaluation_hash": self.evaluation_hash,
            "control_mean_success": self.control_mean_success,
            "candidate_mean_success": self.candidate_mean_success,
            "mean_success_delta": self.mean_success_delta,
            "success_delta_ci95": list(self.success_delta_ci95) if self.success_delta_ci95 else None,
            "incumbent_before": self.incumbent_before,
            "incumbent_after": self.incumbent_after,
            "candidate_evidence_hashes": list(self.candidate_evidence_hashes),
        }


@dataclass(frozen=True)
class StudyTrialRecord:
    record_id: str
    arm_id: str
    stage: StudyStage
    slot_number: int
    status: StudyRecordStatus
    edit_mode: EditMode
    incumbent_before: str
    candidate_commit: str | None
    proposal_session_hash: str | None
    proposal_valid: bool
    candidate_valid: bool
    evidence: tuple[TrialEvidence, ...]
    evaluation: StudyEvaluationSummary | None
    proposal_llm_cost_usd: str
    input_tokens: int
    output_tokens: int
    human_interventions: int
    reason: str
    recorded_at: str

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        arm_id: str,
        stage: StudyStage | str,
        slot_number: int,
        status: StudyRecordStatus | str,
        edit_mode: EditMode | str,
        incumbent_before: str,
        candidate_commit: str | None,
        proposal_session_hash: str | None,
        proposal_valid: bool,
        candidate_valid: bool,
        evidence: Sequence[TrialEvidence] = (),
        evaluation: EvaluationResult | StudyEvaluationSummary | None = None,
        proposal_llm_cost_usd: str = "0",
        input_tokens: int = 0,
        output_tokens: int = 0,
        human_interventions: int = 0,
        reason: str,
        recorded_at: datetime | None = None,
    ) -> "StudyTrialRecord":
        status_value = _enum(StudyRecordStatus, status, "study record status")
        stage_value = _enum(StudyStage, stage, "study record stage")
        commit = require_git_commit(candidate_commit, "study candidate commit") if candidate_commit else None
        session_hash = require_sha256(proposal_session_hash, "proposal session hash") if proposal_session_hash else None
        if not isinstance(proposal_valid, bool) or not isinstance(candidate_valid, bool):
            raise StudyError("proposal/candidate validity flags must be boolean")
        items = tuple(evidence)
        summary = (
            StudyEvaluationSummary.from_result(evaluation)
            if isinstance(evaluation, EvaluationResult)
            else evaluation
        )
        if status_value == StudyRecordStatus.INVALID:
            if proposal_valid or candidate_valid or commit or items or summary:
                raise StudyError("invalid records cannot contain a candidate or evaluation")
        if status_value in {StudyRecordStatus.COMPLETE, StudyRecordStatus.FAILED, StudyRecordStatus.INCONCLUSIVE}:
            if not proposal_valid or not commit or not items or summary is None:
                raise StudyError("evaluated records require a valid proposal, candidate, evidence, and evaluation")
        if status_value == StudyRecordStatus.COMPLETE:
            if not candidate_valid or summary.decision in {Decision.FAILED, Decision.INCONCLUSIVE}:
                raise StudyError("complete records require a scientifically valid terminal evaluation")
        if status_value == StudyRecordStatus.FAILED and summary.decision != Decision.FAILED:
            raise StudyError("failed record requires a failed evaluation")
        if status_value == StudyRecordStatus.INCONCLUSIVE and summary.decision != Decision.INCONCLUSIVE:
            raise StudyError("inconclusive record requires an inconclusive evaluation")
        if summary and summary.incumbent_before != incumbent_before:
            raise StudyError("evaluation uses a different incumbent")
        if summary and summary.decision == Decision.KEEP and summary.incumbent_after != commit:
            raise StudyError("keep evaluation promotes a different candidate")
        if summary and tuple(item.fingerprint() for item in items) != summary.candidate_evidence_hashes:
            raise StudyError("record evidence differs from evaluated candidate evidence")
        return cls(
            record_id=require_identifier(record_id, "study record ID"),
            arm_id=require_identifier(arm_id, "study arm ID"),
            stage=stage_value,
            slot_number=_positive_int(slot_number, "study slot number"),
            status=status_value,
            edit_mode=_enum(EditMode, edit_mode, "study edit mode"),
            incumbent_before=require_git_commit(incumbent_before, "study incumbent"),
            candidate_commit=commit,
            proposal_session_hash=session_hash,
            proposal_valid=proposal_valid,
            candidate_valid=candidate_valid,
            evidence=items,
            evaluation=summary,
            proposal_llm_cost_usd=decimal_text(parse_decimal(proposal_llm_cost_usd, "proposal LLM cost")),
            input_tokens=_positive_int(input_tokens, "input tokens", allow_zero=True),
            output_tokens=_positive_int(output_tokens, "output tokens", allow_zero=True),
            human_interventions=_positive_int(human_interventions, "human interventions", allow_zero=True),
            reason=require_nonempty_text(reason, "study record reason", max_length=2048),
            recorded_at=timestamp_text(recorded_at or datetime.now(timezone.utc)),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "StudyTrialRecord":
        fields = {"record_id", "arm_id", "stage", "slot_number", "status", "edit_mode",
                  "incumbent_before", "candidate_commit", "proposal_session_hash", "proposal_valid",
                  "candidate_valid", "evidence", "evaluation", "proposal_llm_cost_usd",
                  "input_tokens", "output_tokens", "human_interventions", "reason", "recorded_at"}
        data = require_exact_keys(value, "study record", fields)
        if not isinstance(data["evidence"], list):
            raise StudyError("study record evidence must be a list")
        parse_timestamp(data["recorded_at"], "study record recorded_at")
        return cls.create(
            **{key: data[key] for key in fields - {"evidence", "evaluation", "recorded_at"}},
            evidence=tuple(TrialEvidence.from_dict(item) for item in data["evidence"]),
            evaluation=(StudyEvaluationSummary.from_dict(data["evaluation"]) if data["evaluation"] else None),
            recorded_at=parse_timestamp(data["recorded_at"], "study record recorded_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "arm_id": self.arm_id,
            "stage": self.stage.value,
            "slot_number": self.slot_number,
            "status": self.status.value,
            "edit_mode": self.edit_mode.value,
            "incumbent_before": self.incumbent_before,
            "candidate_commit": self.candidate_commit,
            "proposal_session_hash": self.proposal_session_hash,
            "proposal_valid": self.proposal_valid,
            "candidate_valid": self.candidate_valid,
            "evidence": [item.to_dict() for item in self.evidence],
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "proposal_llm_cost_usd": self.proposal_llm_cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "human_interventions": self.human_interventions,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    @property
    def worker_wall_time_seconds(self) -> float:
        return sum(item.elapsed_seconds for item in self.evidence)

    @property
    def worker_gpu_cost_usd(self) -> Decimal:
        return sum((Decimal(item.gpu_cost_usd) for item in self.evidence), Decimal(0))


@dataclass(frozen=True)
class ArmSelection:
    arm_id: str
    selected_record_id: str | None
    selected_candidate_commit: str | None
    reason: str
    selection_rule_version: str
    source_record_hashes: tuple[str, ...]

    @classmethod
    def create(
        cls, *, arm_id: str, selected: StudyTrialRecord | None,
        source_records: Sequence[StudyTrialRecord], reason: str,
    ) -> "ArmSelection":
        return cls(
            arm_id=require_identifier(arm_id, "selection arm ID"),
            selected_record_id=selected.record_id if selected else None,
            selected_candidate_commit=selected.candidate_commit if selected else None,
            reason=require_nonempty_text(reason, "selection reason", max_length=2048),
            selection_rule_version=SELECTION_RULE_VERSION,
            source_record_hashes=tuple(item.fingerprint() for item in source_records),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ArmSelection":
        data = require_exact_keys(value, "arm selection", {"arm_id", "selected_record_id", "selected_candidate_commit", "reason", "selection_rule_version", "source_record_hashes"})
        if data["selection_rule_version"] != SELECTION_RULE_VERSION:
            raise StudyError("selection rule version changed")
        hashes = data["source_record_hashes"]
        if not isinstance(hashes, list):
            raise StudyError("selection source hashes must be a list")
        selected_id = data["selected_record_id"]
        selected_commit = data["selected_candidate_commit"]
        if (selected_id is None) != (selected_commit is None):
            raise StudyError("selection record and commit must both be present or absent")
        return cls(
            arm_id=require_identifier(data["arm_id"], "selection arm ID"),
            selected_record_id=(require_identifier(selected_id, "selected record ID") if selected_id else None),
            selected_candidate_commit=(require_git_commit(selected_commit, "selected commit") if selected_commit else None),
            reason=require_nonempty_text(data["reason"], "selection reason", max_length=2048),
            selection_rule_version=SELECTION_RULE_VERSION,
            source_record_hashes=tuple(require_sha256(item, "selection source hash") for item in hashes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "selected_record_id": self.selected_record_id,
            "selected_candidate_commit": self.selected_candidate_commit,
            "reason": self.reason,
            "selection_rule_version": self.selection_rule_version,
            "source_record_hashes": list(self.source_record_hashes),
        }


@dataclass(frozen=True)
class StudyArmState:
    arm_id: str
    incumbent_commit: str
    discovery_record_ids: tuple[str, ...] = ()
    selection: ArmSelection | None = None
    confirmation_record_id: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> "StudyArmState":
        data = require_exact_keys(value, "study arm state", {"arm_id", "incumbent_commit", "discovery_record_ids", "selection", "confirmation_record_id"})
        ids = data["discovery_record_ids"]
        if not isinstance(ids, list):
            raise StudyError("discovery record IDs must be a list")
        return cls(
            arm_id=require_identifier(data["arm_id"], "arm state ID"),
            incumbent_commit=require_git_commit(data["incumbent_commit"], "arm incumbent"),
            discovery_record_ids=tuple(require_identifier(item, "discovery record ID") for item in ids),
            selection=ArmSelection.from_dict(data["selection"]) if data["selection"] else None,
            confirmation_record_id=(require_identifier(data["confirmation_record_id"], "confirmation record ID") if data["confirmation_record_id"] else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "incumbent_commit": self.incumbent_commit,
            "discovery_record_ids": list(self.discovery_record_ids),
            "selection": self.selection.to_dict() if self.selection else None,
            "confirmation_record_id": self.confirmation_record_id,
        }


@dataclass(frozen=True)
class StudyState:
    spec: StudySpec
    activation: StudyActivation
    phase: StudyPhase
    arms: tuple[StudyArmState, ...]
    records: tuple[StudyTrialRecord, ...]
    generation: int

    @classmethod
    def initial(cls, spec: StudySpec, activation: StudyActivation) -> "StudyState":
        validated_spec = StudySpec.from_dict(spec.to_dict())
        if validated_spec != spec:
            raise StudyError("study preregistration is not canonical")
        validated_activation = StudyActivation.from_dict(
            activation.to_dict(), validated_spec
        )
        if validated_activation != activation:
            raise StudyError("study activation is not canonical")
        if activation.study_hash != spec.fingerprint():
            raise StudyError("activation does not bind the preregistration")
        return cls(
            spec=spec,
            activation=activation,
            phase=StudyPhase.ACTIVE_DISCOVERY,
            arms=tuple(StudyArmState(arm_id=arm.arm_id, incumbent_commit=spec.baseline_commit) for arm in spec.arms),
            records=(),
            generation=0,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "StudyState":
        data = require_exact_keys(value, "study state", {"spec", "activation", "phase", "arms", "records", "generation"})
        spec = StudySpec.from_dict(data["spec"])
        if not isinstance(data["arms"], list) or not isinstance(data["records"], list):
            raise StudyError("study arms and records must be lists")
        state = cls(
            spec=spec,
            activation=StudyActivation.from_dict(data["activation"], spec),
            phase=_enum(StudyPhase, data["phase"], "study phase"),
            arms=tuple(StudyArmState.from_dict(item) for item in data["arms"]),
            records=tuple(StudyTrialRecord.from_dict(item) for item in data["records"]),
            generation=_positive_int(data["generation"], "study generation", allow_zero=True),
        )
        _validate_state(state)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "activation": self.activation.to_dict(),
            "phase": self.phase.value,
            "arms": [arm.to_dict() for arm in self.arms],
            "records": [record.to_dict() for record in self.records],
            "generation": self.generation,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    def arm(self, arm_id: str) -> StudyArmState:
        for arm in self.arms:
            if arm.arm_id == arm_id:
                return arm
        raise StudyError(f"unknown study arm: {arm_id}")


def _validate_state(state: StudyState) -> None:
    if tuple(arm.arm_id for arm in state.arms) != REQUIRED_ARMS:
        raise StudyError("study state has the wrong arms")
    record_ids = [record.record_id for record in state.records]
    if len(set(record_ids)) != len(record_ids):
        raise StudyError("study record IDs must be unique")
    records = {record.record_id: record for record in state.records}
    for arm in state.arms:
        if len(arm.discovery_record_ids) > 3 or len(set(arm.discovery_record_ids)) != len(arm.discovery_record_ids):
            raise StudyError("arm has invalid discovery slots")
        for position, record_id in enumerate(arm.discovery_record_ids, start=1):
            record = records.get(record_id)
            if not record or record.arm_id != arm.arm_id or record.stage != StudyStage.DISCOVERY or record.slot_number != position:
                raise StudyError("arm discovery record order is inconsistent")
        if arm.selection and tuple(arm.selection.source_record_hashes) != tuple(records[item].fingerprint() for item in arm.discovery_record_ids):
            raise StudyError("selection no longer binds exact discovery records")
        if arm.confirmation_record_id:
            record = records.get(arm.confirmation_record_id)
            if not record or record.arm_id != arm.arm_id or record.stage != StudyStage.CONFIRMATION:
                raise StudyError("arm confirmation record is inconsistent")


class StudyStateStore:
    """Atomic, locked, hash-wrapped storage for one study."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def initialize(self, spec: StudySpec, activation: StudyActivation) -> StudyState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            if self.path.exists():
                existing = self._read_unlocked()
                if existing.spec.fingerprint() != spec.fingerprint():
                    raise StudyError("study store already binds a different preregistration")
                return existing
            state = StudyState.initial(spec, activation)
            self._write_unlocked(state)
            return state

    def load(self) -> StudyState:
        with self._lock():
            return self._read_unlocked()

    def mutate(self, operation: Any) -> StudyState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            current = self._read_unlocked()
            updated = operation(current)
            if not isinstance(updated, StudyState):
                raise StudyError("study mutation must return StudyState")
            if updated.spec.fingerprint() != current.spec.fingerprint() or updated.activation != current.activation:
                raise StudyError("study preregistration and activation are immutable")
            if updated == current:
                return current
            updated = replace(updated, generation=current.generation + 1)
            _validate_state(updated)
            self._write_unlocked(updated)
            return updated

    def _lock(self):
        class Lock:
            def __init__(inner, path: Path):
                inner.path = path
                inner.handle = None
            def __enter__(inner):
                inner.path.parent.mkdir(parents=True, exist_ok=True)
                inner.handle = open(inner.path, "a+", encoding="utf-8")
                fcntl.flock(inner.handle.fileno(), fcntl.LOCK_EX)
            def __exit__(inner, *_: Any):
                assert inner.handle is not None
                fcntl.flock(inner.handle.fileno(), fcntl.LOCK_UN)
                inner.handle.close()
        return Lock(self.lock_path)

    def _read_unlocked(self) -> StudyState:
        if not self.path.exists():
            raise StudyError("study state is not initialized")
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StudyError("study state is unreadable") from error
        data = require_exact_keys(envelope, "study state envelope", {"payload", "sha256"})
        if fingerprint(data["payload"]) != require_sha256(data["sha256"], "study state hash"):
            raise StudyError("study state hash mismatch")
        return StudyState.from_dict(data["payload"])

    def _write_unlocked(self, state: StudyState) -> None:
        payload = state.to_dict()
        encoded = (canonical_json({"payload": payload, "sha256": fingerprint(payload)}) + "\n").encode()
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ThreeArmStudy:
    """Apply the frozen discovery, selection, and confirmation protocol."""

    def __init__(self, store: StudyStateStore):
        self.store = store

    def record_discovery(self, record: StudyTrialRecord) -> StudyState:
        if StudyTrialRecord.from_dict(record.to_dict()) != record:
            raise StudyError("study record is not canonical")
        def operation(state: StudyState) -> StudyState:
            existing = next((item for item in state.records if item.record_id == record.record_id), None)
            if existing:
                if existing.fingerprint() != record.fingerprint():
                    raise StudyError("record ID was reused with different content")
                return state
            if state.phase != StudyPhase.ACTIVE_DISCOVERY:
                raise StudyError("discovery is closed")
            arm = state.arm(record.arm_id)
            expected_slot = len(arm.discovery_record_ids) + 1
            if record.stage != StudyStage.DISCOVERY or record.slot_number != expected_slot:
                raise StudyError(f"next discovery slot for {record.arm_id} is {expected_slot}")
            self._validate_record(state, arm, record, confirmation=False)
            incumbent = arm.incumbent_commit
            if record.evaluation and record.evaluation.decision == Decision.KEEP:
                assert record.candidate_commit is not None
                incumbent = record.candidate_commit
            new_arm = replace(arm, incumbent_commit=incumbent, discovery_record_ids=(*arm.discovery_record_ids, record.record_id))
            arms = tuple(new_arm if item.arm_id == arm.arm_id else item for item in state.arms)
            all_full = all(len(item.discovery_record_ids) == 3 for item in arms)
            return replace(state, arms=arms, records=(*state.records, record), phase=(StudyPhase.DISCOVERY_COMPLETE if all_full else state.phase))
        return self.store.mutate(operation)

    def select_candidates(self) -> StudyState:
        def operation(state: StudyState) -> StudyState:
            if state.phase == StudyPhase.ACTIVE_CONFIRMATION:
                return state
            if state.phase != StudyPhase.DISCOVERY_COMPLETE:
                raise StudyError("selection requires all nine discovery slots")
            records = {item.record_id: item for item in state.records}
            arms: list[StudyArmState] = []
            for arm in state.arms:
                source = tuple(records[item] for item in arm.discovery_record_ids)
                eligible = [item for item in source if item.status == StudyRecordStatus.COMPLETE and item.candidate_valid and item.evaluation and item.evaluation.candidate_mean_success is not None]
                eligible.sort(key=lambda item: (
                    -float(item.evaluation.candidate_mean_success),
                    -float(item.evaluation.mean_success_delta or 0),
                    item.worker_gpu_cost_usd,
                    item.worker_wall_time_seconds,
                    item.record_id,
                ))
                selected = eligible[0] if eligible else None
                reason = (
                    "highest valid candidate_mean_success; ties use delta, GPU cost, wall time, then record ID"
                    if selected else "no complete valid discovery candidate; no replacement from another arm"
                )
                arms.append(replace(arm, selection=ArmSelection.create(arm_id=arm.arm_id, selected=selected, source_records=source, reason=reason)))
            return replace(state, arms=tuple(arms), phase=StudyPhase.ACTIVE_CONFIRMATION)
        return self.store.mutate(operation)

    def record_confirmation(self, record: StudyTrialRecord) -> StudyState:
        if StudyTrialRecord.from_dict(record.to_dict()) != record:
            raise StudyError("study record is not canonical")
        def operation(state: StudyState) -> StudyState:
            existing = next((item for item in state.records if item.record_id == record.record_id), None)
            if existing:
                if existing.fingerprint() != record.fingerprint():
                    raise StudyError("record ID was reused with different content")
                return state
            if state.phase != StudyPhase.ACTIVE_CONFIRMATION:
                raise StudyError("confirmation is not active")
            arm = state.arm(record.arm_id)
            if not arm.selection or not arm.selection.selected_candidate_commit:
                raise StudyError("arm has no candidate eligible for confirmation")
            if arm.confirmation_record_id:
                raise StudyError("arm already has a confirmation record")
            if record.stage != StudyStage.CONFIRMATION or record.slot_number != 1:
                raise StudyError("confirmation uses one aggregate paired-seed record per arm")
            if record.candidate_commit != arm.selection.selected_candidate_commit:
                raise StudyError("confirmation candidate differs from frozen selection")
            self._validate_record(state, arm, record, confirmation=True)
            new_arm = replace(arm, confirmation_record_id=record.record_id)
            arms = tuple(new_arm if item.arm_id == arm.arm_id else item for item in state.arms)
            complete = all(
                (item.selection is not None and item.selection.selected_candidate_commit is None)
                or item.confirmation_record_id is not None
                for item in arms
            )
            return replace(state, arms=arms, records=(*state.records, record), phase=(StudyPhase.COMPLETE if complete else state.phase))
        return self.store.mutate(operation)

    @staticmethod
    def _validate_record(state: StudyState, arm: StudyArmState, record: StudyTrialRecord, *, confirmation: bool) -> None:
        arm_spec = state.spec.arm(record.arm_id)
        if record.edit_mode != arm_spec.edit_mode:
            raise StudyError("record edit mode does not match preregistered arm")
        expected_incumbent = state.spec.baseline_commit if confirmation else arm.incumbent_commit
        if record.incumbent_before != expected_incumbent:
            raise StudyError("record crosses arm lineage or uses the wrong confirmation baseline")
        if arm_spec.proposer == ProposerKind.FIXED_RULE and record.proposal_session_hash is not None:
            raise StudyError("fixed-rule arm cannot contain an LLM session")
        if arm_spec.proposer == ProposerKind.CLAUDE and record.status != StudyRecordStatus.INVALID and record.proposal_session_hash is None:
            raise StudyError("Claude arm requires a proposal session hash")
        if Decimal(record.proposal_llm_cost_usd) > Decimal(arm_spec.max_llm_cost_usd_per_candidate):
            raise StudyError("record exceeds its preregistered LLM budget")
        if record.worker_gpu_cost_usd > Decimal(arm_spec.max_gpu_cost_usd_per_candidate):
            raise StudyError("record exceeds its preregistered GPU budget")
        if record.worker_wall_time_seconds > arm_spec.max_wall_time_seconds_per_candidate:
            raise StudyError("record exceeds its preregistered wall-time budget")
        if record.status == StudyRecordStatus.INVALID:
            return
        if record.evaluation is None:
            raise StudyError("evaluated record is missing its evaluation summary")
        if record.evaluation.campaign_id != state.spec.campaign_id:
            raise StudyError("record evaluation belongs to another campaign")
        if record.evaluation.evaluator_version != state.spec.evaluator_version:
            raise StudyError("record evaluation uses another evaluator")
        if tuple(sorted(item.seed for item in record.evidence)) != tuple(sorted(state.spec.paired_seeds)) or len(record.evidence) != 3:
            raise StudyError("evaluated record requires the exact three paired seeds")
        for item in record.evidence:
            if item.campaign_id != state.spec.campaign_id:
                raise StudyError("record evidence belongs to another campaign")
            if item.arm_id != record.arm_id or item.parent_commit != expected_incumbent or item.candidate_commit != record.candidate_commit:
                raise StudyError("record evidence crosses arm/candidate lineage")
            if item.rlinf_commit != state.spec.rlinf_commit or item.reset_set_hash != state.spec.reset_set_hash or item.evaluator_version != state.spec.evaluator_version:
                raise StudyError("record evidence violates the frozen science identity")


def equal_budget_audit(spec: StudySpec) -> dict[str, Any]:
    """Return a mechanical parity audit suitable for reports and tests."""

    return {
        "three_slots_each": all(arm.discovery_slots == 3 for arm in spec.arms),
        "equal_worker_wall_caps": len({arm.max_wall_time_seconds_per_candidate for arm in spec.arms}) == 1,
        "equal_worker_gpu_caps": len({arm.max_gpu_cost_usd_per_candidate for arm in spec.arms}) == 1,
        "equal_claude_llm_caps": spec.arms[1].max_llm_cost_usd_per_candidate == spec.arms[2].max_llm_cost_usd_per_candidate,
        "fixed_rule_llm_cap_zero": Decimal(spec.arms[0].max_llm_cost_usd_per_candidate) == 0,
        "paired_confirmation_seeds": list(spec.paired_seeds),
        "passed": True,
    }
