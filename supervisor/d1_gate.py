"""Read-only D1 Stage-7 evidence binding and evaluator replay gate."""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.d1_rules import decide_d1_candidate
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
from supervisor.contracts import (
    SCHEMA_VERSION,
    ArtifactRef,
    CampaignSpec,
    Decision,
    TrialEvidence,
)
from supervisor.evaluation import EvaluationResult, OfflineD1Evaluator


REQUIRED_STAGE7_ARTIFACTS = frozenset(
    {
        "commands",
        "configs",
        "tracker",
        "run-table",
        "plots",
        "cost-report",
        "limitations",
    }
)
DEFAULT_PACK_PATH = Path("results/d1-stage7/evidence_pack.json")


class D1GateError(ContractError):
    """Raised when D1 evidence cannot satisfy the replay contract."""


class D1GateStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    INVALID = "invalid"


class D1Condition(str, Enum):
    REFERENCE = "reference"
    CONTROL = "control"
    CANDIDATE = "candidate"


@dataclass(frozen=True)
class D1ConditionRun:
    run_id: str
    condition: D1Condition
    seed: int
    project_commit: str
    config_hash: str
    command_hash: str
    started_at: str
    finished_at: str
    status: str
    exit_code: int
    elapsed_seconds: float
    gpu_cost_usd: str
    success_rate: float | None
    successful_episode_length: float | None
    metric_errors: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any, field: str) -> "D1ConditionRun":
        data = require_exact_keys(
            value,
            field,
            {
                "run_id",
                "condition",
                "seed",
                "project_commit",
                "config_hash",
                "command_hash",
                "started_at",
                "finished_at",
                "status",
                "exit_code",
                "elapsed_seconds",
                "gpu_cost_usd",
                "success_rate",
                "successful_episode_length",
                "metric_errors",
            },
        )
        try:
            condition = D1Condition(data["condition"])
        except (TypeError, ValueError) as error:
            raise D1GateError(f"{field}.condition is unsupported") from error
        seed = data["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise D1GateError(f"{field}.seed must be a non-negative integer")
        status = data["status"]
        if status not in {"complete", "failed", "cancelled"}:
            raise D1GateError(f"{field}.status is unsupported")
        exit_code = data["exit_code"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise D1GateError(f"{field}.exit_code must be an integer")
        if (status == "complete") != (exit_code == 0):
            raise D1GateError(f"{field} status and exit code disagree")
        started = parse_timestamp(data["started_at"], f"{field}.started_at")
        finished = parse_timestamp(data["finished_at"], f"{field}.finished_at")
        if finished < started:
            raise D1GateError(f"{field} finished before it started")
        elapsed = data["elapsed_seconds"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(float(elapsed))
            or elapsed < 0
        ):
            raise D1GateError(f"{field}.elapsed_seconds must be finite and non-negative")
        success = cls._optional_number(
            data["success_rate"], f"{field}.success_rate", minimum=0, maximum=1
        )
        length = cls._optional_number(
            data["successful_episode_length"],
            f"{field}.successful_episode_length",
            minimum=0,
            strict_minimum=True,
        )
        errors = data["metric_errors"]
        if not isinstance(errors, list) or not all(
            isinstance(item, str) and item.strip() for item in errors
        ):
            raise D1GateError(f"{field}.metric_errors must contain non-empty strings")
        if status == "complete" and success is None and not errors:
            raise D1GateError(
                f"{field} must record success_rate or an explicit metric error"
            )
        return cls(
            run_id=require_identifier(data["run_id"], f"{field}.run_id"),
            condition=condition,
            seed=seed,
            project_commit=require_git_commit(
                data["project_commit"], f"{field}.project_commit"
            ),
            config_hash=require_sha256(data["config_hash"], f"{field}.config_hash"),
            command_hash=require_sha256(
                data["command_hash"], f"{field}.command_hash"
            ),
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            status=status,
            exit_code=exit_code,
            elapsed_seconds=float(elapsed),
            gpu_cost_usd=decimal_text(
                parse_decimal(data["gpu_cost_usd"], f"{field}.gpu_cost_usd")
            ),
            success_rate=success,
            successful_episode_length=length,
            metric_errors=tuple(errors),
        )

    @staticmethod
    def _optional_number(
        value: Any,
        field: str,
        *,
        minimum: float,
        maximum: float | None = None,
        strict_minimum: bool = False,
    ) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise D1GateError(f"{field} must be numeric or null")
        number = float(value)
        if not math.isfinite(number):
            raise D1GateError(f"{field} must be finite")
        if (strict_minimum and number <= minimum) or (
            not strict_minimum and number < minimum
        ):
            raise D1GateError(f"{field} is below its minimum")
        if maximum is not None and number > maximum:
            raise D1GateError(f"{field} is above its maximum")
        return number

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "condition": self.condition.value,
            "seed": self.seed,
            "project_commit": self.project_commit,
            "config_hash": self.config_hash,
            "command_hash": self.command_hash,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed_seconds,
            "gpu_cost_usd": self.gpu_cost_usd,
            "success_rate": self.success_rate,
            "successful_episode_length": self.successful_episode_length,
            "metric_errors": list(self.metric_errors),
        }


@dataclass(frozen=True)
class D1EvidencePack:
    pack_id: str
    known_good_commit: str
    incumbent_commit: str
    candidate_commit: str
    campaign: CampaignSpec
    baseline_non_degenerate: bool
    legacy_decision: Decision
    reviewed_by: str
    reviewed_at: str
    conclusion: str
    runs: tuple[D1ConditionRun, ...]
    artifacts: tuple[ArtifactRef, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "D1EvidencePack":
        data = require_exact_keys(
            value,
            "d1_pack",
            {
                "schema_version",
                "pack_id",
                "known_good_commit",
                "incumbent_commit",
                "candidate_commit",
                "campaign",
                "baseline_non_degenerate",
                "legacy_decision",
                "reviewed_by",
                "reviewed_at",
                "conclusion",
                "runs",
                "artifacts",
            },
        )
        if data["schema_version"] != SCHEMA_VERSION:
            raise D1GateError(f"d1_pack.schema_version must be {SCHEMA_VERSION}")
        campaign = CampaignSpec.from_dict(data["campaign"])
        incumbent = require_git_commit(
            data["incumbent_commit"], "d1_pack.incumbent_commit"
        )
        candidate = require_git_commit(
            data["candidate_commit"], "d1_pack.candidate_commit"
        )
        if campaign.baseline_commit != incumbent:
            raise D1GateError("D1 pack campaign baseline does not match incumbent")
        if candidate == incumbent:
            raise D1GateError("D1 candidate commit must differ from incumbent")
        baseline = data["baseline_non_degenerate"]
        if not isinstance(baseline, bool):
            raise D1GateError("d1_pack.baseline_non_degenerate must be boolean")
        try:
            decision = Decision(data["legacy_decision"])
        except (TypeError, ValueError) as error:
            raise D1GateError("d1_pack.legacy_decision is unsupported") from error
        if decision == Decision.FAILED:
            raise D1GateError("D1 legacy decision cannot be failed")
        parse_timestamp(data["reviewed_at"], "d1_pack.reviewed_at")
        raw_runs = data["runs"]
        raw_artifacts = data["artifacts"]
        if not isinstance(raw_runs, list) or not raw_runs:
            raise D1GateError("d1_pack.runs must be a non-empty list")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise D1GateError("d1_pack.artifacts must be a non-empty list")
        runs = tuple(
            D1ConditionRun.from_dict(item, f"d1_pack.runs[{index}]")
            for index, item in enumerate(raw_runs)
        )
        artifacts = tuple(
            ArtifactRef.from_dict(item, f"d1_pack.artifacts[{index}]")
            for index, item in enumerate(raw_artifacts)
        )
        cls._validate_run_matrix(runs, campaign, incumbent, candidate)
        artifact_ids = {item.artifact_id for item in artifacts}
        if len(artifact_ids) != len(artifacts):
            raise D1GateError("D1 pack artifact IDs must be unique")
        missing_artifacts = sorted(REQUIRED_STAGE7_ARTIFACTS - artifact_ids)
        if missing_artifacts:
            raise D1GateError(
                f"D1 pack is missing Stage-7 artifacts: {missing_artifacts}"
            )
        return cls(
            pack_id=require_identifier(data["pack_id"], "d1_pack.pack_id"),
            known_good_commit=require_git_commit(
                data["known_good_commit"], "d1_pack.known_good_commit"
            ),
            incumbent_commit=incumbent,
            candidate_commit=candidate,
            campaign=campaign,
            baseline_non_degenerate=baseline,
            legacy_decision=decision,
            reviewed_by=require_nonempty_text(
                data["reviewed_by"], "d1_pack.reviewed_by", max_length=256
            ),
            reviewed_at=data["reviewed_at"],
            conclusion=require_nonempty_text(
                data["conclusion"], "d1_pack.conclusion", max_length=2048
            ),
            runs=runs,
            artifacts=artifacts,
        )

    @staticmethod
    def _validate_run_matrix(
        runs: Sequence[D1ConditionRun],
        campaign: CampaignSpec,
        incumbent: str,
        candidate: str,
    ) -> None:
        identities = [(item.condition, item.seed) for item in runs]
        if len(set(identities)) != len(identities):
            raise D1GateError("D1 pack contains duplicate condition/seed runs")
        if len({item.run_id for item in runs}) != len(runs):
            raise D1GateError("D1 pack run IDs must be unique")
        for condition in (D1Condition.CONTROL, D1Condition.CANDIDATE):
            actual = sorted(item.seed for item in runs if item.condition == condition)
            if actual != sorted(campaign.seeds):
                raise D1GateError(
                    f"D1 {condition.value} runs do not match approved seeds"
                )
        if not any(item.condition == D1Condition.REFERENCE for item in runs):
            raise D1GateError("D1 pack requires Reference A evidence")
        for item in runs:
            expected = candidate if item.condition == D1Condition.CANDIDATE else incumbent
            if item.project_commit != expected:
                raise D1GateError(
                    f"D1 {item.condition.value} run commit does not match its condition"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "pack_id": self.pack_id,
            "known_good_commit": self.known_good_commit,
            "incumbent_commit": self.incumbent_commit,
            "candidate_commit": self.candidate_commit,
            "campaign": self.campaign.to_dict(),
            "baseline_non_degenerate": self.baseline_non_degenerate,
            "legacy_decision": self.legacy_decision.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "conclusion": self.conclusion,
            "runs": [item.to_dict() for item in self.runs],
            "artifacts": [item.to_dict() for item in self.artifacts],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class D1ReplayResult:
    status: D1GateStatus
    pack_hash: str
    campaign_hash: str
    legacy_declared: str
    legacy_replayed: str
    supervisor_decision: str
    equivalent: bool
    reasons: tuple[str, ...]
    control_evidence: tuple[TrialEvidence, ...]
    candidate_evidence: tuple[TrialEvidence, ...]
    evaluation: EvaluationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "pack_hash": self.pack_hash,
            "campaign_hash": self.campaign_hash,
            "legacy_declared": self.legacy_declared,
            "legacy_replayed": self.legacy_replayed,
            "supervisor_decision": self.supervisor_decision,
            "equivalent": self.equivalent,
            "reasons": list(self.reasons),
            "control_evidence_hashes": [
                item.fingerprint() for item in self.control_evidence
            ],
            "candidate_evidence_hashes": [
                item.fingerprint() for item in self.candidate_evidence
            ],
            "evaluation_hash": self.evaluation.fingerprint(),
        }


def _normalize_run(pack: D1EvidencePack, run: D1ConditionRun) -> TrialEvidence:
    candidate = run.condition == D1Condition.CANDIDATE
    metrics: dict[str, float] = {}
    if run.success_rate is not None:
        metrics["success_rate"] = run.success_rate
    if run.successful_episode_length is not None:
        metrics["successful_episode_length"] = run.successful_episode_length
    return TrialEvidence.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": pack.campaign.campaign_id,
            "trial_id": run.run_id,
            "arm_id": "d1-candidate" if candidate else "d1-control",
            "parent_commit": pack.incumbent_commit,
            "candidate_commit": (
                pack.candidate_commit if candidate else pack.incumbent_commit
            ),
            "rlinf_commit": pack.campaign.rlinf_commit,
            "config_hash": run.config_hash,
            "command_hash": run.command_hash,
            "seed": run.seed,
            "reset_set_hash": pack.campaign.reset_set_hash,
            "evaluator_version": pack.campaign.evaluator_version,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "status": run.status,
            "exit_code": run.exit_code,
            "elapsed_seconds": run.elapsed_seconds,
            "gpu_cost_usd": run.gpu_cost_usd,
            "llm_cost_usd": "0",
            "metrics": metrics,
            "metric_errors": list(run.metric_errors),
            "artifacts": [],
        }
    )


def replay_d1_pack(pack: D1EvidencePack) -> D1ReplayResult:
    controls = tuple(
        _normalize_run(pack, item)
        for item in pack.runs
        if item.condition == D1Condition.CONTROL
    )
    candidates = tuple(
        _normalize_run(pack, item)
        for item in pack.runs
        if item.condition == D1Condition.CANDIDATE
    )
    controls = tuple(sorted(controls, key=lambda item: item.seed))
    candidates = tuple(sorted(candidates, key=lambda item: item.seed))
    control_success = [item.metrics.get("success_rate") for item in controls]
    candidate_success = [item.metrics.get("success_rate") for item in candidates]
    legacy = decide_d1_candidate(
        (
            [float(value) for value in control_success if value is not None]
            if all(value is not None for value in control_success)
            else []
        ),
        (
            [float(value) for value in candidate_success if value is not None]
            if all(value is not None for value in candidate_success)
            else []
        ),
        control_successful_episode_length=_optional_lengths(controls),
        candidate_successful_episode_length=_optional_lengths(candidates),
        expected_seeds=len(pack.campaign.seeds),
    )
    evaluation = OfflineD1Evaluator().evaluate(
        campaign=pack.campaign,
        decision_id=f"{pack.pack_id}.replay",
        arm_id="d1-candidate",
        incumbent_commit=pack.incumbent_commit,
        candidate_commit=pack.candidate_commit,
        control_evidence=controls,
        candidate_evidence=candidates,
        decided_at=parse_timestamp(pack.reviewed_at, "d1_pack.reviewed_at"),
    )
    supervisor_decision = evaluation.decision_record.decision.value
    equivalent = (
        pack.legacy_decision.value == legacy.decision == supervisor_decision
        and legacy.control_mean_success == evaluation.control_mean_success
        and legacy.candidate_mean_success == evaluation.candidate_mean_success
        and legacy.mean_success_delta == evaluation.mean_success_delta
        and legacy.success_delta_ci95 == evaluation.success_delta_ci95
    )
    reasons: list[str] = []
    reference_runs = [
        item for item in pack.runs if item.condition == D1Condition.REFERENCE
    ]
    if any(
        item.status != "complete"
        or item.success_rate is None
        or bool(item.metric_errors)
        for item in reference_runs
    ):
        reasons.append("Reference A evidence is incomplete or invalid")
    if not pack.baseline_non_degenerate:
        reasons.append("D1 baseline is explicitly marked degenerate")
    if not equivalent:
        reasons.append("legacy and supervisor evaluator replay are not equivalent")
    return D1ReplayResult(
        status=(
            D1GateStatus.READY
            if pack.baseline_non_degenerate and equivalent and not reasons
            else D1GateStatus.BLOCKED
        ),
        pack_hash=pack.fingerprint(),
        campaign_hash=pack.campaign.fingerprint(),
        legacy_declared=pack.legacy_decision.value,
        legacy_replayed=legacy.decision,
        supervisor_decision=supervisor_decision,
        equivalent=equivalent,
        reasons=tuple(reasons),
        control_evidence=controls,
        candidate_evidence=candidates,
        evaluation=evaluation,
    )


def _optional_lengths(evidence: Sequence[TrialEvidence]) -> list[float] | None:
    values = [item.metrics.get("successful_episode_length") for item in evidence]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


@dataclass(frozen=True)
class D1RepositoryAudit:
    status: D1GateStatus
    repository: str
    head_commit: str | None
    clean: bool
    stage7_complete: bool
    pack_path: str
    pack_exists: bool
    degenerate_baseline_recorded: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "repository": self.repository,
            "head_commit": self.head_commit,
            "clean": self.clean,
            "stage7_complete": self.stage7_complete,
            "pack_path": self.pack_path,
            "pack_exists": self.pack_exists,
            "degenerate_baseline_recorded": self.degenerate_baseline_recorded,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class D1IntegrationGateResult:
    status: D1GateStatus
    audit: D1RepositoryAudit
    replay: D1ReplayResult | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "audit": self.audit.to_dict(),
            "replay": self.replay.to_dict() if self.replay else None,
            "reasons": list(self.reasons),
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


def audit_d1_repository(
    repository: Path,
    *,
    pack_relative_path: Path = DEFAULT_PACK_PATH,
) -> D1RepositoryAudit:
    repo = repository.resolve()
    try:
        relative_pack = require_safe_relative_path(
            pack_relative_path.as_posix(), "D1 pack relative path"
        )
    except ContractError as error:
        return D1RepositoryAudit(
            status=D1GateStatus.INVALID,
            repository=str(repo),
            head_commit=None,
            clean=False,
            stage7_complete=False,
            pack_path=str(pack_relative_path),
            pack_exists=False,
            degenerate_baseline_recorded=False,
            reasons=(str(error),),
        )
    pack_relative_path = Path(relative_pack)
    reasons: list[str] = []
    if not (repo / ".git").exists():
        return D1RepositoryAudit(
            status=D1GateStatus.INVALID,
            repository=str(repo),
            head_commit=None,
            clean=False,
            stage7_complete=False,
            pack_path=str(repo / pack_relative_path),
            pack_exists=False,
            degenerate_baseline_recorded=False,
            reasons=("path is not a Git repository",),
        )
    head = _git(repo, "rev-parse", "HEAD")
    clean = not bool(_git(repo, "status", "--porcelain"))
    if not clean:
        reasons.append("D1 worktree is not clean; no immutable known-good commit exists")
    checklist_path = repo / "docs" / "execution_checklist.md"
    checklist = (
        checklist_path.read_text(encoding="utf-8") if checklist_path.exists() else ""
    )
    stage7 = checklist.split("## Stage 7", 1)[1] if "## Stage 7" in checklist else ""
    stage7_section = stage7.split("## ", 1)[0]
    checkboxes = [line for line in stage7_section.splitlines() if "- [" in line]
    stage7_complete = bool(checkboxes) and all("- [x]" in line for line in checkboxes)
    if not stage7_complete:
        reasons.append("D1 Stage-7 checklist is incomplete")
    pack_path = repo / pack_relative_path
    if not pack_path.is_file():
        reasons.append(f"D1 evidence pack is missing at {pack_relative_path}")
    diagnostic_text = checklist.lower()
    stage5b = repo / "docs" / "stage5b-resource-probe.md"
    if stage5b.exists():
        diagnostic_text += "\n" + stage5b.read_text(encoding="utf-8").lower()
    degenerate = "baseline is degenerate" in diagnostic_text
    if degenerate:
        reasons.append("D1 records a degenerate baseline and blocks Stage 6")
    return D1RepositoryAudit(
        status=D1GateStatus.READY if not reasons else D1GateStatus.BLOCKED,
        repository=str(repo),
        head_commit=head,
        clean=clean,
        stage7_complete=stage7_complete,
        pack_path=str(pack_path),
        pack_exists=pack_path.is_file(),
        degenerate_baseline_recorded=degenerate,
        reasons=tuple(reasons),
    )


def load_d1_pack(path: Path) -> D1EvidencePack:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise D1GateError(f"cannot read D1 evidence pack: {error}") from error
    except json.JSONDecodeError as error:
        raise D1GateError("D1 evidence pack is not valid JSON") from error
    return D1EvidencePack.from_dict(payload)


def run_d1_integration_gate(
    repository: Path,
    *,
    pack_relative_path: Path = DEFAULT_PACK_PATH,
) -> D1IntegrationGateResult:
    audit = audit_d1_repository(
        repository, pack_relative_path=pack_relative_path
    )
    reasons = list(audit.reasons)
    replay: D1ReplayResult | None = None
    status = audit.status
    if audit.pack_exists:
        try:
            pack = load_d1_pack(Path(audit.pack_path))
            replay = replay_d1_pack(pack)
            repo = Path(audit.repository)
            commit_checks = {
                "known-good": pack.known_good_commit,
                "incumbent": pack.incumbent_commit,
                "candidate": pack.candidate_commit,
            }
            commits_valid = True
            for label, commit in commit_checks.items():
                if not _commit_is_ancestor(repo, commit):
                    reasons.append(
                        f"D1 pack {label} commit is not an ancestor of repository HEAD"
                    )
                    commits_valid = False
            relative_pack = str(pack_relative_path.as_posix())
            pack_tracked = bool(_git(repo, "ls-files", "--", relative_pack))
            if not pack_tracked:
                reasons.append("D1 evidence pack is not tracked at repository HEAD")
            reasons.extend(replay.reasons)
            status = (
                D1GateStatus.READY
                if audit.status == D1GateStatus.READY
                and replay.status == D1GateStatus.READY
                and commits_valid
                and pack_tracked
                else D1GateStatus.BLOCKED
            )
        except ContractError as error:
            reasons.append(f"D1 pack contract is invalid: {error}")
            status = D1GateStatus.INVALID
    return D1IntegrationGateResult(
        status=status,
        audit=audit,
        replay=replay,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _git(repository: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise D1GateError(f"read-only Git audit failed: {args}") from error
    return completed.stdout.strip()


def _commit_is_ancestor(repository: Path, commit: str) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "merge-base",
                "--is-ancestor",
                commit,
                "HEAD",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise D1GateError("read-only Git ancestry audit failed") from error
    return completed.returncode == 0
