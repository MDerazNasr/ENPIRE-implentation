"""M5 local D1 launcher adapter with explicit dry-run and paid gates."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from agent.d1_config import build_d1_command, resolve_d1_config, validate_d1_config
from agent.metrics import parse_metrics, summarize_metrics
from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    parse_decimal,
    parse_timestamp,
    require_git_commit,
    require_identifier,
    require_safe_relative_path,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import (
    SCHEMA_VERSION,
    ApprovalEnvelope,
    ArtifactRef,
    CampaignSpec,
    EditMode,
    TrialEvidence,
)
from supervisor.d1_gate import D1GateStatus, D1IntegrationGateResult
from supervisor.git_manager import PreparationRecord, PreparationStatus
from supervisor.workers import (
    RunContract,
    WorkerError,
    WorkerSnapshot,
    WorkerState,
)
from supervisor.objective_validation import (
    OBJECTIVE_CONTRACT_VERSION,
    OBJECTIVE_RELATIVE_PATH,
    ObjectiveValidationResult,
    validate_actor_objective_source,
)


HYDRA_PARAMETER_MAP = {
    "warmup_bc_weight": "algorithm.actor_weight_schedule.warmup_bc_weight",
    "online_bc_weight": "algorithm.actor_weight_schedule.online_bc_weight",
    "warmup_q_weight": "algorithm.actor_weight_schedule.warmup_q_weight",
    "online_q_weight": "algorithm.actor_weight_schedule.online_q_weight",
}
WANDB_RUN = re.compile(r"https://wandb\.ai/[^\s]+/runs/[A-Za-z0-9_-]+")


class D1BackendError(ContractError):
    """Raised when a live-backend boundary or artifact is invalid."""


class ExecutionMode(str, Enum):
    DRY_RUN = "dry_run"
    FIXTURE = "fixture"
    PAID = "paid"


class BackendStatus(str, Enum):
    PLANNED = "planned"
    COMPLETE = "complete"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    INVALID_EVIDENCE = "invalid_evidence"


@dataclass(frozen=True)
class M5Authorization:
    campaign_hash: str
    mode: ExecutionMode
    authorized_at: str
    approval_hash: str | None
    gate_hash: str | None
    paid_acknowledged: bool
    synthetic: bool

    @classmethod
    def create(
        cls,
        *,
        campaign: CampaignSpec,
        mode: ExecutionMode,
        authorized_at: datetime,
        approval: ApprovalEnvelope | None = None,
        gate: D1IntegrationGateResult | None = None,
        acknowledge_paid_run: bool = False,
        allow_fixture_execution: bool = False,
    ) -> "M5Authorization":
        if not isinstance(campaign, CampaignSpec):
            raise D1BackendError("M5 authorization requires a CampaignSpec")
        if not isinstance(mode, ExecutionMode):
            raise D1BackendError("M5 authorization mode is unsupported")
        authorized_text = timestamp_text(authorized_at)
        if mode == ExecutionMode.DRY_RUN:
            if acknowledge_paid_run:
                raise D1BackendError("dry-run authorization cannot acknowledge payment")
            return cls(
                campaign_hash=campaign.fingerprint(),
                mode=mode,
                authorized_at=authorized_text,
                approval_hash=None,
                gate_hash=gate.fingerprint() if gate else None,
                paid_acknowledged=False,
                synthetic=False,
            )
        if mode == ExecutionMode.FIXTURE:
            if not allow_fixture_execution:
                raise D1BackendError("fixture execution requires an explicit test flag")
            if acknowledge_paid_run:
                raise D1BackendError("fixture execution cannot acknowledge payment")
            return cls(
                campaign_hash=campaign.fingerprint(),
                mode=mode,
                authorized_at=authorized_text,
                approval_hash=None,
                gate_hash=gate.fingerprint() if gate else None,
                paid_acknowledged=False,
                synthetic=True,
            )
        if approval is None:
            raise D1BackendError("paid execution requires campaign approval")
        approval.validate_for(campaign, authorized_at)
        if (
            gate is None
            or gate.status != D1GateStatus.READY
            or gate.replay is None
            or gate.replay.status != D1GateStatus.READY
            or not gate.replay.equivalent
            or gate.replay.campaign_hash != campaign.fingerprint()
        ):
            raise D1BackendError("paid execution requires a ready D1 integration gate")
        if not acknowledge_paid_run:
            raise D1BackendError("paid execution requires explicit acknowledgement")
        return cls(
            campaign_hash=campaign.fingerprint(),
            mode=mode,
            authorized_at=authorized_text,
            approval_hash=fingerprint(approval.to_dict()),
            gate_hash=gate.fingerprint(),
            paid_acknowledged=True,
            synthetic=False,
        )

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_hash": self.campaign_hash,
            "mode": self.mode.value,
            "authorized_at": self.authorized_at,
            "approval_hash": self.approval_hash,
            "gate_hash": self.gate_hash,
            "paid_acknowledged": self.paid_acknowledged,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True)
class D1LaunchPlan:
    contract: RunContract
    campaign_hash: str
    evaluation_trajectories: int
    mode: ExecutionMode
    workspace: str
    source_config_path: str
    derived_config_path: str
    results_root: str
    manifest_path: str
    log_path: str
    execution_argv: tuple[str, ...]
    execution_argv_hash: str
    logical_rlinf_command: tuple[str, ...]
    source_config_hash: str
    objective_path: str | None
    objective_relative_path: str | None
    objective_sha256: str | None
    objective_contract_version: str | None
    synthetic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "contract": self.contract.to_dict(),
            "campaign_hash": self.campaign_hash,
            "evaluation_trajectories": self.evaluation_trajectories,
            "mode": self.mode.value,
            "workspace": self.workspace,
            "source_config_path": self.source_config_path,
            "derived_config_path": self.derived_config_path,
            "results_root": self.results_root,
            "manifest_path": self.manifest_path,
            "log_path": self.log_path,
            "execution_argv": list(self.execution_argv),
            "execution_argv_hash": self.execution_argv_hash,
            "logical_rlinf_command": list(self.logical_rlinf_command),
            "source_config_hash": self.source_config_hash,
            "objective_path": self.objective_path,
            "objective_relative_path": self.objective_relative_path,
            "objective_sha256": self.objective_sha256,
            "objective_contract_version": self.objective_contract_version,
            "synthetic": self.synthetic,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


class D1PlanBuilder:
    """Materialize a seed-specific worker-owned config and exact command."""

    def __init__(
        self,
        *,
        results_root: Path,
        python_executable: Path,
        fixture_launcher: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.results_root = results_root.resolve()
        self.python_executable = python_executable.resolve()
        self.fixture_launcher = fixture_launcher.resolve() if fixture_launcher else None
        self.environment = dict(environment) if environment is not None else None

    def build(
        self,
        *,
        campaign: CampaignSpec,
        workspace: Path,
        source_config_relative_path: str,
        trial_id: str,
        arm_id: str,
        parent_commit: str,
        candidate_commit: str,
        seed: int,
        max_wall_time_seconds: int,
        max_gpu_cost_usd: str,
        mode: ExecutionMode,
        objective_relative_path: str | None = None,
    ) -> D1LaunchPlan:
        workspace = workspace.resolve()
        self._validate_workspace(workspace, candidate_commit)
        relative = require_safe_relative_path(
            source_config_relative_path, "M5 source config path"
        )
        source_path = workspace / relative
        resolved_source = source_path.resolve()
        if (
            resolved_source != source_path
            or not resolved_source.is_relative_to(workspace)
            or not resolved_source.is_file()
        ):
            raise D1BackendError("M5 source config must be a regular tracked file")
        source_path = resolved_source
        objective_path: Path | None = None
        objective_hash: str | None = None
        if objective_relative_path is not None:
            objective_relative = require_safe_relative_path(
                objective_relative_path, "M6 objective path"
            )
            candidate_objective = workspace / objective_relative
            resolved_objective = candidate_objective.resolve()
            if (
                resolved_objective != candidate_objective
                or not resolved_objective.is_relative_to(workspace)
                or not resolved_objective.is_file()
            ):
                raise D1BackendError("M6 objective must be a regular tracked file")
            issues = validate_actor_objective_source(resolved_objective.read_bytes())
            if issues:
                raise D1BackendError(
                    "M6 objective violates its ABI: "
                    + "; ".join(f"{item.code}:{item.message}" for item in issues)
                )
            objective_path = resolved_objective
            objective_hash = hashlib.sha256(objective_path.read_bytes()).hexdigest()
            if mode != ExecutionMode.FIXTURE:
                raise D1BackendError(
                    "live M6 objective attachment awaits the D1 compatibility handoff"
                )
        if self.results_root == workspace or self.results_root.is_relative_to(workspace):
            raise D1BackendError("M5 results root must be outside the candidate worktree")
        try:
            source = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise D1BackendError("M5 source config is not valid JSON") from error
        try:
            validate_d1_config(source)
        except ValueError as error:
            raise D1BackendError(f"M5 source config violates D1: {error}") from error
        derived = synchronize_d1_config(source, seed=seed)
        if mode != ExecutionMode.FIXTURE:
            try:
                derived = resolve_d1_config(derived, self.environment)
            except ValueError as error:
                raise D1BackendError(f"M5 could not resolve D1 environment: {error}") from error
        evaluation = derived.get("evaluation")
        if (
            not isinstance(evaluation, dict)
            or evaluation.get("num_trajectories") != campaign.evaluation_trajectories
        ):
            raise D1BackendError(
                "D1 config evaluation count does not match the campaign contract"
            )
        derived_text = canonical_json(derived)
        derived_file_text = derived_text + "\n"
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        config_hash = hashlib.sha256(derived_file_text.encode("utf-8")).hexdigest()
        trial = require_identifier(trial_id, "M5 trial ID")
        plan_root = self.results_root / ".plans" / trial
        derived_path = plan_root / "resolved_config.json"
        self._write_idempotent(derived_path, derived_file_text)
        run_directory = self.results_root / "d1" / trial
        if mode == ExecutionMode.FIXTURE:
            logical_parts = ["fixture-rlt", f"actor.seed={seed}"]
            if objective_hash is not None:
                logical_parts.extend(
                    [
                        f"objective.contract={OBJECTIVE_CONTRACT_VERSION}",
                        f"objective.sha256={objective_hash}",
                    ]
                )
            logical_command = tuple(logical_parts)
            if self.fixture_launcher is None or not self.fixture_launcher.is_file():
                raise D1BackendError("fixture mode requires a fixture launcher")
            execution_parts = [
                str(self.python_executable),
                str(self.fixture_launcher),
                "--config",
                str(derived_path),
                "--results-root",
                str(self.results_root),
                "--run-id",
                trial,
                "--logical-command-json",
                canonical_json(list(logical_command)),
                "--fixture-execute",
            ]
            if objective_path is not None and objective_hash is not None:
                execution_parts.extend(
                    [
                        "--objective-plugin",
                        str(objective_path),
                        "--objective-display-path",
                        objective_relative,
                        "--objective-sha256",
                        objective_hash,
                        "--objective-contract-version",
                        OBJECTIVE_CONTRACT_VERSION,
                    ]
                )
            execution = tuple(execution_parts)
        else:
            logical, _ = build_d1_command(derived, run_directory)
            logical_command = tuple(logical)
            execution_parts = [
                str(self.python_executable),
                "-m",
                "agent.d1_launcher",
                "--config",
                str(derived_path),
                "--results-root",
                str(self.results_root),
                "--run-id",
                trial,
            ]
            if mode == ExecutionMode.PAID:
                execution_parts.extend(["--execute", "--acknowledge-paid-run"])
            execution = tuple(execution_parts)
        contract = RunContract.create(
            campaign_id=campaign.campaign_id,
            trial_id=trial,
            arm_id=arm_id,
            parent_commit=parent_commit,
            candidate_commit=candidate_commit,
            rlinf_commit=campaign.rlinf_commit,
            config_hash=config_hash,
            command_hash=fingerprint(list(logical_command)),
            seed=seed,
            reset_set_hash=campaign.reset_set_hash,
            evaluator_version=campaign.evaluator_version,
            max_wall_time_seconds=max_wall_time_seconds,
            max_gpu_cost_usd=max_gpu_cost_usd,
        )
        return D1LaunchPlan(
            contract=contract,
            campaign_hash=campaign.fingerprint(),
            evaluation_trajectories=campaign.evaluation_trajectories,
            mode=mode,
            workspace=str(workspace),
            source_config_path=str(source_path),
            derived_config_path=str(derived_path),
            results_root=str(self.results_root),
            manifest_path=str(run_directory / "manifest.json"),
            log_path=str(run_directory / "run.log"),
            execution_argv=execution,
            execution_argv_hash=fingerprint(list(execution)),
            logical_rlinf_command=logical_command,
            source_config_hash=source_hash,
            objective_path=str(objective_path) if objective_path else None,
            objective_relative_path=(
                objective_relative if objective_path is not None else None
            ),
            objective_sha256=objective_hash,
            objective_contract_version=(
                OBJECTIVE_CONTRACT_VERSION if objective_hash else None
            ),
            synthetic=mode == ExecutionMode.FIXTURE,
        )

    @staticmethod
    def _validate_workspace(workspace: Path, candidate_commit: str) -> None:
        candidate = require_git_commit(candidate_commit, "M5 candidate commit")
        if not workspace.is_dir() or not (workspace / ".git").exists():
            raise D1BackendError("M5 workspace must be a Git checkout")
        head = _git(workspace, "rev-parse", "HEAD")
        if head != candidate:
            raise D1BackendError("M5 workspace HEAD does not match candidate commit")
        if _git(workspace, "status", "--porcelain"):
            raise D1BackendError("M5 candidate workspace must be clean")

    @staticmethod
    def _write_idempotent(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise D1BackendError("M5 derived plan path already contains other data")
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def synchronize_d1_config(source: Mapping[str, Any], *, seed: int) -> dict[str, Any]:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise D1BackendError("M5 seed must be a non-negative integer")
    derived = copy.deepcopy(dict(source))
    scientific = derived.get("scientific_values")
    overrides = derived.get("hydra_overrides")
    if not isinstance(scientific, dict) or not isinstance(overrides, list):
        raise D1BackendError("D1 config lacks scientific values or Hydra overrides")
    parsed: dict[str, str] = {}
    order: list[str] = []
    for item in overrides:
        if not isinstance(item, str) or "=" not in item:
            raise D1BackendError("D1 Hydra overrides must be key=value strings")
        key, value = item.split("=", 1)
        if key in parsed:
            raise D1BackendError(f"D1 Hydra override is duplicated: {key}")
        parsed[key] = value
        order.append(key)
    for scientific_key, hydra_key in HYDRA_PARAMETER_MAP.items():
        if scientific_key in scientific:
            parsed[hydra_key] = str(scientific[scientific_key])
            if hydra_key not in order:
                order.append(hydra_key)
    parsed["actor.seed"] = str(seed)
    if "actor.seed" not in order:
        order.append("actor.seed")
    derived["hydra_overrides"] = [f"{key}={parsed[key]}" for key in order]
    try:
        validate_d1_config(derived)
    except ValueError as error:
        raise D1BackendError(f"derived D1 config is invalid: {error}") from error
    return derived


@dataclass(frozen=True)
class ProcessOutcome:
    return_code: int | None
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stdout_hash: str
    stderr_hash: str
    timed_out: bool


class ProcessTransport(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> ProcessOutcome: ...


class SubprocessTransport:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> ProcessOutcome:
        from datetime import timezone

        started = datetime.now(timezone.utc)
        monotonic_started = time.monotonic()
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
        finished = datetime.now(timezone.utc)
        return ProcessOutcome(
            return_code=None if timed_out else process.returncode,
            started_at=timestamp_text(started),
            finished_at=timestamp_text(finished),
            elapsed_seconds=time.monotonic() - monotonic_started,
            stdout_hash=hashlib.sha256(stdout).hexdigest(),
            stderr_hash=hashlib.sha256(stderr).hexdigest(),
            timed_out=timed_out,
        )


@dataclass(frozen=True)
class D1BackendResult:
    status: BackendStatus
    plan_hash: str
    authorization_hash: str
    evidence: TrialEvidence | None
    wandb_run_url: str | None
    process: ProcessOutcome | None
    errors: tuple[str, ...]
    synthetic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "plan_hash": self.plan_hash,
            "authorization_hash": self.authorization_hash,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "wandb_run_url": self.wandb_run_url,
            "process": self.process.__dict__ if self.process else None,
            "errors": list(self.errors),
            "synthetic": self.synthetic,
        }


class D1ExperimentBackend:
    def __init__(self, transport: ProcessTransport | None = None) -> None:
        self.transport = transport or SubprocessTransport()

    def run(
        self,
        plan: D1LaunchPlan,
        authorization: M5Authorization,
    ) -> D1BackendResult:
        self._validate(plan, authorization)
        if plan.mode == ExecutionMode.DRY_RUN:
            return D1BackendResult(
                status=BackendStatus.PLANNED,
                plan_hash=plan.fingerprint(),
                authorization_hash=authorization.fingerprint(),
                evidence=None,
                wandb_run_url=None,
                process=None,
                errors=(),
                synthetic=False,
            )
        outcome = self.transport.run(
            plan.execution_argv,
            cwd=Path(plan.workspace),
            timeout_seconds=plan.contract.max_wall_time_seconds,
        )
        if outcome.timed_out:
            return self._without_evidence(
                plan, authorization, outcome, BackendStatus.TIMED_OUT,
                "D1 launcher exceeded the immutable wall-time cap",
            )
        manifest_path = Path(plan.manifest_path)
        log_path = Path(plan.log_path)
        if not manifest_path.is_file() or not log_path.is_file():
            return self._without_evidence(
                plan, authorization, outcome, BackendStatus.FAILED,
                "D1 launcher did not produce both manifest.json and run.log",
            )
        try:
            evidence, wandb_url = normalize_d1_evidence(
                plan,
                require_wandb=plan.mode == ExecutionMode.PAID,
            )
        except ContractError as error:
            return self._without_evidence(
                plan, authorization, outcome, BackendStatus.INVALID_EVIDENCE,
                str(error),
            )
        status = (
            BackendStatus.COMPLETE
            if outcome.return_code == 0 and evidence.status.value == "complete"
            else BackendStatus.FAILED
        )
        return D1BackendResult(
            status=status,
            plan_hash=plan.fingerprint(),
            authorization_hash=authorization.fingerprint(),
            evidence=evidence,
            wandb_run_url=wandb_url,
            process=outcome,
            errors=(),
            synthetic=authorization.synthetic,
        )

    @staticmethod
    def _validate(plan: D1LaunchPlan, authorization: M5Authorization) -> None:
        require_sha256(authorization.campaign_hash, "M5 authorization campaign hash")
        parse_timestamp(authorization.authorized_at, "M5 authorization timestamp")
        if authorization.mode == ExecutionMode.PAID:
            if (
                not authorization.paid_acknowledged
                or authorization.synthetic
                or authorization.approval_hash is None
                or authorization.gate_hash is None
            ):
                raise D1BackendError("M5 paid authorization invariants are invalid")
            require_sha256(authorization.approval_hash, "M5 approval hash")
            require_sha256(authorization.gate_hash, "M5 gate hash")
        elif authorization.mode == ExecutionMode.FIXTURE:
            if authorization.paid_acknowledged or not authorization.synthetic:
                raise D1BackendError("M5 fixture authorization invariants are invalid")
        elif authorization.paid_acknowledged or authorization.synthetic:
            raise D1BackendError("M5 dry-run authorization invariants are invalid")
        if plan.mode != authorization.mode:
            raise D1BackendError("M5 plan and authorization modes differ")
        if plan.campaign_hash != authorization.campaign_hash:
            raise D1BackendError("M5 authorization is bound to another campaign")
        if plan.contract.campaign_id == "":
            raise D1BackendError("M5 run contract campaign is missing")
        if plan.synthetic != authorization.synthetic:
            raise D1BackendError("M5 plan synthetic label disagrees with authorization")
        objective_fields = (
            plan.objective_path,
            plan.objective_relative_path,
            plan.objective_sha256,
            plan.objective_contract_version,
        )
        if any(item is not None for item in objective_fields) and not all(
            item is not None for item in objective_fields
        ):
            raise D1BackendError("M6 objective provenance is incomplete")
        if plan.objective_path is not None:
            if plan.objective_contract_version != OBJECTIVE_CONTRACT_VERSION:
                raise D1BackendError("M6 objective contract version is unsupported")
            objective_hash = hashlib.sha256(
                Path(plan.objective_path).read_bytes()
            ).hexdigest()
            if objective_hash != plan.objective_sha256:
                raise D1BackendError("M6 objective source hash mismatch")
        if fingerprint(list(plan.execution_argv)) != plan.execution_argv_hash:
            raise D1BackendError("M5 execution argv hash mismatch")
        if fingerprint(list(plan.logical_rlinf_command)) != plan.contract.command_hash:
            raise D1BackendError("M5 logical RLinf command hash mismatch")
        config_hash = hashlib.sha256(Path(plan.derived_config_path).read_bytes()).hexdigest()
        if config_hash != plan.contract.config_hash:
            raise D1BackendError("M5 derived config hash mismatch")

    @staticmethod
    def _without_evidence(
        plan: D1LaunchPlan,
        authorization: M5Authorization,
        outcome: ProcessOutcome,
        status: BackendStatus,
        error: str,
    ) -> D1BackendResult:
        return D1BackendResult(
            status=status,
            plan_hash=plan.fingerprint(),
            authorization_hash=authorization.fingerprint(),
            evidence=None,
            wandb_run_url=None,
            process=outcome,
            errors=(error,),
            synthetic=authorization.synthetic,
        )


@dataclass
class _D1WorkerRun:
    plan: D1LaunchPlan
    authorization: M5Authorization
    state: WorkerState = WorkerState.NEW
    heartbeat_count: int = 0
    result: D1BackendResult | None = None


class D1ProcessWorker:
    """Synchronous ExperimentWorker backed by the guarded D1 subprocess adapter."""

    def __init__(
        self,
        *,
        worker_id: str = "d1-local-worker",
        backend: D1ExperimentBackend | None = None,
    ) -> None:
        self.worker_id = require_identifier(worker_id, "D1 worker ID")
        self.backend = backend or D1ExperimentBackend()
        self._runs: dict[str, _D1WorkerRun] = {}

    def register(
        self,
        plan: D1LaunchPlan,
        authorization: M5Authorization,
    ) -> None:
        D1ExperimentBackend._validate(plan, authorization)
        trial_id = plan.contract.trial_id
        existing = self._runs.get(trial_id)
        if existing is not None:
            if (
                existing.plan.fingerprint() != plan.fingerprint()
                or existing.authorization.fingerprint() != authorization.fingerprint()
            ):
                raise WorkerError(
                    "D1 trial ID is already registered to different immutable inputs"
                )
            return
        self._runs[trial_id] = _D1WorkerRun(
            plan=plan,
            authorization=authorization,
        )

    def _run(self, trial_id: str) -> _D1WorkerRun:
        trial = require_identifier(trial_id, "D1 worker trial ID")
        if trial not in self._runs:
            raise WorkerError(f"D1 worker has no registered plan for {trial!r}")
        return self._runs[trial]

    def _snapshot(self, run: _D1WorkerRun) -> WorkerSnapshot:
        evidence = run.result.evidence if run.result else None
        return WorkerSnapshot(
            worker_id=self.worker_id,
            trial_id=run.plan.contract.trial_id,
            state=run.state,
            contract_hash=run.plan.contract.fingerprint(),
            heartbeat_count=run.heartbeat_count,
            evidence_hash=evidence.fingerprint() if evidence else None,
        )

    def prepare(self, contract: RunContract) -> WorkerSnapshot:
        if not isinstance(contract, RunContract):
            raise WorkerError("D1 worker requires a RunContract")
        run = self._run(contract.trial_id)
        if run.plan.contract.fingerprint() != contract.fingerprint():
            raise WorkerError("D1 worker plan and run contract disagree")
        if run.state == WorkerState.NEW:
            run.state = WorkerState.PREPARED
        elif run.state not in {
            WorkerState.PREPARED,
            WorkerState.COMPLETED,
            WorkerState.FAILED,
            WorkerState.CANCELLED,
            WorkerState.LOST,
        }:
            raise WorkerError("D1 worker cannot prepare the trial in its current state")
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
            raise WorkerError("D1 trial is not prepared for launch")
        run.state = WorkerState.RUNNING
        run.result = self.backend.run(run.plan, run.authorization)
        if run.result.status == BackendStatus.COMPLETE:
            run.state = WorkerState.COMPLETED
        elif run.result.evidence is not None:
            run.state = WorkerState.FAILED
        else:
            run.state = WorkerState.LOST
        return self._snapshot(run)

    def status(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot(self._run(trial_id))

    def heartbeat(self, trial_id: str) -> WorkerSnapshot:
        run = self._run(trial_id)
        if run.state in {WorkerState.PREPARED, WorkerState.RUNNING}:
            run.heartbeat_count += 1
        return self._snapshot(run)

    def cancel(self, trial_id: str) -> WorkerSnapshot:
        run = self._run(trial_id)
        if run.state in {WorkerState.NEW, WorkerState.PREPARED}:
            run.state = WorkerState.CANCELLED
        elif run.state == WorkerState.RUNNING:
            raise WorkerError(
                "synchronous D1 cancellation is handled by the process wall-time cap"
            )
        return self._snapshot(run)

    def fetch_evidence(self, trial_id: str) -> TrialEvidence:
        run = self._run(trial_id)
        if run.state not in {WorkerState.COMPLETED, WorkerState.FAILED}:
            raise WorkerError("D1 terminal evidence is unavailable for this trial")
        if run.result is None or run.result.evidence is None:
            raise WorkerError("D1 terminal state has no normalized evidence")
        return run.result.evidence


class D1CoordinatorContractFactory:
    """Build seed-specific D1 plans at the coordinator contract boundary."""

    def __init__(
        self,
        *,
        builder: D1PlanBuilder,
        worker: D1ProcessWorker,
        authorization: M5Authorization,
        code_base_config_relative_path: str | None = None,
    ) -> None:
        if authorization.mode == ExecutionMode.DRY_RUN:
            raise D1BackendError(
                "coordinator execution requires fixture or paid authorization"
            )
        self.builder = builder
        self.worker = worker
        self.authorization = authorization
        self.code_base_config_relative_path = code_base_config_relative_path
        self.synthetic = authorization.synthetic

    def create(
        self,
        *,
        campaign: CampaignSpec,
        proposal: Any,
        preparation: PreparationRecord,
        trial_id: str,
        seed: int,
        incumbent_commit: str,
        candidate_commit: str,
        default_config_hash: str,
        max_gpu_cost_usd: str,
    ) -> RunContract:
        if campaign.fingerprint() != self.authorization.campaign_hash:
            raise D1BackendError("D1 factory authorization is for another campaign")
        if preparation.status != PreparationStatus.READY:
            raise D1BackendError("D1 factory requires a ready candidate preparation")
        if not preparation.worktree_path:
            raise D1BackendError("D1 candidate preparation has no isolated worktree")
        changed_paths = tuple(proposal.changed_paths)
        if len(changed_paths) != 1:
            raise D1BackendError("D1 execution requires exactly one candidate path")
        if not isinstance(default_config_hash, str) or not default_config_hash:
            raise D1BackendError("M5 coordinator config hash is missing")
        objective_path: str | None = None
        if proposal.edit_mode == EditMode.CONFIG_ONLY:
            source_config_path = changed_paths[0]
        elif proposal.edit_mode == EditMode.ACTOR_OBJECTIVE_CODE:
            if self.code_base_config_relative_path is None:
                raise D1BackendError("M6 code execution requires a frozen base config path")
            source_config_path = self.code_base_config_relative_path
            objective_path = changed_paths[0]
            if objective_path != OBJECTIVE_RELATIVE_PATH:
                raise D1BackendError(
                    "M6 code execution permits only the project-owned actor objective"
                )
            objective_checks = {
                item.check_id: item for item in preparation.checks
            }
            required = objective_checks.get("m6-objective-contract")
            if required is None or not required.passed:
                raise D1BackendError("M6 candidate lacks its mandatory objective check")
        else:
            raise D1BackendError("D1 proposal edit mode is unsupported")
        plan = self.builder.build(
            campaign=campaign,
            workspace=Path(preparation.worktree_path),
            source_config_relative_path=source_config_path,
            trial_id=trial_id,
            arm_id=proposal.arm_id,
            parent_commit=incumbent_commit,
            candidate_commit=candidate_commit,
            seed=seed,
            max_wall_time_seconds=proposal.estimated_budget.wall_time_seconds,
            max_gpu_cost_usd=max_gpu_cost_usd,
            mode=self.authorization.mode,
            objective_relative_path=objective_path,
        )
        self.worker.register(plan, self.authorization)
        return plan.contract


def normalize_d1_evidence(
    plan: D1LaunchPlan,
    *,
    require_wandb: bool,
) -> tuple[TrialEvidence, str | None]:
    manifest_path = Path(plan.manifest_path)
    log_path = Path(plan.log_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        log_text = log_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        raise D1BackendError("D1 terminal artifacts are unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise D1BackendError("D1 manifest schema is unsupported")
    contract = plan.contract
    checks = {
        "project commit": (manifest.get("project_commit"), contract.candidate_commit),
        "RLinf expected commit": (
            manifest.get("rlinf_commit_expected"), contract.rlinf_commit,
        ),
        "RLinf actual commit": (
            manifest.get("rlinf_commit_actual"), contract.rlinf_commit,
        ),
        "config hash": (manifest.get("config_sha256"), contract.config_hash),
    }
    if plan.objective_sha256 is not None:
        checks.update(
            {
                "objective hash": (
                    manifest.get("objective_sha256"),
                    plan.objective_sha256,
                ),
                "objective contract": (
                    manifest.get("objective_contract_version"),
                    plan.objective_contract_version,
                ),
            }
        )
    elif manifest.get("objective_sha256") is not None:
        raise D1BackendError("D1 manifest contains an unexpected objective")
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise D1BackendError(f"D1 manifest {label} mismatch")
    if plan.objective_path is not None:
        if hashlib.sha256(Path(plan.objective_path).read_bytes()).hexdigest() != (
            plan.objective_sha256
        ):
            raise D1BackendError("D1 objective artifact changed after planning")
        objective_validation = ObjectiveValidationResult.from_dict(
            manifest.get("objective_validation")
        )
        if (
            not objective_validation.passed
            or not objective_validation.behavior_changed
            or objective_validation.source_sha256 != plan.objective_sha256
            or objective_validation.plugin_path != plan.objective_relative_path
            or objective_validation.contract_version
            != plan.objective_contract_version
        ):
            raise D1BackendError("D1 objective validation record is inconsistent")
    command = manifest.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise D1BackendError("D1 manifest command is invalid")
    if fingerprint(command) != contract.command_hash:
        raise D1BackendError("D1 manifest command hash mismatch")
    status = manifest.get("status")
    exit_code = manifest.get("exit_code")
    if status not in {"complete", "failed"}:
        raise D1BackendError("D1 manifest is not terminal")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise D1BackendError("D1 manifest exit code is invalid")
    if (status == "complete") != (exit_code == 0):
        raise D1BackendError("D1 manifest status and exit code disagree")
    started_at = manifest.get("started_at")
    finished_at = manifest.get("finished_at")
    parse_timestamp(started_at, "D1 manifest started_at")
    parse_timestamp(finished_at, "D1 manifest finished_at")
    elapsed = manifest.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or elapsed < 0
    ):
        raise D1BackendError("D1 manifest elapsed time is invalid")
    cost_value = manifest.get("run_cost_usd")
    if cost_value is None:
        cost_value = manifest.get("final_cost_usd")
    gpu_cost = parse_decimal(cost_value, "D1 manifest run cost")
    if gpu_cost > parse_decimal(contract.max_gpu_cost_usd, "run GPU cap"):
        raise D1BackendError("D1 manifest cost exceeds immutable run cap")
    resolved = manifest.get("resolved_config")
    if not isinstance(resolved, dict):
        raise D1BackendError("D1 manifest lacks a resolved config")
    evaluation = resolved.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("fixed_reset_state_ids") is not True:
        raise D1BackendError("D1 manifest does not prove fixed reset IDs")
    if evaluation.get("num_trajectories") != plan.evaluation_trajectories:
        raise D1BackendError("D1 manifest evaluation count violates the campaign")
    override_map = _override_map(resolved.get("hydra_overrides"))
    if override_map.get("actor.seed") != str(contract.seed):
        raise D1BackendError("D1 manifest seed does not match run contract")
    histories = parse_metrics(log_text)
    summary = summarize_metrics(histories)
    metrics: dict[str, float] = {}
    metric_errors: list[str] = []
    success = summary.get("success")
    if success is None or not math.isfinite(float(success)):
        metric_errors.append("success_rate:missing_or_nonfinite")
    else:
        metrics["success_rate"] = float(success)
    successful_lengths = (
        histories.get("eval/successful_episode_length")
        or histories.get("eval/successful_episode_len")
    )
    if (
        successful_lengths
        and math.isfinite(successful_lengths[-1])
        and successful_lengths[-1] > 0
    ):
        metrics["successful_episode_length"] = float(successful_lengths[-1])
    loss = summary.get("loss")
    if loss is not None and math.isfinite(float(loss)):
        metrics["diagnostic_loss"] = float(loss)
    urls = sorted(set(WANDB_RUN.findall(log_text)))
    manifest_url = manifest.get("wandb_run_url")
    if manifest_url is not None:
        if not isinstance(manifest_url, str) or not WANDB_RUN.fullmatch(manifest_url):
            raise D1BackendError("D1 manifest W&B URL is invalid")
        urls = sorted(set([*urls, manifest_url]))
    if len(urls) > 1:
        raise D1BackendError("D1 artifacts disagree on W&B run URL")
    wandb_url = urls[0] if urls else None
    if require_wandb and wandb_url is None:
        raise D1BackendError("paid D1 evidence requires a W&B run URL")
    artifacts = [
        _local_artifact(plan.contract.trial_id, "manifest", manifest_path),
        _local_artifact(plan.contract.trial_id, "run-log", log_path),
    ]
    if plan.objective_path is not None:
        artifacts.append(
            _local_artifact(
                plan.contract.trial_id,
                "actor-objective",
                Path(plan.objective_path),
            )
        )
    if wandb_url:
        artifacts.append(
            ArtifactRef.from_dict(
                {
                    "artifact_id": "wandb-run",
                    "kind": "tracker",
                    "uri": wandb_url,
                    "sha256": fingerprint(wandb_url),
                    "size_bytes": 0,
                },
                "D1 W&B artifact",
            )
        )
    evidence = TrialEvidence.from_dict(
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
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "exit_code": exit_code,
            "elapsed_seconds": elapsed,
            "gpu_cost_usd": str(gpu_cost),
            "llm_cost_usd": "0",
            "metrics": metrics,
            "metric_errors": metric_errors,
            "artifacts": [item.to_dict() for item in artifacts],
        }
    )
    return evidence, wandb_url


def _override_map(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        raise D1BackendError("D1 resolved Hydra overrides are invalid")
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str) or "=" not in item:
            raise D1BackendError("D1 resolved Hydra overrides are invalid")
        key, raw = item.split("=", 1)
        if key in result:
            raise D1BackendError("D1 resolved Hydra overrides contain duplicates")
        result[key] = raw
    return result


def _local_artifact(trial_id: str, artifact_id: str, path: Path) -> ArtifactRef:
    return ArtifactRef.from_dict(
        {
            "artifact_id": artifact_id,
            "kind": artifact_id,
            "uri": f"artifact://trials/{trial_id}/{artifact_id}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        },
        f"D1 {artifact_id} artifact",
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
        raise D1BackendError(f"M5 read-only Git check failed: {args}") from error
    return completed.stdout.strip()
