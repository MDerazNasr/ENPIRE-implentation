"""Deterministic offline evidence evaluation and per-arm incumbent state."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.d1_rules import D1DecisionResult, decide_d1_candidate
from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    require_git_commit,
    require_identifier,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import (
    SCHEMA_VERSION,
    CampaignSpec,
    Decision,
    DecisionRecord,
    TrialEvidence,
    TrialStatus,
)


class EvaluationError(ContractError):
    """Raised when evaluator or incumbent-store contracts are violated."""


@dataclass(frozen=True)
class EvaluationResult:
    evaluator_version: str
    decision_record: DecisionRecord
    control_mean_success: float | None
    candidate_mean_success: float | None
    mean_success_delta: float | None
    success_delta_ci95: tuple[float, float] | None
    control_evidence_hashes: tuple[str, ...]
    candidate_evidence_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "evaluator_version": self.evaluator_version,
            "decision_record": self.decision_record.to_dict(),
            "control_mean_success": self.control_mean_success,
            "candidate_mean_success": self.candidate_mean_success,
            "mean_success_delta": self.mean_success_delta,
            "success_delta_ci95": (
                list(self.success_delta_ci95) if self.success_delta_ci95 else None
            ),
            "control_evidence_hashes": list(self.control_evidence_hashes),
            "candidate_evidence_hashes": list(self.candidate_evidence_hashes),
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


class OfflineD1Evaluator:
    """Exercise the frozen D1 rule on strict synthetic/fixture evidence."""

    SUCCESS_METRIC = "success_rate"
    LENGTH_METRIC = "successful_episode_length"

    def evaluate(
        self,
        *,
        campaign: CampaignSpec,
        decision_id: str,
        arm_id: str,
        incumbent_commit: str,
        candidate_commit: str,
        control_evidence: Sequence[TrialEvidence],
        candidate_evidence: Sequence[TrialEvidence],
        decided_at: datetime | None = None,
    ) -> EvaluationResult:
        decision_id = require_identifier(decision_id, "evaluation.decision_id")
        arm_id = require_identifier(arm_id, "evaluation.arm_id")
        incumbent = require_git_commit(incumbent_commit, "evaluation.incumbent")
        candidate = require_git_commit(candidate_commit, "evaluation.candidate")
        controls = tuple(control_evidence)
        candidates = tuple(candidate_evidence)
        all_evidence = (*controls, *candidates)
        if not all_evidence:
            raise EvaluationError("evaluation requires control and candidate evidence")
        failure = self._hard_failure(all_evidence)
        mismatch = self._identity_mismatch(
            campaign,
            arm_id,
            incumbent,
            candidate,
            controls,
            candidates,
        )
        expected_seeds = tuple(campaign.seeds)
        controls_by_seed = self._by_seed(controls)
        candidates_by_seed = self._by_seed(candidates)
        missing = (
            tuple(sorted(controls_by_seed)) != tuple(sorted(expected_seeds))
            or tuple(sorted(candidates_by_seed)) != tuple(sorted(expected_seeds))
            or len(controls_by_seed) != len(controls)
            or len(candidates_by_seed) != len(candidates)
        )

        d1_result: D1DecisionResult | None = None
        if failure:
            decision = Decision.FAILED
            reason = failure
        elif mismatch:
            decision = Decision.INCONCLUSIVE
            reason = mismatch
        elif missing:
            decision = Decision.INCONCLUSIVE
            reason = "missing or duplicate evidence for the approved seed set"
        elif self._missing_success_metric(all_evidence):
            decision = Decision.INCONCLUSIVE
            reason = "required success_rate metric is missing"
        else:
            control_success = [
                controls_by_seed[seed].metrics.get(self.SUCCESS_METRIC)
                for seed in expected_seeds
            ]
            candidate_success = [
                candidates_by_seed[seed].metrics.get(self.SUCCESS_METRIC)
                for seed in expected_seeds
            ]
            control_lengths = self._optional_metric(
                controls_by_seed, expected_seeds, self.LENGTH_METRIC
            )
            candidate_lengths = self._optional_metric(
                candidates_by_seed, expected_seeds, self.LENGTH_METRIC
            )
            d1_result = decide_d1_candidate(
                control_success,
                candidate_success,
                control_successful_episode_length=control_lengths,
                candidate_successful_episode_length=candidate_lengths,
                expected_seeds=len(expected_seeds),
            )
            decision = Decision(d1_result.decision)
            reason = f"offline fixture D1 rule: {d1_result.reason}"

        ordered = tuple(
            sorted(controls, key=lambda item: item.seed)
            + sorted(candidates, key=lambda item: item.seed)
        )
        after = candidate if decision == Decision.KEEP else incumbent
        decision_record = DecisionRecord.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "campaign_id": campaign.campaign_id,
                "decision_id": decision_id,
                "trial_ids": [item.trial_id for item in ordered],
                "evaluator_version": campaign.evaluator_version,
                "decision": decision.value,
                "reason": reason,
                "decided_at": timestamp_text(
                    decided_at or datetime.now(timezone.utc)
                ),
                "evidence_hashes": [item.fingerprint() for item in ordered],
                "incumbent_before": incumbent,
                "incumbent_after": after,
            }
        )
        return EvaluationResult(
            evaluator_version=campaign.evaluator_version,
            decision_record=decision_record,
            control_mean_success=(
                d1_result.control_mean_success if d1_result else None
            ),
            candidate_mean_success=(
                d1_result.candidate_mean_success if d1_result else None
            ),
            mean_success_delta=d1_result.mean_success_delta if d1_result else None,
            success_delta_ci95=(
                d1_result.success_delta_ci95 if d1_result else None
            ),
            control_evidence_hashes=tuple(item.fingerprint() for item in controls),
            candidate_evidence_hashes=tuple(
                item.fingerprint() for item in candidates
            ),
        )

    @staticmethod
    def _by_seed(evidence: Sequence[TrialEvidence]) -> dict[int, TrialEvidence]:
        return {item.seed: item for item in evidence}

    @staticmethod
    def _hard_failure(evidence: Sequence[TrialEvidence]) -> str | None:
        for item in evidence:
            if item.status != TrialStatus.COMPLETE:
                return f"trial {item.trial_id} did not complete successfully"
            if item.metric_errors:
                return f"trial {item.trial_id} contains metric errors"
        return None

    @classmethod
    def _missing_success_metric(
        cls, evidence: Sequence[TrialEvidence]
    ) -> bool:
        return any(cls.SUCCESS_METRIC not in item.metrics for item in evidence)

    @staticmethod
    def _identity_mismatch(
        campaign: CampaignSpec,
        arm_id: str,
        incumbent: str,
        candidate: str,
        controls: Sequence[TrialEvidence],
        candidates: Sequence[TrialEvidence],
    ) -> str | None:
        for item in (*controls, *candidates):
            if item.campaign_id != campaign.campaign_id:
                return "evidence campaign identity mismatch"
            if item.rlinf_commit != campaign.rlinf_commit:
                return "evidence RLinf commit mismatch"
            if item.reset_set_hash != campaign.reset_set_hash:
                return "evidence reset-set mismatch"
            if item.evaluator_version != campaign.evaluator_version:
                return "evidence evaluator version mismatch"
        for item in controls:
            if item.candidate_commit != incumbent:
                return "control evidence does not represent the incumbent"
        for item in candidates:
            if (
                item.arm_id != arm_id
                or item.parent_commit != incumbent
                or item.candidate_commit != candidate
            ):
                return "candidate evidence identity or lineage mismatch"
        return None

    @staticmethod
    def _optional_metric(
        by_seed: Mapping[int, TrialEvidence],
        seeds: Sequence[int],
        metric: str,
    ) -> list[float] | None:
        values = [by_seed[seed].metrics.get(metric) for seed in seeds]
        if any(value is None for value in values):
            return None
        return [float(value) for value in values if value is not None]


class ArmIncumbentStore:
    """Small locked JSON state: decisions move only their named arm pointer."""

    def __init__(
        self,
        path: Path,
        *,
        campaign_id: str,
        initial_incumbents: Mapping[str, str],
    ) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.campaign_id = require_identifier(campaign_id, "incumbents.campaign_id")
        if not initial_incumbents:
            raise EvaluationError("incumbent store requires at least one arm")
        self.initial_incumbents = {
            require_identifier(arm, "incumbents arm"): require_git_commit(
                commit, f"incumbents.{arm}"
            )
            for arm, commit in initial_incumbents.items()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            if self.path.exists():
                self._load()
            else:
                self._write(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "campaign_id": self.campaign_id,
                        "incumbents": dict(sorted(self.initial_incumbents.items())),
                        "applied_decisions": {},
                    }
                )
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvaluationError("incumbent store is not valid JSON") from error
        if not isinstance(data, dict) or set(data) != {
            "schema_version",
            "campaign_id",
            "incumbents",
            "applied_decisions",
        }:
            raise EvaluationError("incumbent store fields are invalid")
        if data["schema_version"] != SCHEMA_VERSION:
            raise EvaluationError("incumbent store schema version is unsupported")
        if data["campaign_id"] != self.campaign_id:
            raise EvaluationError("incumbent store campaign mismatch")
        incumbents = data["incumbents"]
        decisions = data["applied_decisions"]
        if not isinstance(incumbents, dict) or not isinstance(decisions, dict):
            raise EvaluationError("incumbent store mappings are invalid")
        for arm, commit in incumbents.items():
            require_identifier(arm, "stored incumbent arm")
            require_git_commit(commit, f"stored incumbent {arm}")
        for decision_id, decision_hash in decisions.items():
            require_identifier(decision_id, "stored decision ID")
            require_sha256(decision_hash, "stored decision hash")
        if set(incumbents) != set(self.initial_incumbents):
            raise EvaluationError("stored incumbent arms do not match configuration")
        return data

    def _write(self, data: Mapping[str, Any]) -> None:
        payload = canonical_json(dict(data)).encode("utf-8") + b"\n"
        descriptor, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self) -> dict[str, str]:
        return dict(self._load()["incumbents"])

    def apply(self, arm_id: str, result: EvaluationResult) -> str:
        arm = require_identifier(arm_id, "incumbent update arm")
        record = result.decision_record
        if record.campaign_id != self.campaign_id:
            raise EvaluationError("decision campaign does not match incumbent store")
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            data = self._load()
            incumbents = data["incumbents"]
            applied = data["applied_decisions"]
            if arm not in incumbents:
                raise EvaluationError("decision arm is not registered")
            decision_hash = record.fingerprint()
            existing = applied.get(record.decision_id)
            if existing is not None:
                if existing != decision_hash:
                    raise EvaluationError("decision ID is already bound to another record")
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return incumbents[arm]
            if incumbents[arm] != record.incumbent_before:
                raise EvaluationError("decision incumbent does not match current arm")
            incumbents[arm] = record.incumbent_after
            applied[record.decision_id] = decision_hash
            self._write(data)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return incumbents[arm]
