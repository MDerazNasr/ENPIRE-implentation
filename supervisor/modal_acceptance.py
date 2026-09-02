"""Immutable Modal request/receipt transport for non-promotable D2 acceptance."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    require_exact_keys,
    require_git_commit,
    require_identifier,
    require_sha256,
    timestamp_text,
)
from supervisor.d1_backend import D1LaunchPlan, ExecutionMode, ProcessOutcome


RESULT_MARKER = "D2_MODAL_ACCEPTANCE_RESULT="
SOURCE_ROOTS = ("agent", "envs", "scripts", "supervisor")
SOURCE_FILES = ("sitecustomize.py", "modal_d2_acceptance.py")


class ModalAcceptanceError(ContractError):
    """Raised when the Modal acceptance request or receipt is invalid."""


def _b64_encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64_decode(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ModalAcceptanceError(f"{field} must be non-empty base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ModalAcceptanceError(f"{field} is not valid base64") from error


def source_bundle_hashes(root: Path) -> dict[str, str]:
    root = root.resolve()
    paths: list[Path] = []
    for name in SOURCE_ROOTS:
        directory = root / name
        if not directory.is_dir():
            raise ModalAcceptanceError(f"runtime source directory is missing: {name}")
        paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    for name in SOURCE_FILES:
        path = root / name
        if not path.is_file():
            raise ModalAcceptanceError(f"runtime source file is missing: {name}")
        paths.append(path)
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(paths))
    }


@dataclass(frozen=True)
class ModalAcceptanceRequest:
    request_id: str
    plan: Mapping[str, Any]
    plan_hash: str
    derived_config_b64: str
    derived_config_sha256: str
    source_hashes: Mapping[str, str]
    source_bundle_hash: str

    @classmethod
    def create(cls, plan: D1LaunchPlan) -> "ModalAcceptanceRequest":
        if plan.mode != ExecutionMode.PAID_ACCEPTANCE:
            raise ModalAcceptanceError(
                "Modal acceptance transport requires paid_acceptance mode"
            )
        config_path = Path(plan.derived_config_path)
        config = config_path.read_bytes()
        config_hash = hashlib.sha256(config).hexdigest()
        if config_hash != plan.contract.config_hash:
            raise ModalAcceptanceError("derived config changed before Modal request")
        hashes = source_bundle_hashes(Path(plan.workspace))
        return cls(
            request_id=require_identifier(
                f"modal-{plan.contract.trial_id}", "Modal request ID"
            ),
            plan=plan.to_dict(),
            plan_hash=plan.fingerprint(),
            derived_config_b64=_b64_encode(config),
            derived_config_sha256=config_hash,
            source_hashes=hashes,
            source_bundle_hash=fingerprint(hashes),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ModalAcceptanceRequest":
        fields = {
            "schema_version",
            "request_id",
            "plan",
            "plan_hash",
            "derived_config_b64",
            "derived_config_sha256",
            "source_hashes",
            "source_bundle_hash",
        }
        data = require_exact_keys(value, "Modal acceptance request", fields)
        if data["schema_version"] != 1 or not isinstance(data["plan"], dict):
            raise ModalAcceptanceError("Modal acceptance request schema is invalid")
        plan_hash = require_sha256(data["plan_hash"], "Modal request plan hash")
        if fingerprint(data["plan"]) != plan_hash:
            raise ModalAcceptanceError("Modal request plan hash mismatch")
        raw_hashes = data["source_hashes"]
        if not isinstance(raw_hashes, dict) or not raw_hashes:
            raise ModalAcceptanceError("Modal request source hashes are missing")
        hashes: dict[str, str] = {}
        for path, digest in raw_hashes.items():
            if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
                raise ModalAcceptanceError("Modal request source path is unsafe")
            hashes[path] = require_sha256(digest, f"Modal source hash {path}")
        bundle_hash = require_sha256(
            data["source_bundle_hash"], "Modal source bundle hash"
        )
        if fingerprint(hashes) != bundle_hash:
            raise ModalAcceptanceError("Modal request source bundle hash mismatch")
        config = _b64_decode(data["derived_config_b64"], "derived_config_b64")
        config_hash = require_sha256(
            data["derived_config_sha256"], "Modal request config hash"
        )
        if hashlib.sha256(config).hexdigest() != config_hash:
            raise ModalAcceptanceError("Modal request derived config hash mismatch")
        contract = data["plan"].get("contract")
        if not isinstance(contract, dict):
            raise ModalAcceptanceError("Modal request plan contract is missing")
        require_git_commit(contract.get("candidate_commit"), "Modal candidate commit")
        if data["plan"].get("mode") != ExecutionMode.PAID_ACCEPTANCE.value:
            raise ModalAcceptanceError("Modal request plan mode is not paid_acceptance")
        if contract.get("config_hash") != config_hash:
            raise ModalAcceptanceError("Modal request contract config hash mismatch")
        return cls(
            request_id=require_identifier(data["request_id"], "Modal request ID"),
            plan=data["plan"],
            plan_hash=plan_hash,
            derived_config_b64=data["derived_config_b64"],
            derived_config_sha256=config_hash,
            source_hashes=dict(sorted(hashes.items())),
            source_bundle_hash=bundle_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "request_id": self.request_id,
            "plan": dict(self.plan),
            "plan_hash": self.plan_hash,
            "derived_config_b64": self.derived_config_b64,
            "derived_config_sha256": self.derived_config_sha256,
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "source_bundle_hash": self.source_bundle_hash,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class ModalAcceptanceReceipt:
    request_hash: str
    status: str
    return_code: int
    manifest_b64: str
    manifest_sha256: str
    log_b64: str
    log_sha256: str
    artifact_inventory: tuple[Mapping[str, Any], ...]
    worker: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Any) -> "ModalAcceptanceReceipt":
        fields = {
            "schema_version",
            "request_hash",
            "status",
            "return_code",
            "manifest_b64",
            "manifest_sha256",
            "log_b64",
            "log_sha256",
            "artifact_inventory",
            "worker",
        }
        data = require_exact_keys(value, "Modal acceptance receipt", fields)
        if data["schema_version"] != 1 or data["status"] not in {"complete", "failed"}:
            raise ModalAcceptanceError("Modal acceptance receipt schema/status is invalid")
        return_code = data["return_code"]
        if isinstance(return_code, bool) or not isinstance(return_code, int):
            raise ModalAcceptanceError("Modal receipt return code is invalid")
        if (data["status"] == "complete") != (return_code == 0):
            raise ModalAcceptanceError("Modal receipt status and return code disagree")
        manifest = _b64_decode(data["manifest_b64"], "manifest_b64")
        log = _b64_decode(data["log_b64"], "log_b64")
        manifest_hash = require_sha256(
            data["manifest_sha256"], "Modal receipt manifest hash"
        )
        log_hash = require_sha256(data["log_sha256"], "Modal receipt log hash")
        if hashlib.sha256(manifest).hexdigest() != manifest_hash:
            raise ModalAcceptanceError("Modal receipt manifest hash mismatch")
        if hashlib.sha256(log).hexdigest() != log_hash:
            raise ModalAcceptanceError("Modal receipt log hash mismatch")
        inventory = data["artifact_inventory"]
        if not isinstance(inventory, list) or not inventory:
            raise ModalAcceptanceError("Modal receipt artifact inventory is missing")
        for index, item in enumerate(inventory):
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}:
                raise ModalAcceptanceError(f"Modal inventory item {index} is invalid")
            require_sha256(item["sha256"], f"Modal inventory item {index} hash")
            if (
                not isinstance(item["path"], str)
                or not item["path"]
                or isinstance(item["size_bytes"], bool)
                or not isinstance(item["size_bytes"], int)
                or item["size_bytes"] < 0
            ):
                raise ModalAcceptanceError(f"Modal inventory item {index} is invalid")
        worker = data["worker"]
        if not isinstance(worker, dict) or not worker:
            raise ModalAcceptanceError("Modal receipt worker identity is missing")
        return cls(
            request_hash=require_sha256(data["request_hash"], "Modal request hash"),
            status=data["status"],
            return_code=return_code,
            manifest_b64=data["manifest_b64"],
            manifest_sha256=manifest_hash,
            log_b64=data["log_b64"],
            log_sha256=log_hash,
            artifact_inventory=tuple(inventory),
            worker=worker,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "request_hash": self.request_hash,
            "status": self.status,
            "return_code": self.return_code,
            "manifest_b64": self.manifest_b64,
            "manifest_sha256": self.manifest_sha256,
            "log_b64": self.log_b64,
            "log_sha256": self.log_sha256,
            "artifact_inventory": [dict(item) for item in self.artifact_inventory],
            "worker": dict(self.worker),
        }


class ModalAcceptanceTransport:
    """Run the immutable plan through Modal and materialize verified artifacts."""

    def __init__(
        self,
        *,
        modal_executable: Path,
        app_path: Path,
        expected_profile: str,
    ) -> None:
        self.modal_executable = modal_executable.resolve()
        self.app_path = app_path.resolve()
        self.expected_profile = expected_profile

    def run_plan(self, plan: D1LaunchPlan) -> ProcessOutcome:
        if not self.modal_executable.is_file() or not self.app_path.is_file():
            raise ModalAcceptanceError("Modal executable or application is missing")
        profile = subprocess.run(
            [str(self.modal_executable), "profile", "current"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        ).stdout.strip()
        if profile != self.expected_profile:
            raise ModalAcceptanceError(
                f"active Modal profile {profile!r} is not the approved profile"
            )
        request = ModalAcceptanceRequest.create(plan)
        payload = _b64_encode(canonical_json(request.to_dict()).encode("utf-8"))
        command = [
            str(self.modal_executable),
            "run",
            str(self.app_path),
            "--payload-b64",
            payload,
            "--expected-profile",
            self.expected_profile,
        ]
        started = datetime.now(timezone.utc)
        monotonic_started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=Path(plan.workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(
                timeout=plan.contract.max_wall_time_seconds + 60
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
        finished = datetime.now(timezone.utc)
        return_code = None if timed_out else process.returncode
        if not timed_out and process.returncode == 0:
            try:
                receipt = self._extract_receipt(stdout, request)
                self._materialize(plan, receipt)
                return_code = receipt.return_code
            except ContractError as error:
                stderr += f"\nmodal acceptance receipt error: {error}\n".encode()
                return_code = 78
        return ProcessOutcome(
            return_code=return_code,
            started_at=timestamp_text(started),
            finished_at=timestamp_text(finished),
            elapsed_seconds=time.monotonic() - monotonic_started,
            stdout_hash=hashlib.sha256(stdout).hexdigest(),
            stderr_hash=hashlib.sha256(stderr).hexdigest(),
            timed_out=timed_out,
        )

    @staticmethod
    def _extract_receipt(
        stdout: bytes,
        request: ModalAcceptanceRequest,
    ) -> ModalAcceptanceReceipt:
        markers = [
            line[len(RESULT_MARKER) :]
            for line in stdout.decode("utf-8", errors="replace").splitlines()
            if line.startswith(RESULT_MARKER)
        ]
        if len(markers) != 1:
            raise ModalAcceptanceError("Modal output must contain exactly one receipt")
        payload = json.loads(_b64_decode(markers[0], "Modal result marker"))
        receipt = ModalAcceptanceReceipt.from_dict(payload)
        if receipt.request_hash != request.fingerprint():
            raise ModalAcceptanceError("Modal receipt is bound to another request")
        return receipt

    @staticmethod
    def _materialize(
        plan: D1LaunchPlan,
        receipt: ModalAcceptanceReceipt,
    ) -> None:
        manifest = _b64_decode(receipt.manifest_b64, "manifest_b64")
        log = _b64_decode(receipt.log_b64, "log_b64")
        receipt_bytes = canonical_json(receipt.to_dict()).encode("utf-8") + b"\n"
        for path, content in (
            (Path(plan.manifest_path), manifest),
            (Path(plan.log_path), log),
            (Path(plan.manifest_path).with_name("modal-receipt.json"), receipt_bytes),
        ):
            if path.exists():
                raise ModalAcceptanceError(f"local Modal artifact already exists: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=path.name + ".", suffix=".tmp", dir=path.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
