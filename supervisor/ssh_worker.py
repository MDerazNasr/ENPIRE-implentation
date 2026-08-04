"""Provider-neutral SSH worker client with a fixed, mockable RPC protocol."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, Sequence

from supervisor.canonical import (
    canonical_json,
    require_identifier,
    require_nonempty_text,
)
from supervisor.contracts import TrialEvidence
from supervisor.workers import (
    ExperimentWorker,
    RunContract,
    WorkerError,
    WorkerSnapshot,
)


MAX_RPC_OUTPUT_BYTES = 1_048_576
SSH_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9@._:\[\]-]{0,254}")
REMOTE_PATH = re.compile(r"/[A-Za-z0-9_./-]{1,511}")


class SshWorkerError(WorkerError):
    """Raised when an SSH endpoint or remote response violates the protocol."""


@dataclass(frozen=True)
class RpcResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise SshWorkerError("RPC return code must be an integer")
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise SshWorkerError("RPC output must be bytes")


class RpcExecutor(Protocol):
    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> RpcResult: ...


class SubprocessRpcExecutor:
    """Explicit live executor; constructing the client alone performs no I/O."""

    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> RpcResult:
        try:
            completed = subprocess.run(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "GIT_TERMINAL_PROMPT": "0",
                },
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SshWorkerError("SSH worker RPC timed out") from error
        return RpcResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class SshEndpoint:
    worker_id: str
    host: str
    remote_helper: str
    ssh_executable: Path
    connect_timeout_seconds: int = 10
    rpc_timeout_seconds: int = 30

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        host: str,
        remote_helper: str,
        ssh_executable: Path,
        connect_timeout_seconds: int = 10,
        rpc_timeout_seconds: int = 30,
    ) -> "SshEndpoint":
        identity = require_identifier(worker_id, "SSH worker ID")
        host_text = require_nonempty_text(host, "SSH host", max_length=255)
        if not SSH_HOST.fullmatch(host_text) or host_text.startswith("-"):
            raise SshWorkerError("SSH host contains unsupported characters")
        helper = require_nonempty_text(
            remote_helper, "SSH remote helper", max_length=512
        )
        path = PurePosixPath(helper)
        if not path.is_absolute() or not REMOTE_PATH.fullmatch(helper) or ".." in path.parts:
            raise SshWorkerError("SSH remote helper must be a safe absolute path")
        executable = ssh_executable.resolve()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise SshWorkerError("SSH executable is unavailable")
        for value, field in (
            (connect_timeout_seconds, "SSH connect timeout"),
            (rpc_timeout_seconds, "SSH RPC timeout"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SshWorkerError(f"{field} must be positive")
        return cls(
            worker_id=identity,
            host=host_text,
            remote_helper=helper,
            ssh_executable=executable,
            connect_timeout_seconds=connect_timeout_seconds,
            rpc_timeout_seconds=rpc_timeout_seconds,
        )

    def argv(self, action: str, payload: Any) -> tuple[str, ...]:
        operation = require_identifier(action, "SSH worker action")
        encoded = base64.urlsafe_b64encode(
            canonical_json(payload).encode("utf-8")
        ).decode("ascii")
        return (
            str(self.ssh_executable),
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
            self.host,
            self.remote_helper,
            operation,
            encoded,
        )


class SshExperimentWorker(ExperimentWorker):
    """Strict client for a fixed remote helper; it accepts no agent commands."""

    def __init__(self, *, endpoint: SshEndpoint, executor: RpcExecutor) -> None:
        self.endpoint = endpoint
        self.executor = executor
        self.worker_id = endpoint.worker_id

    def prepare(self, contract: RunContract) -> WorkerSnapshot:
        if not isinstance(contract, RunContract):
            raise SshWorkerError("SSH prepare requires a RunContract")
        snapshot = self._snapshot("prepare", {"contract": contract.to_dict()})
        if (
            snapshot.trial_id != contract.trial_id
            or snapshot.contract_hash != contract.fingerprint()
        ):
            raise SshWorkerError("SSH prepare response does not match the contract")
        return snapshot

    def launch(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot("launch", self._trial_payload(trial_id))

    def status(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot("status", self._trial_payload(trial_id))

    def heartbeat(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot("heartbeat", self._trial_payload(trial_id))

    def cancel(self, trial_id: str) -> WorkerSnapshot:
        return self._snapshot("cancel", self._trial_payload(trial_id))

    def fetch_evidence(self, trial_id: str) -> TrialEvidence:
        response = self._request("fetch_evidence", self._trial_payload(trial_id))
        if set(response) != {"evidence"}:
            raise SshWorkerError("SSH evidence response fields are invalid")
        evidence = TrialEvidence.from_dict(response["evidence"])
        if evidence.trial_id != trial_id:
            raise SshWorkerError("SSH evidence trial identity mismatch")
        return evidence

    def _snapshot(self, action: str, payload: dict[str, Any]) -> WorkerSnapshot:
        response = self._request(action, payload)
        if set(response) != {"snapshot"}:
            raise SshWorkerError("SSH snapshot response fields are invalid")
        snapshot = WorkerSnapshot.from_dict(response["snapshot"])
        if snapshot.worker_id != self.worker_id:
            raise SshWorkerError("SSH worker identity mismatch")
        return snapshot

    def _request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        argv = self.endpoint.argv(action, payload)
        result = self.executor.run(
            argv, timeout_seconds=self.endpoint.rpc_timeout_seconds
        )
        if len(result.stdout) > MAX_RPC_OUTPUT_BYTES or len(result.stderr) > MAX_RPC_OUTPUT_BYTES:
            raise SshWorkerError("SSH worker RPC output exceeded its cap")
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace")[:512]
            raise SshWorkerError(
                f"SSH worker RPC {action!r} failed with {result.returncode}: {detail}"
            )
        try:
            response = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SshWorkerError("SSH worker returned invalid JSON") from error
        if not isinstance(response, dict):
            raise SshWorkerError("SSH worker response must be an object")
        return response

    @staticmethod
    def _trial_payload(trial_id: str) -> dict[str, str]:
        return {"trial_id": require_identifier(trial_id, "SSH trial ID")}
