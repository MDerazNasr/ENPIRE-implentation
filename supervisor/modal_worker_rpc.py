"""Strict Modal transport for the fixed M7 experiment-worker RPC."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from supervisor.canonical import (
    canonical_json,
    fingerprint,
    require_exact_keys,
    require_identifier,
    require_nonempty_text,
    require_sha256,
)
from supervisor.contracts import ArtifactRef, TrialEvidence
from supervisor.workers import ExperimentWorker, RunContract, WorkerError, WorkerSnapshot


MAX_RPC_OUTPUT_BYTES = 1_048_576
MAX_ARTIFACT_BYTES = 8_388_608
ARTIFACT_CHUNK_BYTES = 262_144
F1_APP_NAME = "enpire-f1-worker-rpc-v1"
F1_FUNCTION_NAME = "rpc"


class ModalWorkerRpcError(WorkerError):
    """Raised when the fixed Modal worker protocol is violated."""


@dataclass(frozen=True)
class WorkerRpcRequest:
    request_id: str
    worker_id: str
    runtime_contract_id: str
    runtime_contract_sha256: str
    action: str
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        runtime_contract_id: str,
        runtime_contract_sha256: str,
        action: str,
        payload: dict[str, Any],
    ) -> "WorkerRpcRequest":
        operation = require_identifier(action, "worker RPC action")
        if operation not in {
            "prepare",
            "launch",
            "status",
            "heartbeat",
            "cancel",
            "fetch_evidence",
            "fetch_artifact",
        }:
            raise ModalWorkerRpcError("worker RPC action is not allowlisted")
        if not isinstance(payload, dict):
            raise ModalWorkerRpcError("worker RPC payload must be an object")
        partial = {
            "schema_version": 1,
            "worker_id": require_identifier(worker_id, "worker RPC worker ID"),
            "runtime_contract_id": require_identifier(
                runtime_contract_id, "worker RPC runtime contract ID"
            ),
            "runtime_contract_sha256": require_sha256(
                runtime_contract_sha256, "worker RPC runtime contract hash"
            ),
            "action": operation,
            "payload": payload,
        }
        return cls(
            request_id=fingerprint(partial),
            worker_id=partial["worker_id"],
            runtime_contract_id=partial["runtime_contract_id"],
            runtime_contract_sha256=partial["runtime_contract_sha256"],
            action=operation,
            payload=payload,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "WorkerRpcRequest":
        data = require_exact_keys(
            value,
            "worker RPC request",
            {
                "schema_version",
                "request_id",
                "worker_id",
                "runtime_contract_id",
                "runtime_contract_sha256",
                "action",
                "payload",
            },
        )
        if data["schema_version"] != 1:
            raise ModalWorkerRpcError("worker RPC schema_version must be 1")
        request = cls.create(
            worker_id=data["worker_id"],
            runtime_contract_id=data["runtime_contract_id"],
            runtime_contract_sha256=data["runtime_contract_sha256"],
            action=data["action"],
            payload=data["payload"],
        )
        if data["request_id"] != request.request_id:
            raise ModalWorkerRpcError("worker RPC request hash mismatch")
        return request

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "request_id": self.request_id,
            "worker_id": self.worker_id,
            "runtime_contract_id": self.runtime_contract_id,
            "runtime_contract_sha256": self.runtime_contract_sha256,
            "action": self.action,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class ModalRpcResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise ModalWorkerRpcError("Modal RPC return code must be an integer")
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise ModalWorkerRpcError("Modal RPC output must be bytes")


class ModalRpcExecutor(Protocol):
    def run(self, request: WorkerRpcRequest, *, timeout_seconds: int) -> ModalRpcResult: ...


@dataclass(frozen=True)
class FixedModalRpcExecutor:
    """Invoke only the harness-owned client script with one canonical payload."""

    python_executable: Path
    client_script: Path
    expected_profile: str

    @classmethod
    def create(
        cls,
        *,
        python_executable: Path,
        client_script: Path,
        expected_profile: str,
    ) -> "FixedModalRpcExecutor":
        # Preserve virtual-environment interpreter symlinks. Resolving a Homebrew
        # venv's ``bin/python`` selects the base interpreter and drops the venv's
        # site-packages, including Modal itself.
        executable = Path(os.path.abspath(os.fspath(python_executable)))
        script = client_script.resolve()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ModalWorkerRpcError("Modal client Python is unavailable")
        if not script.is_file():
            raise ModalWorkerRpcError("fixed Modal RPC client script is unavailable")
        return cls(
            python_executable=executable,
            client_script=script,
            expected_profile=require_nonempty_text(
                expected_profile, "Modal profile", max_length=256
            ),
        )

    def run(self, request: WorkerRpcRequest, *, timeout_seconds: int) -> ModalRpcResult:
        payload = base64.urlsafe_b64encode(
            canonical_json(request.to_dict()).encode("utf-8")
        ).decode("ascii")
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
        for name, value in os.environ.items():
            if name == "HOME" or name.startswith("MODAL_"):
                environment[name] = value
        try:
            completed = subprocess.run(
                [
                    str(self.python_executable),
                    str(self.client_script),
                    "--expected-profile",
                    self.expected_profile,
                    "--payload-b64",
                    payload,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise ModalWorkerRpcError("Modal worker RPC timed out") from error
        return ModalRpcResult(completed.returncode, completed.stdout, completed.stderr)


class ModalExperimentWorker(ExperimentWorker):
    """M7 worker implementation with no agent-controlled endpoint or command."""

    def __init__(
        self,
        *,
        worker_id: str,
        runtime_contract_id: str,
        runtime_contract_sha256: str,
        executor: ModalRpcExecutor,
        rpc_timeout_seconds: int = 60,
        recovered_contracts: Iterable[RunContract] = (),
    ) -> None:
        self.worker_id = require_identifier(worker_id, "Modal worker ID")
        self.runtime_contract_id = require_identifier(
            runtime_contract_id, "Modal runtime contract ID"
        )
        self.runtime_contract_sha256 = require_sha256(
            runtime_contract_sha256, "Modal runtime contract hash"
        )
        if (
            isinstance(rpc_timeout_seconds, bool)
            or not isinstance(rpc_timeout_seconds, int)
            or rpc_timeout_seconds <= 0
        ):
            raise ModalWorkerRpcError("Modal RPC timeout must be positive")
        self.executor = executor
        self.rpc_timeout_seconds = rpc_timeout_seconds
        self._contracts: dict[str, RunContract] = {}
        for contract in recovered_contracts:
            if not isinstance(contract, RunContract):
                raise ModalWorkerRpcError("recovered contracts must be RunContract values")
            existing = self._contracts.get(contract.trial_id)
            if existing is not None and existing.fingerprint() != contract.fingerprint():
                raise ModalWorkerRpcError("recovered trial has conflicting contracts")
            self._contracts[contract.trial_id] = contract

    def prepare(self, contract: RunContract) -> WorkerSnapshot:
        if not isinstance(contract, RunContract):
            raise ModalWorkerRpcError("Modal prepare requires a RunContract")
        snapshot = self._snapshot("prepare", {"contract": contract.to_dict()})
        self._verify_contract_snapshot(snapshot, contract)
        self._contracts[contract.trial_id] = contract
        return snapshot

    def launch(self, trial_id: str) -> WorkerSnapshot:
        return self._known_snapshot("launch", trial_id)

    def status(self, trial_id: str) -> WorkerSnapshot:
        return self._known_snapshot("status", trial_id)

    def heartbeat(self, trial_id: str) -> WorkerSnapshot:
        return self._known_snapshot("heartbeat", trial_id)

    def cancel(self, trial_id: str) -> WorkerSnapshot:
        return self._known_snapshot("cancel", trial_id)

    def fetch_evidence(self, trial_id: str) -> TrialEvidence:
        trial = require_identifier(trial_id, "Modal trial ID")
        contract = self._known_contract(trial)
        response = self._request(
            "fetch_evidence",
            {"trial_id": trial, "contract_hash": contract.fingerprint()},
        )
        if set(response) != {"evidence"}:
            raise ModalWorkerRpcError("Modal evidence response fields are invalid")
        evidence = TrialEvidence.from_dict(response["evidence"])
        if evidence.trial_id != trial:
            raise ModalWorkerRpcError("Modal evidence trial identity mismatch")
        self._verify_evidence(evidence, contract)
        return evidence

    def fetch_artifact(self, trial_id: str, artifact: ArtifactRef) -> bytes:
        if not isinstance(artifact, ArtifactRef):
            raise ModalWorkerRpcError("artifact transfer requires an ArtifactRef")
        trial = require_identifier(trial_id, "Modal trial ID")
        if artifact.size_bytes > MAX_ARTIFACT_BYTES:
            raise ModalWorkerRpcError("artifact exceeds the transfer cap")
        contract_hash = self._known_contract(trial).fingerprint()
        content = bytearray()
        while len(content) < artifact.size_bytes:
            response = self._request(
                "fetch_artifact",
                {
                    "trial_id": trial,
                    "contract_hash": contract_hash,
                    "artifact_id": artifact.artifact_id,
                    "offset": len(content),
                    "length": min(
                        ARTIFACT_CHUNK_BYTES, artifact.size_bytes - len(content)
                    ),
                },
            )
            if set(response) != {"artifact_chunk"}:
                raise ModalWorkerRpcError("Modal artifact response fields are invalid")
            chunk = response["artifact_chunk"]
            expected = {
                "artifact_id",
                "offset",
                "total_size_bytes",
                "sha256",
                "data_b64",
            }
            if not isinstance(chunk, dict) or set(chunk) != expected:
                raise ModalWorkerRpcError("Modal artifact chunk fields are invalid")
            if (
                chunk["artifact_id"] != artifact.artifact_id
                or chunk["offset"] != len(content)
                or chunk["total_size_bytes"] != artifact.size_bytes
                or chunk["sha256"] != artifact.sha256
            ):
                raise ModalWorkerRpcError("Modal artifact chunk identity mismatch")
            try:
                raw = base64.b64decode(chunk["data_b64"], validate=True)
            except (TypeError, ValueError) as error:
                raise ModalWorkerRpcError("Modal artifact chunk is invalid base64") from error
            if not raw or len(raw) > ARTIFACT_CHUNK_BYTES:
                raise ModalWorkerRpcError("Modal artifact chunk size is invalid")
            content.extend(raw)
        result = bytes(content)
        if len(result) != artifact.size_bytes:
            raise ModalWorkerRpcError("Modal artifact size mismatch")
        if hashlib.sha256(result).hexdigest() != artifact.sha256:
            raise ModalWorkerRpcError("Modal artifact digest mismatch")
        return result

    def materialize_artifact(
        self, trial_id: str, artifact: ArtifactRef, destination: Path
    ) -> Path:
        content = self.fetch_artifact(trial_id, artifact)
        target = destination.resolve()
        if target.exists():
            raise ModalWorkerRpcError("artifact destination already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    def _known_snapshot(self, action: str, trial_id: str) -> WorkerSnapshot:
        trial = require_identifier(trial_id, "Modal trial ID")
        contract_hash = self._known_contract(trial).fingerprint()
        snapshot = self._snapshot(
            action, {"trial_id": trial, "contract_hash": contract_hash}
        )
        if snapshot.trial_id != trial or snapshot.contract_hash != contract_hash:
            raise ModalWorkerRpcError("Modal snapshot does not match prepared trial")
        return snapshot

    def _known_contract(self, trial_id: str) -> RunContract:
        try:
            return self._contracts[trial_id]
        except KeyError as error:
            raise ModalWorkerRpcError("trial is not prepared in this client") from error

    @staticmethod
    def _verify_evidence(evidence: TrialEvidence, contract: RunContract) -> None:
        fields = (
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
        )
        if any(getattr(evidence, field) != getattr(contract, field) for field in fields):
            raise ModalWorkerRpcError("Modal evidence does not match the run contract")
        if evidence.elapsed_seconds > contract.max_wall_time_seconds:
            raise ModalWorkerRpcError("Modal evidence exceeded the wall-time contract")
        if Decimal(evidence.gpu_cost_usd) > Decimal(contract.max_gpu_cost_usd):
            raise ModalWorkerRpcError("Modal evidence exceeded the GPU-cost contract")

    def _snapshot(self, action: str, payload: dict[str, Any]) -> WorkerSnapshot:
        response = self._request(action, payload)
        if set(response) != {"snapshot"}:
            raise ModalWorkerRpcError("Modal snapshot response fields are invalid")
        snapshot = WorkerSnapshot.from_dict(response["snapshot"])
        if snapshot.worker_id != self.worker_id:
            raise ModalWorkerRpcError("Modal worker identity mismatch")
        return snapshot

    @staticmethod
    def _verify_contract_snapshot(
        snapshot: WorkerSnapshot, contract: RunContract
    ) -> None:
        if (
            snapshot.trial_id != contract.trial_id
            or snapshot.contract_hash != contract.fingerprint()
        ):
            raise ModalWorkerRpcError("Modal prepare response does not match contract")

    def _request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = WorkerRpcRequest.create(
            worker_id=self.worker_id,
            runtime_contract_id=self.runtime_contract_id,
            runtime_contract_sha256=self.runtime_contract_sha256,
            action=action,
            payload=payload,
        )
        result = self.executor.run(request, timeout_seconds=self.rpc_timeout_seconds)
        if len(result.stdout) > MAX_RPC_OUTPUT_BYTES or len(result.stderr) > MAX_RPC_OUTPUT_BYTES:
            raise ModalWorkerRpcError("Modal worker RPC output exceeded its cap")
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace")[:512]
            raise ModalWorkerRpcError(
                f"Modal worker RPC {action!r} failed with {result.returncode}: {detail}"
            )
        try:
            envelope = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModalWorkerRpcError("Modal worker returned invalid JSON") from error
        data = require_exact_keys(
            envelope,
            "Modal worker response",
            {"schema_version", "request_id", "result"},
        )
        if data["schema_version"] != 1 or data["request_id"] != request.request_id:
            raise ModalWorkerRpcError("Modal worker response request identity mismatch")
        if not isinstance(data["result"], dict):
            raise ModalWorkerRpcError("Modal worker result must be an object")
        return data["result"]
