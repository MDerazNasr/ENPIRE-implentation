"""Durable M7 worker registry, lease scheduler, and concurrent dispatcher."""

from __future__ import annotations

import fcntl
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    decimal_text,
    fingerprint,
    parse_decimal,
    parse_timestamp,
    require_git_commit,
    require_identifier,
    require_nonempty_text,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import (
    CampaignSpec,
    SCHEMA_VERSION,
    TrialEvidence,
    TrialStatus,
)
from supervisor.workers import (
    ExperimentWorker,
    RunContract,
    WorkerSnapshot,
    WorkerState,
)


SCHEDULER_VERSION = "m7-scheduler-v1"


class SchedulerError(ContractError):
    """Raised when durable dispatch state or a worker response is invalid."""


class WorkerAvailability(str, Enum):
    READY = "ready"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"


class DispatchState(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LeaseState(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    LOST = "lost"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchedulerError(f"{field} must be an integer")
    if value < 0 or (not allow_zero and value == 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise SchedulerError(f"{field} must be {comparator}")
    return value


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise SchedulerError(f"{field} is unsupported") from error


@dataclass(frozen=True)
class WorkerCapabilities:
    worker_id: str
    transport: str
    gpu_name: str
    gpu_memory_gb: int
    supported_modes: tuple[str, ...]
    max_slots: int = 1

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        transport: str,
        gpu_name: str,
        gpu_memory_gb: int,
        supported_modes: Sequence[str],
        max_slots: int = 1,
    ) -> "WorkerCapabilities":
        modes = tuple(
            require_identifier(item, "worker supported mode") for item in supported_modes
        )
        if not modes or len(set(modes)) != len(modes):
            raise SchedulerError("worker supported modes must be unique and non-empty")
        slots = _positive_int(max_slots, "worker max slots")
        if slots != 1:
            raise SchedulerError("M7 permits one independent trial per worker")
        return cls(
            worker_id=require_identifier(worker_id, "worker ID"),
            transport=require_identifier(transport, "worker transport"),
            gpu_name=require_nonempty_text(gpu_name, "worker GPU name", max_length=128),
            gpu_memory_gb=_positive_int(
                gpu_memory_gb, "worker GPU memory", allow_zero=True
            ),
            supported_modes=tuple(sorted(modes)),
            max_slots=slots,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "WorkerCapabilities":
        if not isinstance(value, dict) or set(value) != {
            "worker_id",
            "transport",
            "gpu_name",
            "gpu_memory_gb",
            "supported_modes",
            "max_slots",
        }:
            raise SchedulerError("worker capability fields are invalid")
        if not isinstance(value["supported_modes"], list):
            raise SchedulerError("worker supported modes must be a list")
        return cls.create(**value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "transport": self.transport,
            "gpu_name": self.gpu_name,
            "gpu_memory_gb": self.gpu_memory_gb,
            "supported_modes": list(self.supported_modes),
            "max_slots": self.max_slots,
        }


@dataclass(frozen=True)
class WorkerRecord:
    capabilities: WorkerCapabilities
    availability: WorkerAvailability
    registered_at: str
    last_heartbeat_at: str
    active_lease_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Any) -> "WorkerRecord":
        if not isinstance(value, dict) or set(value) != {
            "capabilities",
            "availability",
            "registered_at",
            "last_heartbeat_at",
            "active_lease_ids",
        }:
            raise SchedulerError("worker record fields are invalid")
        registered = value["registered_at"]
        heartbeat = value["last_heartbeat_at"]
        parse_timestamp(registered, "worker registered_at")
        if parse_timestamp(heartbeat, "worker last_heartbeat_at") < parse_timestamp(
            registered, "worker registered_at"
        ):
            raise SchedulerError("worker heartbeat precedes registration")
        leases = value["active_lease_ids"]
        if not isinstance(leases, list):
            raise SchedulerError("worker active leases must be a list")
        normalized = tuple(require_identifier(item, "worker lease ID") for item in leases)
        if len(set(normalized)) != len(normalized):
            raise SchedulerError("worker active leases must be unique")
        return cls(
            capabilities=WorkerCapabilities.from_dict(value["capabilities"]),
            availability=_enum(
                WorkerAvailability, value["availability"], "worker availability"
            ),
            registered_at=registered,
            last_heartbeat_at=heartbeat,
            active_lease_ids=normalized,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": self.capabilities.to_dict(),
            "availability": self.availability.value,
            "registered_at": self.registered_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "active_lease_ids": list(self.active_lease_ids),
        }


@dataclass(frozen=True)
class ScheduledTrial:
    contract: RunContract
    required_mode: str
    required_gpu_memory_gb: int
    priority: int
    enqueued_at: str
    state: DispatchState = DispatchState.QUEUED
    attempt_count: int = 0
    active_lease_id: str | None = None
    evidence: TrialEvidence | None = None
    errors: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        contract: RunContract,
        required_mode: str,
        required_gpu_memory_gb: int,
        priority: int,
        enqueued_at: datetime,
    ) -> "ScheduledTrial":
        if not isinstance(contract, RunContract):
            raise SchedulerError("scheduled trial requires a RunContract")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise SchedulerError("trial priority must be an integer")
        return cls(
            contract=contract,
            required_mode=require_identifier(required_mode, "trial required mode"),
            required_gpu_memory_gb=_positive_int(
                required_gpu_memory_gb,
                "trial required GPU memory",
                allow_zero=True,
            ),
            priority=priority,
            enqueued_at=timestamp_text(enqueued_at),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ScheduledTrial":
        if not isinstance(value, dict) or set(value) != {
            "contract",
            "required_mode",
            "required_gpu_memory_gb",
            "priority",
            "enqueued_at",
            "state",
            "attempt_count",
            "active_lease_id",
            "evidence",
            "errors",
        }:
            raise SchedulerError("scheduled trial fields are invalid")
        contract = RunContract.from_dict(value["contract"])
        created = cls.create(
            contract=contract,
            required_mode=value["required_mode"],
            required_gpu_memory_gb=value["required_gpu_memory_gb"],
            priority=value["priority"],
            enqueued_at=parse_timestamp(value["enqueued_at"], "trial enqueued_at"),
        )
        attempts = _positive_int(
            value["attempt_count"], "trial attempt count", allow_zero=True
        )
        lease = value["active_lease_id"]
        if lease is not None:
            lease = require_identifier(lease, "trial active lease")
        evidence = value["evidence"]
        parsed_evidence = TrialEvidence.from_dict(evidence) if evidence is not None else None
        errors = value["errors"]
        if not isinstance(errors, list) or not all(
            isinstance(item, str) and item for item in errors
        ):
            raise SchedulerError("trial errors must be non-empty strings")
        return replace(
            created,
            state=_enum(DispatchState, value["state"], "trial dispatch state"),
            attempt_count=attempts,
            active_lease_id=lease,
            evidence=parsed_evidence,
            errors=tuple(errors),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "required_mode": self.required_mode,
            "required_gpu_memory_gb": self.required_gpu_memory_gb,
            "priority": self.priority,
            "enqueued_at": self.enqueued_at,
            "state": self.state.value,
            "attempt_count": self.attempt_count,
            "active_lease_id": self.active_lease_id,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class LeaseRecord:
    lease_id: str
    trial_id: str
    worker_id: str
    contract_hash: str
    candidate_commit: str
    attempt: int
    issued_at: str
    expires_at: str
    reserved_wall_time_seconds: int
    reserved_gpu_cost_usd: str
    state: LeaseState = LeaseState.ACTIVE
    closed_at: str | None = None
    completion_hash: str | None = None

    @classmethod
    def create(
        cls,
        *,
        trial: ScheduledTrial,
        worker_id: str,
        attempt: int,
        issued_at: datetime,
        expires_at: datetime,
    ) -> "LeaseRecord":
        issued = timestamp_text(issued_at)
        expires = timestamp_text(expires_at)
        if parse_timestamp(expires, "lease expires_at") <= parse_timestamp(
            issued, "lease issued_at"
        ):
            raise SchedulerError("lease expiration must follow issuance")
        lease_id = require_identifier(
            f"{trial.contract.trial_id}.a{attempt}", "lease ID"
        )
        return cls(
            lease_id=lease_id,
            trial_id=trial.contract.trial_id,
            worker_id=require_identifier(worker_id, "lease worker ID"),
            contract_hash=trial.contract.fingerprint(),
            candidate_commit=trial.contract.candidate_commit,
            attempt=_positive_int(attempt, "lease attempt"),
            issued_at=issued,
            expires_at=expires,
            reserved_wall_time_seconds=trial.contract.max_wall_time_seconds,
            reserved_gpu_cost_usd=trial.contract.max_gpu_cost_usd,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "LeaseRecord":
        if not isinstance(value, dict) or set(value) != {
            "lease_id",
            "trial_id",
            "worker_id",
            "contract_hash",
            "candidate_commit",
            "attempt",
            "issued_at",
            "expires_at",
            "reserved_wall_time_seconds",
            "reserved_gpu_cost_usd",
            "state",
            "closed_at",
            "completion_hash",
        }:
            raise SchedulerError("lease fields are invalid")
        issued = value["issued_at"]
        expires = value["expires_at"]
        if parse_timestamp(expires, "lease expires_at") <= parse_timestamp(
            issued, "lease issued_at"
        ):
            raise SchedulerError("lease expiration must follow issuance")
        closed = value["closed_at"]
        if closed is not None:
            parse_timestamp(closed, "lease closed_at")
        completion = value["completion_hash"]
        if completion is not None:
            completion = require_sha256(completion, "lease completion hash")
        return cls(
            lease_id=require_identifier(value["lease_id"], "lease ID"),
            trial_id=require_identifier(value["trial_id"], "lease trial ID"),
            worker_id=require_identifier(value["worker_id"], "lease worker ID"),
            contract_hash=require_sha256(value["contract_hash"], "lease contract hash"),
            candidate_commit=require_git_commit(
                value["candidate_commit"], "lease candidate commit"
            ),
            attempt=_positive_int(value["attempt"], "lease attempt"),
            issued_at=issued,
            expires_at=expires,
            reserved_wall_time_seconds=_positive_int(
                value["reserved_wall_time_seconds"], "lease wall time"
            ),
            reserved_gpu_cost_usd=decimal_text(
                parse_decimal(
                    value["reserved_gpu_cost_usd"],
                    "lease reserved GPU cost",
                    allow_zero=False,
                )
            ),
            state=_enum(LeaseState, value["state"], "lease state"),
            closed_at=closed,
            completion_hash=completion,
        )

    def authorization_token(self) -> str:
        return fingerprint(
            {
                "lease_id": self.lease_id,
                "trial_id": self.trial_id,
                "worker_id": self.worker_id,
                "contract_hash": self.contract_hash,
                "candidate_commit": self.candidate_commit,
                "attempt": self.attempt,
                "issued_at": self.issued_at,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "trial_id": self.trial_id,
            "worker_id": self.worker_id,
            "contract_hash": self.contract_hash,
            "candidate_commit": self.candidate_commit,
            "attempt": self.attempt,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "reserved_wall_time_seconds": self.reserved_wall_time_seconds,
            "reserved_gpu_cost_usd": self.reserved_gpu_cost_usd,
            "state": self.state.value,
            "closed_at": self.closed_at,
            "completion_hash": self.completion_hash,
        }


@dataclass(frozen=True)
class Assignment:
    lease: LeaseRecord
    contract: RunContract

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease": self.lease.to_dict(),
            "lease_token": self.lease.authorization_token(),
            "contract": self.contract.to_dict(),
        }


@dataclass(frozen=True)
class CompletionEnvelope:
    lease_id: str
    lease_token: str
    worker_id: str
    trial_id: str
    contract_hash: str
    terminal_state: WorkerState
    snapshot: WorkerSnapshot | None
    evidence: TrialEvidence | None
    error: str | None = None

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "lease_token": self.lease_token,
            "worker_id": self.worker_id,
            "trial_id": self.trial_id,
            "contract_hash": self.contract_hash,
            "terminal_state": self.terminal_state.value,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class DispatchResult:
    assignments: tuple[Assignment, ...]
    blocked: tuple[str, ...]
    state_hash: str


@dataclass(frozen=True)
class ReconcileResult:
    trial_id: str
    state: DispatchState
    accepted: bool
    requeued: bool
    evidence_hash: str | None


@dataclass(frozen=True)
class RecoveryResult:
    renewed_lease_ids: tuple[str, ...]
    reconciled: tuple[ReconcileResult, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class SchedulerState:
    campaign_id: str
    campaign_hash: str
    max_concurrency: int
    max_attempts: int
    generation: int
    workers: tuple[WorkerRecord, ...]
    trials: tuple[ScheduledTrial, ...]
    leases: tuple[LeaseRecord, ...]

    @classmethod
    def empty(cls, campaign: CampaignSpec, max_attempts: int) -> "SchedulerState":
        return cls(
            campaign_id=campaign.campaign_id,
            campaign_hash=campaign.fingerprint(),
            max_concurrency=campaign.max_concurrency,
            max_attempts=_positive_int(max_attempts, "scheduler max attempts"),
            generation=0,
            workers=(),
            trials=(),
            leases=(),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "SchedulerState":
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "scheduler_version",
            "campaign_id",
            "campaign_hash",
            "max_concurrency",
            "max_attempts",
            "generation",
            "workers",
            "trials",
            "leases",
        }:
            raise SchedulerError("scheduler state fields are invalid")
        if value["schema_version"] != SCHEMA_VERSION:
            raise SchedulerError("scheduler state schema version is unsupported")
        if value["scheduler_version"] != SCHEDULER_VERSION:
            raise SchedulerError("scheduler state version is unsupported")
        for field in ("workers", "trials", "leases"):
            if not isinstance(value[field], list):
                raise SchedulerError(f"scheduler {field} must be a list")
        state = cls(
            campaign_id=require_identifier(value["campaign_id"], "scheduler campaign"),
            campaign_hash=require_sha256(value["campaign_hash"], "campaign hash"),
            max_concurrency=_positive_int(
                value["max_concurrency"], "scheduler max concurrency"
            ),
            max_attempts=_positive_int(value["max_attempts"], "scheduler max attempts"),
            generation=_positive_int(
                value["generation"], "scheduler generation", allow_zero=True
            ),
            workers=tuple(WorkerRecord.from_dict(item) for item in value["workers"]),
            trials=tuple(ScheduledTrial.from_dict(item) for item in value["trials"]),
            leases=tuple(LeaseRecord.from_dict(item) for item in value["leases"]),
        )
        state.validate()
        return state

    def validate(self) -> None:
        workers = {item.capabilities.worker_id: item for item in self.workers}
        trials = {item.contract.trial_id: item for item in self.trials}
        leases = {item.lease_id: item for item in self.leases}
        if len(workers) != len(self.workers):
            raise SchedulerError("scheduler worker IDs are duplicated")
        if len(trials) != len(self.trials):
            raise SchedulerError("scheduler trial IDs are duplicated")
        if len(leases) != len(self.leases):
            raise SchedulerError("scheduler lease IDs are duplicated")
        active_by_trial: dict[str, str] = {}
        active_by_worker: dict[str, set[str]] = {}
        for lease in self.leases:
            if lease.trial_id not in trials or lease.worker_id not in workers:
                raise SchedulerError("scheduler lease references an unknown entity")
            trial = trials[lease.trial_id]
            if (
                lease.contract_hash != trial.contract.fingerprint()
                or lease.candidate_commit != trial.contract.candidate_commit
                or lease.attempt > trial.attempt_count
            ):
                raise SchedulerError("scheduler lease provenance is inconsistent")
            if lease.state == LeaseState.ACTIVE and (
                lease.closed_at is not None or lease.completion_hash is not None
            ):
                raise SchedulerError("active lease contains terminal fields")
            if lease.state != LeaseState.ACTIVE and lease.closed_at is None:
                raise SchedulerError("closed lease is missing its closure time")
            if lease.closed_at is not None and parse_timestamp(
                lease.closed_at, "lease closed_at"
            ) < parse_timestamp(lease.issued_at, "lease issued_at"):
                raise SchedulerError("lease closes before issuance")
            if lease.state in {LeaseState.COMPLETED, LeaseState.FAILED, LeaseState.LOST}:
                if lease.completion_hash is None:
                    raise SchedulerError("reconciled lease is missing completion hash")
            elif lease.completion_hash is not None:
                raise SchedulerError("unreconciled lease contains a completion hash")
            if lease.state == LeaseState.ACTIVE:
                if lease.trial_id in active_by_trial:
                    raise SchedulerError("trial has multiple active leases")
                active_by_trial[lease.trial_id] = lease.lease_id
                active_by_worker.setdefault(lease.worker_id, set()).add(lease.lease_id)
        if len(active_by_trial) > self.max_concurrency:
            raise SchedulerError("scheduler active leases exceed campaign concurrency")
        for trial in self.trials:
            active = active_by_trial.get(trial.contract.trial_id)
            if trial.active_lease_id != active:
                raise SchedulerError("trial active lease pointer is inconsistent")
            if trial.state == DispatchState.LEASED and active is None:
                raise SchedulerError("leased trial has no active lease")
            if trial.state != DispatchState.LEASED and active is not None:
                raise SchedulerError("non-leased trial has an active lease")
            if trial.state == DispatchState.COMPLETED and trial.evidence is None:
                raise SchedulerError("completed trial is missing evidence")
            if trial.evidence is not None:
                _validate_evidence_contract(trial.evidence, trial.contract)
                if trial.state == DispatchState.COMPLETED and (
                    trial.evidence.status != TrialStatus.COMPLETE
                ):
                    raise SchedulerError("completed scheduler trial has failed evidence")
                if trial.state == DispatchState.FAILED and (
                    trial.evidence.status != TrialStatus.FAILED
                ):
                    raise SchedulerError("failed scheduler trial has complete evidence")
            if trial.state not in {DispatchState.COMPLETED, DispatchState.FAILED} and (
                trial.evidence is not None
            ):
                raise SchedulerError("non-terminal trial contains evidence")
        for worker_id, worker in workers.items():
            expected = active_by_worker.get(worker_id, set())
            if set(worker.active_lease_ids) != expected:
                raise SchedulerError("worker active lease pointers are inconsistent")
            if len(expected) > worker.capabilities.max_slots:
                raise SchedulerError("worker active leases exceed its slot cap")
            if expected and worker.availability != WorkerAvailability.BUSY:
                raise SchedulerError("worker with active lease is not busy")
            if not expected and worker.availability == WorkerAvailability.BUSY:
                raise SchedulerError("busy worker has no active lease")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "scheduler_version": SCHEDULER_VERSION,
            "campaign_id": self.campaign_id,
            "campaign_hash": self.campaign_hash,
            "max_concurrency": self.max_concurrency,
            "max_attempts": self.max_attempts,
            "generation": self.generation,
            "workers": [
                item.to_dict()
                for item in sorted(
                    self.workers, key=lambda item: item.capabilities.worker_id
                )
            ],
            "trials": [
                item.to_dict()
                for item in sorted(self.trials, key=lambda item: item.contract.trial_id)
            ],
            "leases": [
                item.to_dict() for item in sorted(self.leases, key=lambda item: item.lease_id)
            ],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


class SchedulerStateStore:
    """Atomic, hash-checked scheduler snapshot with process and thread locking."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._thread_lock = threading.RLock()

    def initialize(self, campaign: CampaignSpec, *, max_attempts: int) -> SchedulerState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock, self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if self.path.exists():
                state = self._read_unlocked()
            else:
                state = SchedulerState.empty(campaign, max_attempts)
                self._write_unlocked(state)
            self._validate_campaign(state, campaign, max_attempts)
            return state

    def read(self) -> SchedulerState:
        with self._thread_lock, self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            return self._read_unlocked()

    def mutate(
        self, operation: Callable[[SchedulerState], tuple[SchedulerState, Any]]
    ) -> tuple[SchedulerState, Any]:
        with self._thread_lock, self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            current = self._read_unlocked()
            updated, result = operation(current)
            if not isinstance(updated, SchedulerState):
                raise SchedulerError("scheduler mutation returned invalid state")
            if updated == current:
                return current, result
            updated = replace(updated, generation=current.generation + 1)
            updated.validate()
            self._write_unlocked(updated)
            return updated, result

    @staticmethod
    def _validate_campaign(
        state: SchedulerState, campaign: CampaignSpec, max_attempts: int
    ) -> None:
        if (
            state.campaign_id != campaign.campaign_id
            or state.campaign_hash != campaign.fingerprint()
            or state.max_concurrency != campaign.max_concurrency
            or state.max_attempts != max_attempts
        ):
            raise SchedulerError("scheduler state does not match the exact campaign")

    def _read_unlocked(self) -> SchedulerState:
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SchedulerError("scheduler state is unreadable") from error
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "payload_hash"}:
            raise SchedulerError("scheduler state envelope is invalid")
        if require_sha256(envelope["payload_hash"], "scheduler payload hash") != fingerprint(
            envelope["payload"]
        ):
            raise SchedulerError("scheduler state hash mismatch")
        return SchedulerState.from_dict(envelope["payload"])

    def _write_unlocked(self, state: SchedulerState) -> None:
        payload = state.to_dict()
        content = canonical_json(
            {"payload": payload, "payload_hash": fingerprint(payload)}
        ) + "\n"
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()


class DurableScheduler:
    """Deterministic lease authority; workers can execute but cannot self-promote."""

    def __init__(
        self,
        *,
        campaign: CampaignSpec,
        store: SchedulerStateStore,
        max_attempts: int = 2,
    ) -> None:
        self.campaign = campaign
        self.store = store
        self.max_attempts = _positive_int(max_attempts, "scheduler max attempts")
        self.store.initialize(campaign, max_attempts=max_attempts)

    def snapshot(self) -> SchedulerState:
        state = self.store.read()
        SchedulerStateStore._validate_campaign(
            state, self.campaign, self.max_attempts
        )
        return state

    def register_worker(
        self, capabilities: WorkerCapabilities, *, at: datetime
    ) -> WorkerRecord:
        moment = timestamp_text(at)

        def operation(state: SchedulerState) -> tuple[SchedulerState, WorkerRecord]:
            workers = {item.capabilities.worker_id: item for item in state.workers}
            existing = workers.get(capabilities.worker_id)
            if existing is not None:
                if existing.capabilities != capabilities:
                    raise SchedulerError("worker ID is bound to different capabilities")
                updated = replace(existing, last_heartbeat_at=moment)
            else:
                updated = WorkerRecord(
                    capabilities=capabilities,
                    availability=WorkerAvailability.READY,
                    registered_at=moment,
                    last_heartbeat_at=moment,
                )
            workers[capabilities.worker_id] = updated
            return replace(state, workers=tuple(workers.values())), updated

        return self.store.mutate(operation)[1]

    def heartbeat_worker(self, worker_id: str, *, at: datetime) -> WorkerRecord:
        identity = require_identifier(worker_id, "worker ID")
        moment = timestamp_text(at)

        def operation(state: SchedulerState) -> tuple[SchedulerState, WorkerRecord]:
            workers = {item.capabilities.worker_id: item for item in state.workers}
            if identity not in workers:
                raise SchedulerError("heartbeat references an unknown worker")
            current = workers[identity]
            availability = current.availability
            if availability == WorkerAvailability.OFFLINE and not current.active_lease_ids:
                availability = WorkerAvailability.READY
            updated = replace(
                current, availability=availability, last_heartbeat_at=moment
            )
            workers[identity] = updated
            return replace(state, workers=tuple(workers.values())), updated

        return self.store.mutate(operation)[1]

    def enqueue(
        self,
        contract: RunContract,
        *,
        required_mode: str,
        required_gpu_memory_gb: int,
        at: datetime,
        priority: int = 0,
    ) -> ScheduledTrial:
        if contract.campaign_id != self.campaign.campaign_id:
            raise SchedulerError("run contract campaign does not match scheduler")
        proposed = ScheduledTrial.create(
            contract=contract,
            required_mode=required_mode,
            required_gpu_memory_gb=required_gpu_memory_gb,
            priority=priority,
            enqueued_at=at,
        )

        def operation(state: SchedulerState) -> tuple[SchedulerState, ScheduledTrial]:
            trials = {item.contract.trial_id: item for item in state.trials}
            existing = trials.get(contract.trial_id)
            if existing is not None:
                if existing.contract.fingerprint() != contract.fingerprint():
                    raise SchedulerError("trial ID is bound to a different run contract")
                return state, existing
            trials[contract.trial_id] = proposed
            return replace(state, trials=tuple(trials.values())), proposed

        return self.store.mutate(operation)[1]

    def dispatch(self, *, at: datetime, lease_ttl_seconds: int) -> DispatchResult:
        ttl = _positive_int(lease_ttl_seconds, "lease TTL")
        moment = parse_timestamp(timestamp_text(at), "dispatch time")

        def operation(state: SchedulerState) -> tuple[SchedulerState, DispatchResult]:
            state = self._expire_state(state, moment)
            workers = {item.capabilities.worker_id: item for item in state.workers}
            trials = {item.contract.trial_id: item for item in state.trials}
            leases = list(state.leases)
            assignments: list[Assignment] = []
            blocked: list[str] = []
            active_count = sum(item.state == LeaseState.ACTIVE for item in leases)
            queued = sorted(
                (item for item in trials.values() if item.state == DispatchState.QUEUED),
                key=lambda item: (-item.priority, item.enqueued_at, item.contract.trial_id),
            )
            for trial in queued:
                if active_count >= state.max_concurrency:
                    blocked.append(f"{trial.contract.trial_id}: concurrency cap")
                    continue
                budget_error = self._budget_error(leases, trial.contract)
                if budget_error:
                    blocked.append(f"{trial.contract.trial_id}: {budget_error}")
                    continue
                compatible = [
                    worker
                    for worker in workers.values()
                    if worker.availability
                    in {WorkerAvailability.READY, WorkerAvailability.BUSY}
                    and len(worker.active_lease_ids) < worker.capabilities.max_slots
                    and trial.required_mode in worker.capabilities.supported_modes
                    and worker.capabilities.gpu_memory_gb
                    >= trial.required_gpu_memory_gb
                ]
                if not compatible:
                    blocked.append(f"{trial.contract.trial_id}: no compatible worker")
                    continue
                worker = sorted(
                    compatible, key=lambda item: item.capabilities.worker_id
                )[0]
                attempt = trial.attempt_count + 1
                lease = LeaseRecord.create(
                    trial=trial,
                    worker_id=worker.capabilities.worker_id,
                    attempt=attempt,
                    issued_at=moment,
                    expires_at=moment + timedelta(seconds=ttl),
                )
                active_ids = tuple(sorted((*worker.active_lease_ids, lease.lease_id)))
                workers[worker.capabilities.worker_id] = replace(
                    worker,
                    availability=WorkerAvailability.BUSY,
                    active_lease_ids=active_ids,
                )
                trials[trial.contract.trial_id] = replace(
                    trial,
                    state=DispatchState.LEASED,
                    attempt_count=attempt,
                    active_lease_id=lease.lease_id,
                )
                leases.append(lease)
                assignments.append(Assignment(lease=lease, contract=trial.contract))
                active_count += 1
            updated = replace(
                state,
                workers=tuple(workers.values()),
                trials=tuple(trials.values()),
                leases=tuple(leases),
            )
            preview = (
                state
                if updated == state
                else replace(updated, generation=state.generation + 1)
            )
            result = DispatchResult(
                assignments=tuple(assignments),
                blocked=tuple(blocked),
                state_hash=preview.fingerprint(),
            )
            return updated, result

        return self.store.mutate(operation)[1]

    def renew(
        self,
        *,
        lease_id: str,
        lease_token: str,
        worker_id: str,
        at: datetime,
        lease_ttl_seconds: int,
    ) -> LeaseRecord:
        identity = require_identifier(worker_id, "worker ID")
        token = require_sha256(lease_token, "lease token")
        target = require_identifier(lease_id, "lease ID")
        moment = parse_timestamp(timestamp_text(at), "lease heartbeat time")
        ttl = _positive_int(lease_ttl_seconds, "lease TTL")

        def operation(state: SchedulerState) -> tuple[SchedulerState, LeaseRecord]:
            leases = {item.lease_id: item for item in state.leases}
            lease = leases.get(target)
            if lease is None or lease.worker_id != identity:
                raise SchedulerError("lease heartbeat identity mismatch")
            if lease.authorization_token() != token or lease.state != LeaseState.ACTIVE:
                raise SchedulerError("lease heartbeat is stale")
            if moment < parse_timestamp(lease.issued_at, "lease issued_at"):
                raise SchedulerError("lease heartbeat precedes issuance")
            if moment >= parse_timestamp(lease.expires_at, "lease expires_at"):
                raise SchedulerError("lease already expired")
            updated = replace(
                lease, expires_at=timestamp_text(moment + timedelta(seconds=ttl))
            )
            leases[target] = updated
            workers = {item.capabilities.worker_id: item for item in state.workers}
            workers[identity] = replace(
                workers[identity], last_heartbeat_at=timestamp_text(moment)
            )
            return (
                replace(
                    state,
                    workers=tuple(workers.values()),
                    leases=tuple(leases.values()),
                ),
                updated,
            )

        return self.store.mutate(operation)[1]

    def expire_leases(self, *, at: datetime) -> tuple[str, ...]:
        moment = parse_timestamp(timestamp_text(at), "lease expiration time")

        def operation(state: SchedulerState) -> tuple[SchedulerState, tuple[str, ...]]:
            expired = tuple(
                item.lease_id
                for item in state.leases
                if item.state == LeaseState.ACTIVE
                and moment >= parse_timestamp(item.expires_at, "lease expires_at")
            )
            return self._expire_state(state, moment), expired

        return self.store.mutate(operation)[1]

    def reconcile(
        self, completion: CompletionEnvelope, *, at: datetime
    ) -> ReconcileResult:
        if not isinstance(completion, CompletionEnvelope):
            raise SchedulerError("completion envelope type is invalid")
        moment = parse_timestamp(timestamp_text(at), "completion time")

        def operation(state: SchedulerState) -> tuple[SchedulerState, ReconcileResult]:
            leases = {item.lease_id: item for item in state.leases}
            trials = {item.contract.trial_id: item for item in state.trials}
            workers = {item.capabilities.worker_id: item for item in state.workers}
            lease = leases.get(completion.lease_id)
            if lease is None:
                raise SchedulerError("completion references an unknown lease")
            if lease.authorization_token() != completion.lease_token:
                raise SchedulerError("completion lease token mismatch")
            if lease.state != LeaseState.ACTIVE:
                if (
                    lease.state in {LeaseState.COMPLETED, LeaseState.FAILED}
                    and lease.completion_hash == completion.fingerprint()
                ):
                    trial = trials[lease.trial_id]
                    return state, ReconcileResult(
                        trial_id=trial.contract.trial_id,
                        state=trial.state,
                        accepted=True,
                        requeued=False,
                        evidence_hash=(
                            trial.evidence.fingerprint() if trial.evidence else None
                        ),
                    )
                raise SchedulerError("completion uses a stale lease")
            if moment >= parse_timestamp(lease.expires_at, "lease expires_at"):
                raise SchedulerError("completion arrived after lease expiration")
            if moment < parse_timestamp(lease.issued_at, "lease issued_at"):
                raise SchedulerError("completion precedes lease issuance")
            if (
                completion.worker_id != lease.worker_id
                or completion.trial_id != lease.trial_id
                or completion.contract_hash != lease.contract_hash
            ):
                raise SchedulerError("completion identity does not match lease")
            trial = trials[lease.trial_id]
            if trial.active_lease_id != lease.lease_id:
                raise SchedulerError("completion lease is not the trial authority")
            self._validate_completion(completion, trial.contract)
            if completion.error is not None and (
                not isinstance(completion.error, str) or not completion.error
            ):
                raise SchedulerError("completion error must be non-empty text")
            evidence_hash = (
                completion.evidence.fingerprint() if completion.evidence else None
            )
            requeued = False
            if completion.terminal_state == WorkerState.COMPLETED:
                lease_state = LeaseState.COMPLETED
                trial_state = DispatchState.COMPLETED
                evidence = completion.evidence
            elif completion.terminal_state == WorkerState.FAILED:
                lease_state = LeaseState.FAILED
                trial_state = DispatchState.FAILED
                evidence = completion.evidence
            elif completion.terminal_state == WorkerState.LOST:
                lease_state = LeaseState.LOST
                evidence = None
                requeued = trial.attempt_count < state.max_attempts
                trial_state = DispatchState.QUEUED if requeued else DispatchState.FAILED
            elif completion.terminal_state == WorkerState.CANCELLED:
                lease_state = LeaseState.CANCELLED
                evidence = None
                trial_state = DispatchState.CANCELLED
            else:
                raise SchedulerError("completion is not terminal")
            error_items = trial.errors
            if completion.error:
                error_items = (*error_items, completion.error)
            trials[trial.contract.trial_id] = replace(
                trial,
                state=trial_state,
                active_lease_id=None,
                evidence=evidence,
                errors=error_items,
            )
            leases[lease.lease_id] = replace(
                lease,
                state=lease_state,
                closed_at=timestamp_text(moment),
                completion_hash=completion.fingerprint(),
            )
            worker = workers[lease.worker_id]
            remaining = tuple(
                item for item in worker.active_lease_ids if item != lease.lease_id
            )
            availability = (
                WorkerAvailability.OFFLINE
                if completion.terminal_state == WorkerState.LOST
                else WorkerAvailability.READY
            )
            if remaining and availability != WorkerAvailability.OFFLINE:
                availability = WorkerAvailability.BUSY
            workers[lease.worker_id] = replace(
                worker, availability=availability, active_lease_ids=remaining
            )
            updated = replace(
                state,
                workers=tuple(workers.values()),
                trials=tuple(trials.values()),
                leases=tuple(leases.values()),
            )
            return updated, ReconcileResult(
                trial_id=trial.contract.trial_id,
                state=trial_state,
                accepted=True,
                requeued=requeued,
                evidence_hash=evidence_hash,
            )

        return self.store.mutate(operation)[1]

    def cancel_trial(self, trial_id: str, *, at: datetime) -> Assignment | None:
        target = require_identifier(trial_id, "trial ID")
        moment = timestamp_text(at)

        def operation(state: SchedulerState) -> tuple[SchedulerState, Assignment | None]:
            trials = {item.contract.trial_id: item for item in state.trials}
            if target not in trials:
                raise SchedulerError("cancellation references an unknown trial")
            trial = trials[target]
            if trial.state in {
                DispatchState.COMPLETED,
                DispatchState.FAILED,
                DispatchState.CANCELLED,
            }:
                return state, None
            leases = {item.lease_id: item for item in state.leases}
            workers = {item.capabilities.worker_id: item for item in state.workers}
            order = None
            if trial.active_lease_id is not None:
                lease = leases[trial.active_lease_id]
                if parse_timestamp(moment, "cancellation time") < parse_timestamp(
                    lease.issued_at, "lease issued_at"
                ):
                    raise SchedulerError("cancellation precedes lease issuance")
                order = Assignment(lease=lease, contract=trial.contract)
                leases[lease.lease_id] = replace(
                    lease,
                    state=LeaseState.CANCELLED,
                    closed_at=moment,
                )
                worker = workers[lease.worker_id]
                remaining = tuple(
                    item for item in worker.active_lease_ids if item != lease.lease_id
                )
                workers[lease.worker_id] = replace(
                    worker,
                    availability=(
                        WorkerAvailability.BUSY
                        if remaining
                        else WorkerAvailability.READY
                    ),
                    active_lease_ids=remaining,
                )
            trials[target] = replace(
                trial,
                state=DispatchState.CANCELLED,
                active_lease_id=None,
                errors=(*trial.errors, "cancelled by coordinator"),
            )
            return (
                replace(
                    state,
                    workers=tuple(workers.values()),
                    trials=tuple(trials.values()),
                    leases=tuple(leases.values()),
                ),
                order,
            )

        return self.store.mutate(operation)[1]

    def active_assignments(self) -> tuple[Assignment, ...]:
        state = self.snapshot()
        trials = {item.contract.trial_id: item for item in state.trials}
        return tuple(
            Assignment(lease=lease, contract=trials[lease.trial_id].contract)
            for lease in state.leases
            if lease.state == LeaseState.ACTIVE
        )

    def _budget_error(
        self, leases: Sequence[LeaseRecord], contract: RunContract
    ) -> str | None:
        cap = self.campaign.budget
        if len(leases) + 1 > cap.max_trials:
            return "trial budget exhausted"
        wall = sum(item.reserved_wall_time_seconds for item in leases)
        if wall + contract.max_wall_time_seconds > cap.max_wall_time_seconds:
            return "wall-time budget exhausted"
        gpu = sum(
            (
                parse_decimal(item.reserved_gpu_cost_usd, "reserved GPU cost")
                for item in leases
            ),
            Decimal(0),
        )
        if gpu + parse_decimal(
            contract.max_gpu_cost_usd, "contract GPU cost"
        ) > cap.gpu_cost():
            return "GPU budget exhausted"
        return None

    @staticmethod
    def _validate_completion(
        completion: CompletionEnvelope, contract: RunContract
    ) -> None:
        snapshot = completion.snapshot
        if completion.terminal_state == WorkerState.LOST:
            if completion.evidence is not None:
                raise SchedulerError("lost worker may not return evidence")
            return
        if snapshot is None:
            raise SchedulerError("terminal completion is missing worker snapshot")
        if (
            snapshot.worker_id != completion.worker_id
            or snapshot.trial_id != contract.trial_id
            or snapshot.contract_hash != contract.fingerprint()
            or snapshot.state != completion.terminal_state
        ):
            raise SchedulerError("worker snapshot does not match completion")
        if completion.terminal_state in {WorkerState.COMPLETED, WorkerState.FAILED}:
            evidence = completion.evidence
            if evidence is None or snapshot.evidence_hash != evidence.fingerprint():
                raise SchedulerError("completion evidence hash is invalid")
            expected_status = (
                TrialStatus.COMPLETE
                if completion.terminal_state == WorkerState.COMPLETED
                else TrialStatus.FAILED
            )
            if evidence.status != expected_status:
                raise SchedulerError("completion evidence terminal status mismatch")
            _validate_evidence_contract(evidence, contract)
        elif completion.evidence is not None:
            raise SchedulerError("cancelled completion may not return evidence")

    def _expire_state(self, state: SchedulerState, at: datetime) -> SchedulerState:
        workers = {item.capabilities.worker_id: item for item in state.workers}
        trials = {item.contract.trial_id: item for item in state.trials}
        leases: list[LeaseRecord] = []
        for lease in state.leases:
            if lease.state != LeaseState.ACTIVE or at < parse_timestamp(
                lease.expires_at, "lease expires_at"
            ):
                leases.append(lease)
                continue
            trial = trials[lease.trial_id]
            requeue = trial.attempt_count < state.max_attempts
            trials[lease.trial_id] = replace(
                trial,
                state=DispatchState.QUEUED if requeue else DispatchState.FAILED,
                active_lease_id=None,
                errors=(*trial.errors, f"lease {lease.lease_id} expired"),
            )
            worker = workers[lease.worker_id]
            workers[lease.worker_id] = replace(
                worker,
                availability=WorkerAvailability.OFFLINE,
                active_lease_ids=tuple(
                    item for item in worker.active_lease_ids if item != lease.lease_id
                ),
            )
            leases.append(
                replace(
                    lease,
                    state=LeaseState.EXPIRED,
                    closed_at=timestamp_text(at),
                )
            )
        return replace(
            state,
            workers=tuple(workers.values()),
            trials=tuple(trials.values()),
            leases=tuple(leases),
        )


def execute_assignments(
    assignments: Sequence[Assignment],
    *,
    workers: Mapping[str, ExperimentWorker],
    max_workers: int,
) -> tuple[CompletionEnvelope, ...]:
    """Execute independent leases concurrently; do not evaluate or promote them."""

    limit = _positive_int(max_workers, "dispatcher max workers")
    if len({item.lease.lease_id for item in assignments}) != len(assignments):
        raise SchedulerError("dispatcher assignments contain duplicate leases")

    def execute(assignment: Assignment) -> CompletionEnvelope:
        lease = assignment.lease
        contract = assignment.contract
        worker = workers.get(lease.worker_id)
        if worker is None or worker.worker_id != lease.worker_id:
            return CompletionEnvelope(
                lease_id=lease.lease_id,
                lease_token=lease.authorization_token(),
                worker_id=lease.worker_id,
                trial_id=lease.trial_id,
                contract_hash=lease.contract_hash,
                terminal_state=WorkerState.LOST,
                snapshot=None,
                evidence=None,
                error="assigned worker transport is unavailable",
            )
        try:
            prepared = worker.prepare(contract)
            _validate_snapshot(prepared, worker.worker_id, contract, {WorkerState.PREPARED})
            heartbeat = worker.heartbeat(contract.trial_id)
            _validate_snapshot(
                heartbeat, worker.worker_id, contract, {WorkerState.PREPARED}
            )
            terminal = worker.launch(contract.trial_id)
            _validate_snapshot(
                terminal,
                worker.worker_id,
                contract,
                {
                    WorkerState.COMPLETED,
                    WorkerState.FAILED,
                    WorkerState.CANCELLED,
                    WorkerState.LOST,
                },
            )
            evidence = None
            if terminal.state in {WorkerState.COMPLETED, WorkerState.FAILED}:
                evidence = worker.fetch_evidence(contract.trial_id)
            return CompletionEnvelope(
                lease_id=lease.lease_id,
                lease_token=lease.authorization_token(),
                worker_id=worker.worker_id,
                trial_id=contract.trial_id,
                contract_hash=contract.fingerprint(),
                terminal_state=terminal.state,
                snapshot=terminal,
                evidence=evidence,
            )
        except Exception as error:  # transport loss becomes non-promotable evidence
            return CompletionEnvelope(
                lease_id=lease.lease_id,
                lease_token=lease.authorization_token(),
                worker_id=lease.worker_id,
                trial_id=lease.trial_id,
                contract_hash=lease.contract_hash,
                terminal_state=WorkerState.LOST,
                snapshot=None,
                evidence=None,
                error=f"{type(error).__name__}: {error}",
            )

    if not assignments:
        return ()
    with ThreadPoolExecutor(max_workers=min(limit, len(assignments))) as executor:
        futures = [executor.submit(execute, item) for item in assignments]
        completed = [future.result() for future in as_completed(futures)]
    return tuple(sorted(completed, key=lambda item: item.trial_id))


def cancel_assignment(
    assignment: Assignment, *, workers: Mapping[str, ExperimentWorker]
) -> WorkerSnapshot | None:
    """Best-effort transport cancellation after durable authority is revoked."""

    worker = workers.get(assignment.lease.worker_id)
    if worker is None:
        return None
    snapshot = worker.cancel(assignment.contract.trial_id)
    _validate_snapshot(
        snapshot,
        assignment.lease.worker_id,
        assignment.contract,
        {
            WorkerState.CANCELLED,
            WorkerState.COMPLETED,
            WorkerState.FAILED,
            WorkerState.LOST,
        },
    )
    return snapshot


def recover_active_assignments(
    scheduler: DurableScheduler,
    *,
    workers: Mapping[str, ExperimentWorker],
    at: datetime,
    lease_ttl_seconds: int,
) -> RecoveryResult:
    """Poll durable leases after restart, renew live work, and reconcile terminals."""

    if not isinstance(scheduler, DurableScheduler):
        raise SchedulerError("recovery requires a DurableScheduler")
    renewed: list[str] = []
    reconciled: list[ReconcileResult] = []
    errors: list[str] = []
    for assignment in scheduler.active_assignments():
        lease = assignment.lease
        contract = assignment.contract
        worker = workers.get(lease.worker_id)
        completion: CompletionEnvelope | None = None
        if worker is None or worker.worker_id != lease.worker_id:
            completion = CompletionEnvelope(
                lease_id=lease.lease_id,
                lease_token=lease.authorization_token(),
                worker_id=lease.worker_id,
                trial_id=lease.trial_id,
                contract_hash=lease.contract_hash,
                terminal_state=WorkerState.LOST,
                snapshot=None,
                evidence=None,
                error="worker transport was unavailable during recovery",
            )
        else:
            try:
                snapshot = worker.status(contract.trial_id)
                _validate_snapshot(
                    snapshot,
                    worker.worker_id,
                    contract,
                    {
                        WorkerState.PREPARED,
                        WorkerState.RUNNING,
                        WorkerState.COMPLETED,
                        WorkerState.FAILED,
                        WorkerState.CANCELLED,
                        WorkerState.LOST,
                    },
                )
                if snapshot.state in {WorkerState.PREPARED, WorkerState.RUNNING}:
                    heartbeat = worker.heartbeat(contract.trial_id)
                    _validate_snapshot(
                        heartbeat,
                        worker.worker_id,
                        contract,
                        {
                            WorkerState.PREPARED,
                            WorkerState.RUNNING,
                            WorkerState.COMPLETED,
                            WorkerState.FAILED,
                            WorkerState.CANCELLED,
                            WorkerState.LOST,
                        },
                    )
                    snapshot = heartbeat
                if snapshot.state in {WorkerState.PREPARED, WorkerState.RUNNING}:
                    scheduler.renew(
                        lease_id=lease.lease_id,
                        lease_token=lease.authorization_token(),
                        worker_id=lease.worker_id,
                        at=at,
                        lease_ttl_seconds=lease_ttl_seconds,
                    )
                    renewed.append(lease.lease_id)
                    continue
                evidence = None
                if snapshot.state in {WorkerState.COMPLETED, WorkerState.FAILED}:
                    evidence = worker.fetch_evidence(contract.trial_id)
                completion = CompletionEnvelope(
                    lease_id=lease.lease_id,
                    lease_token=lease.authorization_token(),
                    worker_id=lease.worker_id,
                    trial_id=lease.trial_id,
                    contract_hash=lease.contract_hash,
                    terminal_state=snapshot.state,
                    snapshot=snapshot,
                    evidence=evidence,
                )
            except Exception as error:  # recovery cannot trust an invalid transport
                completion = CompletionEnvelope(
                    lease_id=lease.lease_id,
                    lease_token=lease.authorization_token(),
                    worker_id=lease.worker_id,
                    trial_id=lease.trial_id,
                    contract_hash=lease.contract_hash,
                    terminal_state=WorkerState.LOST,
                    snapshot=None,
                    evidence=None,
                    error=f"recovery {type(error).__name__}: {error}",
                )
        try:
            reconciled.append(scheduler.reconcile(completion, at=at))
        except SchedulerError as error:
            errors.append(f"{lease.trial_id}: {error}")
    return RecoveryResult(
        renewed_lease_ids=tuple(sorted(renewed)),
        reconciled=tuple(sorted(reconciled, key=lambda item: item.trial_id)),
        errors=tuple(errors),
    )


def _validate_snapshot(
    snapshot: WorkerSnapshot,
    worker_id: str,
    contract: RunContract,
    states: set[WorkerState],
) -> None:
    if not isinstance(snapshot, WorkerSnapshot):
        raise SchedulerError("worker returned an invalid snapshot type")
    if (
        snapshot.worker_id != worker_id
        or snapshot.trial_id != contract.trial_id
        or snapshot.contract_hash != contract.fingerprint()
        or snapshot.state not in states
    ):
        raise SchedulerError("worker snapshot violates its assignment")


def _validate_evidence_contract(
    evidence: TrialEvidence, contract: RunContract
) -> None:
    if not isinstance(evidence, TrialEvidence):
        raise SchedulerError("completion evidence type is invalid")
    expected = {
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
    }
    for name, value in expected.items():
        if getattr(evidence, name) != value:
            raise SchedulerError(f"completion evidence {name} mismatch")
    if evidence.elapsed_seconds > contract.max_wall_time_seconds:
        raise SchedulerError("completion evidence exceeds wall-time cap")
    if parse_decimal(
        evidence.gpu_cost_usd, "completion GPU cost"
    ) > parse_decimal(contract.max_gpu_cost_usd, "contract GPU cost"):
        raise SchedulerError("completion evidence exceeds GPU-cost cap")
