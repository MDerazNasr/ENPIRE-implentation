"""Provider-neutral worker contracts and a deterministic offline worker."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from supervisor.canonical import (
    ContractError,
    decimal_text,
    fingerprint,
    parse_decimal,
    parse_timestamp,
    require_git_commit,
    require_identifier,
    require_sha256,
)
from supervisor.contracts import SCHEMA_VERSION, ArtifactRef, TrialEvidence, TrialStatus


class WorkerError(ContractError):
    """Raised when a worker request violates its contract or lifecycle."""


class WorkerState(str, Enum):
    NEW = "new"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


@dataclass(frozen=True)
class RunContract:
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
    max_wall_time_seconds: int
    max_gpu_cost_usd: str

    @classmethod
    def create(
        cls,
        *,
        campaign_id: str,
        trial_id: str,
        arm_id: str,
        parent_commit: str,
        candidate_commit: str,
        rlinf_commit: str,
        config_hash: str,
        command_hash: str,
        seed: int,
        reset_set_hash: str,
        evaluator_version: str,
        max_wall_time_seconds: int,
        max_gpu_cost_usd: str,
    ) -> "RunContract":
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise WorkerError("run contract seed must be a non-negative integer")
        if (
            isinstance(max_wall_time_seconds, bool)
            or not isinstance(max_wall_time_seconds, int)
            or max_wall_time_seconds <= 0
        ):
            raise WorkerError("run contract wall-time cap must be positive")
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(campaign_id, "run.campaign_id"),
            trial_id=require_identifier(trial_id, "run.trial_id"),
            arm_id=require_identifier(arm_id, "run.arm_id"),
            parent_commit=require_git_commit(parent_commit, "run.parent_commit"),
            candidate_commit=require_git_commit(
                candidate_commit, "run.candidate_commit"
            ),
            rlinf_commit=require_git_commit(rlinf_commit, "run.rlinf_commit"),
            config_hash=require_sha256(config_hash, "run.config_hash"),
            command_hash=require_sha256(command_hash, "run.command_hash"),
            seed=seed,
            reset_set_hash=require_sha256(reset_set_hash, "run.reset_set_hash"),
            evaluator_version=require_identifier(
                evaluator_version, "run.evaluator_version"
            ),
            max_wall_time_seconds=max_wall_time_seconds,
            max_gpu_cost_usd=decimal_text(
                parse_decimal(
                    max_gpu_cost_usd,
                    "run.max_gpu_cost_usd",
                    allow_zero=False,
                )
            ),
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
            "max_wall_time_seconds": self.max_wall_time_seconds,
            "max_gpu_cost_usd": self.max_gpu_cost_usd,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class WorkerScenario:
    terminal_state: WorkerState
    started_at: str
    finished_at: str
    elapsed_seconds: float
    metrics: Mapping[str, float]
    metric_errors: tuple[str, ...]
    exit_code: int
    gpu_cost_usd: str
    llm_cost_usd: str = "0"
    artifacts: tuple[ArtifactRef, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        terminal_state: WorkerState,
        started_at: str,
        finished_at: str,
        elapsed_seconds: float,
        metrics: Mapping[str, int | float],
        exit_code: int,
        gpu_cost_usd: str,
        metric_errors: tuple[str, ...] = (),
        llm_cost_usd: str = "0",
        artifacts: tuple[ArtifactRef, ...] = (),
    ) -> "WorkerScenario":
        if terminal_state not in {
            WorkerState.COMPLETED,
            WorkerState.FAILED,
            WorkerState.LOST,
        }:
            raise WorkerError("fake scenario terminal state is unsupported")
        started = parse_timestamp(started_at, "scenario.started_at")
        finished = parse_timestamp(finished_at, "scenario.finished_at")
        if finished < started:
            raise WorkerError("scenario finished before it started")
        if (
            isinstance(elapsed_seconds, bool)
            or not isinstance(elapsed_seconds, (int, float))
            or not math.isfinite(float(elapsed_seconds))
            or elapsed_seconds < 0
        ):
            raise WorkerError("scenario elapsed time must be finite and non-negative")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise WorkerError("scenario exit code must be an integer")
        if terminal_state == WorkerState.COMPLETED and exit_code != 0:
            raise WorkerError("completed fake scenario requires exit code zero")
        if terminal_state == WorkerState.FAILED and exit_code == 0:
            raise WorkerError("failed fake scenario requires non-zero exit code")
        normalized: dict[str, float] = {}
        if not isinstance(metrics, Mapping):
            raise WorkerError("scenario metrics must be an object")
        for name, value in metrics.items():
            require_identifier(name, "scenario metric name")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise WorkerError(f"scenario metric {name!r} must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise WorkerError(f"scenario metric {name!r} must be finite")
            normalized[name] = number
        if not all(isinstance(item, str) and item for item in metric_errors):
            raise WorkerError("scenario metric errors must be non-empty strings")
        if not isinstance(artifacts, tuple) or not all(
            isinstance(item, ArtifactRef) for item in artifacts
        ):
            raise WorkerError("scenario artifacts must contain ArtifactRef records")
        return cls(
            terminal_state=terminal_state,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=float(elapsed_seconds),
            metrics=MappingProxyType(normalized),
            metric_errors=metric_errors,
            exit_code=exit_code,
            gpu_cost_usd=decimal_text(
                parse_decimal(gpu_cost_usd, "scenario.gpu_cost_usd")
            ),
            llm_cost_usd=decimal_text(
                parse_decimal(llm_cost_usd, "scenario.llm_cost_usd")
            ),
            artifacts=artifacts,
        )


@dataclass(frozen=True)
class WorkerSnapshot:
    worker_id: str
    trial_id: str
    state: WorkerState
    contract_hash: str
    heartbeat_count: int
    evidence_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "trial_id": self.trial_id,
            "state": self.state.value,
            "contract_hash": self.contract_hash,
            "heartbeat_count": self.heartbeat_count,
            "evidence_hash": self.evidence_hash,
        }


class ExperimentWorker(Protocol):
    worker_id: str

    def prepare(self, contract: RunContract) -> WorkerSnapshot: ...

    def launch(self, trial_id: str) -> WorkerSnapshot: ...

    def status(self, trial_id: str) -> WorkerSnapshot: ...

    def heartbeat(self, trial_id: str) -> WorkerSnapshot: ...

    def cancel(self, trial_id: str) -> WorkerSnapshot: ...

    def fetch_evidence(self, trial_id: str) -> TrialEvidence: ...


@dataclass
class _FakeRun:
    contract: RunContract
    scenario: WorkerScenario
    state: WorkerState = WorkerState.PREPARED
    heartbeat_count: int = 0
    evidence: TrialEvidence | None = None


class FakeExperimentWorker:
    """Synchronous deterministic worker used only for offline orchestration."""

    def __init__(
        self,
        *,
        worker_id: str,
        scenarios: Mapping[str, WorkerScenario],
    ) -> None:
        self.worker_id = require_identifier(worker_id, "worker.worker_id")
        self._scenarios = dict(scenarios)
        self._runs: dict[str, _FakeRun] = {}

    def _run(self, trial_id: str) -> _FakeRun:
        trial = require_identifier(trial_id, "worker trial ID")
        if trial not in self._runs:
            raise WorkerError(f"worker has not prepared trial {trial!r}")
        return self._runs[trial]

    def _snapshot(self, run: _FakeRun) -> WorkerSnapshot:
        return WorkerSnapshot(
            worker_id=self.worker_id,
            trial_id=run.contract.trial_id,
            state=run.state,
            contract_hash=run.contract.fingerprint(),
            heartbeat_count=run.heartbeat_count,
            evidence_hash=run.evidence.fingerprint() if run.evidence else None,
        )

    def prepare(self, contract: RunContract) -> WorkerSnapshot:
        if not isinstance(contract, RunContract):
            raise WorkerError("worker requires a RunContract")
        existing = self._runs.get(contract.trial_id)
        if existing is not None:
            if existing.contract.fingerprint() != contract.fingerprint():
                raise WorkerError("trial ID is already bound to a different run contract")
            return self._snapshot(existing)
        scenario = self._scenarios.get(contract.trial_id)
        if scenario is None:
            raise WorkerError("fake worker has no scenario for this trial")
        run = _FakeRun(contract=contract, scenario=scenario)
        self._runs[contract.trial_id] = run
        return self._snapshot(run)

    def launch(self, trial_id: str) -> WorkerSnapshot:
        run = self._run(trial_id)
        if run.state in {
            WorkerState.COMPLETED,
            WorkerState.FAILED,
            WorkerState.CANCELLED,
            WorkerState.LOST,
        }:
            return self._snapshot(run)
        if run.state != WorkerState.PREPARED:
            raise WorkerError("trial is not prepared for launch")
        run.state = WorkerState.RUNNING
        if run.scenario.terminal_state == WorkerState.LOST:
            run.state = WorkerState.LOST
            return self._snapshot(run)
        run.evidence = self._evidence(run.contract, run.scenario)
        run.state = run.scenario.terminal_state
        return self._snapshot(run)

    def status(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot(self._run(trial_id))

    def heartbeat(self, trial_id: str) -> WorkerSnapshot:
        run = self._run(trial_id)
        if run.state in {
            WorkerState.COMPLETED,
            WorkerState.FAILED,
            WorkerState.CANCELLED,
            WorkerState.LOST,
        }:
            return self._snapshot(run)
        run.heartbeat_count += 1
        return self._snapshot(run)

    def cancel(self, trial_id: str) -> WorkerSnapshot:
        run = self._run(trial_id)
        if run.state in {WorkerState.PREPARED, WorkerState.RUNNING}:
            run.state = WorkerState.CANCELLED
        return self._snapshot(run)

    def fetch_evidence(self, trial_id: str) -> TrialEvidence:
        run = self._run(trial_id)
        if run.state not in {WorkerState.COMPLETED, WorkerState.FAILED}:
            raise WorkerError("terminal evidence is unavailable for this trial")
        if run.evidence is None:
            raise WorkerError("worker terminal state has no evidence")
        return run.evidence

    @staticmethod
    def _evidence(contract: RunContract, scenario: WorkerScenario) -> TrialEvidence:
        status = (
            TrialStatus.COMPLETE
            if scenario.terminal_state == WorkerState.COMPLETED
            else TrialStatus.FAILED
        )
        return TrialEvidence.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "campaign_id": contract.campaign_id,
                "trial_id": contract.trial_id,
                "arm_id": contract.arm_id,
                "parent_commit": contract.parent_commit,
                "candidate_commit": contract.candidate_commit,
                "rlinf_commit": contract.rlinf_commit,
                "config_hash": contract.config_hash,
                "command_hash": contract.command_hash,
                "seed": contract.seed,
                "reset_set_hash": contract.reset_set_hash,
                "evaluator_version": contract.evaluator_version,
                "started_at": scenario.started_at,
                "finished_at": scenario.finished_at,
                "status": status.value,
                "exit_code": scenario.exit_code,
                "elapsed_seconds": scenario.elapsed_seconds,
                "gpu_cost_usd": scenario.gpu_cost_usd,
                "llm_cost_usd": scenario.llm_cost_usd,
                "metrics": dict(scenario.metrics),
                "metric_errors": list(scenario.metric_errors),
                "artifacts": [item.to_dict() for item in scenario.artifacts],
            }
        )
