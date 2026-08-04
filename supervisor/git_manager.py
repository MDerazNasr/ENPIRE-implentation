"""Isolated per-hypothesis Git lifecycle for validated proposals."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    fingerprint,
    parse_timestamp,
    require_git_commit,
    require_identifier,
    require_safe_relative_path,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import SCHEMA_VERSION, CampaignSpec, EditMode, TrialState
from supervisor.enforcement import (
    MaterializedConfig,
    PolicyViolation,
    ProposalEnforcer,
    ValidationReport,
    materialize_config,
)
from supervisor.proposals import Proposal
from supervisor.ledger import EntityType, EventLedger, LedgerEvent


MAX_COMMAND_OUTPUT_BYTES = 1_048_576


class GitOperationError(ContractError):
    """Raised for a bounded Git or candidate-preparation failure."""


class PreparationStatus(str, Enum):
    REJECTED = "rejected"
    FAILED = "failed"
    READY = "ready"


@dataclass(frozen=True)
class HarnessCheck:
    check_id: str
    argv: tuple[str, ...]
    timeout_seconds: int

    def __post_init__(self) -> None:
        require_identifier(self.check_id, "harness_check.check_id")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise GitOperationError("harness check argv must be a non-empty tuple")
        if not all(
            isinstance(value, str) and value and "\x00" not in value
            for value in self.argv
        ):
            raise GitOperationError("harness check argv contains an invalid value")
        executable = Path(self.argv[0])
        if not executable.is_absolute():
            raise GitOperationError("harness check executable must be absolute")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise GitOperationError("harness check executable must exist and be executable")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 600
        ):
            raise GitOperationError("harness check timeout must be between 1 and 600 seconds")

    @classmethod
    def create(
        cls,
        *,
        check_id: str,
        argv: Sequence[str],
        timeout_seconds: int = 60,
    ) -> "HarnessCheck":
        if isinstance(argv, (str, bytes)) or not argv:
            raise GitOperationError("harness check argv must be a non-empty sequence")
        normalized: list[str] = []
        for index, value in enumerate(argv):
            if not isinstance(value, str) or not value or "\x00" in value:
                raise GitOperationError(f"harness check argv[{index}] is invalid")
            normalized.append(value)
        executable = Path(normalized[0])
        if not executable.is_absolute():
            raise GitOperationError("harness check executable must be absolute")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise GitOperationError("harness check executable must exist and be executable")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 600
        ):
            raise GitOperationError("harness check timeout must be between 1 and 600 seconds")
        return cls(
            check_id=require_identifier(check_id, "harness_check.check_id"),
            argv=tuple(normalized),
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    argv: tuple[str, ...]
    argv_hash: str
    exit_code: int | None
    elapsed_seconds: float
    stdout_hash: str | None
    stderr_hash: str | None
    passed: bool
    error: str | None

    def __post_init__(self) -> None:
        require_identifier(self.check_id, "check_result.check_id")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise GitOperationError("check result argv must be a non-empty tuple")
        require_sha256(self.argv_hash, "check_result.argv_hash")
        if self.argv_hash != fingerprint(list(self.argv)):
            raise GitOperationError("check result argv hash does not match argv")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise GitOperationError("check result exit code must be an integer or null")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(float(self.elapsed_seconds))
            or self.elapsed_seconds < 0
        ):
            raise GitOperationError("check result elapsed time must be finite and non-negative")
        for field, value in (
            ("stdout_hash", self.stdout_hash),
            ("stderr_hash", self.stderr_hash),
        ):
            if value is not None:
                require_sha256(value, f"check_result.{field}")
        if self.passed and (self.exit_code != 0 or self.error is not None):
            raise GitOperationError("passed check result requires exit 0 and no error")
        if not self.passed and not self.error:
            raise GitOperationError("failed check result requires an error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "argv": list(self.argv),
            "argv_hash": self.argv_hash,
            "exit_code": self.exit_code,
            "elapsed_seconds": self.elapsed_seconds,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "passed": self.passed,
            "error": self.error,
        }


@dataclass(frozen=True)
class PreparationRecord:
    schema_version: int
    status: PreparationStatus
    campaign_id: str
    proposal_id: str
    proposal_hash: str
    validation_hash: str
    validation_accepted: bool
    base_commit: str
    stable_head_before: str | None
    stable_head_after: str | None
    branch_name: str | None
    worktree_path: str | None
    candidate_commit: str | None
    candidate_tree_hash: str | None
    staged_diff_hash: str | None
    materialized_config_hash: str | None
    base_config_hash: str | None
    overrides_hash: str | None
    resolved_config_hash: str | None
    changed_paths: tuple[str, ...]
    checks: tuple[CheckResult, ...]
    errors: tuple[str, ...]
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise GitOperationError(
                f"preparation schema version must be {SCHEMA_VERSION}"
            )
        require_identifier(self.campaign_id, "preparation.campaign_id")
        require_identifier(self.proposal_id, "preparation.proposal_id")
        if not isinstance(self.status, PreparationStatus):
            raise GitOperationError("preparation status is unsupported")
        if not isinstance(self.validation_accepted, bool):
            raise GitOperationError("preparation validation flag must be boolean")
        require_sha256(self.proposal_hash, "preparation.proposal_hash")
        require_sha256(self.validation_hash, "preparation.validation_hash")
        require_git_commit(self.base_commit, "preparation.base_commit")
        for field, value in (
            ("stable_head_before", self.stable_head_before),
            ("stable_head_after", self.stable_head_after),
            ("candidate_commit", self.candidate_commit),
            ("candidate_tree_hash", self.candidate_tree_hash),
        ):
            if value is not None:
                require_git_commit(value, f"preparation.{field}")
        for field, value in (
            ("staged_diff_hash", self.staged_diff_hash),
            ("materialized_config_hash", self.materialized_config_hash),
            ("base_config_hash", self.base_config_hash),
            ("overrides_hash", self.overrides_hash),
            ("resolved_config_hash", self.resolved_config_hash),
        ):
            if value is not None:
                require_sha256(value, f"preparation.{field}")
        config_hashes = (
            self.materialized_config_hash,
            self.base_config_hash,
            self.overrides_hash,
            self.resolved_config_hash,
        )
        if any(value is not None for value in config_hashes) and not all(
            value is not None for value in config_hashes
        ):
            raise GitOperationError("preparation config hashes must be all present or all null")
        if self.branch_name is not None:
            parts = self.branch_name.split("/")
            if len(parts) != 3 or parts[0] != "hypothesis":
                raise GitOperationError("preparation branch name is not a hypothesis branch")
            for part in parts[1:]:
                require_identifier(part, "preparation branch component")
        if self.worktree_path is not None and not Path(self.worktree_path).is_absolute():
            raise GitOperationError("preparation worktree path must be absolute")
        if not isinstance(self.changed_paths, tuple):
            raise GitOperationError("preparation changed paths must be a tuple")
        if len(set(self.changed_paths)) != len(self.changed_paths):
            raise GitOperationError("preparation changed paths must be unique")
        for path in self.changed_paths:
            require_safe_relative_path(path, "preparation.changed_path")
        if not isinstance(self.checks, tuple) or not all(
            isinstance(item, CheckResult) for item in self.checks
        ):
            raise GitOperationError("preparation checks must contain CheckResult records")
        if not isinstance(self.errors, tuple) or not all(
            isinstance(item, str) and item for item in self.errors
        ):
            raise GitOperationError("preparation errors must contain non-empty strings")
        started = parse_timestamp(self.started_at, "preparation.started_at")
        completed = parse_timestamp(self.completed_at, "preparation.completed_at")
        if completed < started:
            raise GitOperationError("preparation completed before it started")
        if self.status == PreparationStatus.READY:
            required = (
                self.stable_head_before,
                self.stable_head_after,
                self.branch_name,
                self.worktree_path,
                self.candidate_commit,
                self.candidate_tree_hash,
                self.staged_diff_hash,
            )
            if (
                not self.validation_accepted
                or self.errors
                or not all(value is not None for value in required)
                or self.stable_head_before != self.stable_head_after
                or not self.changed_paths
                or not self.checks
                or not all(item.passed for item in self.checks)
            ):
                raise GitOperationError("ready preparation record is inconsistent")
        elif self.status == PreparationStatus.REJECTED:
            if (
                self.validation_accepted
                or not self.errors
                or self.branch_name is not None
                or self.worktree_path is not None
                or self.candidate_commit is not None
            ):
                raise GitOperationError("rejected preparation record is inconsistent")
        elif not self.errors:
            raise GitOperationError("failed preparation record requires errors")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "campaign_id": self.campaign_id,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "validation_hash": self.validation_hash,
            "validation_accepted": self.validation_accepted,
            "base_commit": self.base_commit,
            "stable_head_before": self.stable_head_before,
            "stable_head_after": self.stable_head_after,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "candidate_commit": self.candidate_commit,
            "candidate_tree_hash": self.candidate_tree_hash,
            "staged_diff_hash": self.staged_diff_hash,
            "materialized_config_hash": self.materialized_config_hash,
            "base_config_hash": self.base_config_hash,
            "overrides_hash": self.overrides_hash,
            "resolved_config_hash": self.resolved_config_hash,
            "changed_paths": list(self.changed_paths),
            "checks": [item.to_dict() for item in self.checks],
            "errors": list(self.errors),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class HypothesisSnapshot:
    campaign_id: str
    proposal_id: str
    branch_name: str
    branch_commit: str | None
    worktree_path: str | None
    worktree_head: str | None
    changed_paths: tuple[str, ...]

    @property
    def exists(self) -> bool:
        return self.branch_commit is not None or self.worktree_path is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "proposal_id": self.proposal_id,
            "branch_name": self.branch_name,
            "branch_commit": self.branch_commit,
            "worktree_path": self.worktree_path,
            "worktree_head": self.worktree_head,
            "changed_paths": list(self.changed_paths),
            "exists": self.exists,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


class GitExperimentManager:
    """Apply one accepted proposal without moving the stable repository HEAD."""

    def __init__(
        self,
        *,
        repository: Path,
        worktree_root: Path,
        enforcer: ProposalEnforcer,
        trusted_checks: Mapping[str, HarnessCheck],
        objective_check: HarnessCheck | None = None,
    ) -> None:
        self.repository = repository.resolve()
        self.worktree_root = worktree_root.resolve()
        if not self.repository.is_dir():
            raise GitOperationError("repository must be an existing directory")
        if not self.worktree_root.is_dir():
            raise GitOperationError("worktree root must be an existing directory")
        if self.worktree_root == self.repository or self.repository in self.worktree_root.parents:
            raise GitOperationError("worktree root must be outside the stable repository")
        self.enforcer = enforcer
        self.trusted_checks = dict(trusted_checks)
        self.objective_check = objective_check
        if set(self.trusted_checks) != set(enforcer.policy.trusted_test_ids):
            raise GitOperationError(
                "trusted check registry must exactly match the enforcement policy"
            )
        for check_id, check in self.trusted_checks.items():
            if check_id != check.check_id:
                raise GitOperationError("trusted check registry key does not match check ID")
        if (
            objective_check is not None
            and objective_check.check_id in self.trusted_checks
        ):
            raise GitOperationError("objective check must be separate from requested tests")
        top = self._git(("rev-parse", "--show-toplevel")).stdout_text().strip()
        if Path(top).resolve() != self.repository:
            raise GitOperationError("repository path is not its Git worktree root")

    @staticmethod
    def _environment() -> dict[str, str]:
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if "TMPDIR" in os.environ:
            environment["TMPDIR"] = os.environ["TMPDIR"]
        return environment

    def _git(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
        check: bool = True,
        timeout_seconds: int = 60,
    ) -> "_DecodedGitResult":
        command = ["git", "-C", str(cwd or self.repository), *args]
        try:
            completed = subprocess.run(
                command,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment(),
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise GitOperationError(
                f"Git operation {args[0]!r} exceeded {timeout_seconds} seconds"
            ) from error
        if (
            len(completed.stdout) > MAX_COMMAND_OUTPUT_BYTES
            or len(completed.stderr) > MAX_COMMAND_OUTPUT_BYTES
        ):
            raise GitOperationError(f"Git operation {args[0]!r} produced excessive output")
        result = _DecodedGitResult(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
        if check and completed.returncode != 0:
            raise GitOperationError(
                f"Git operation {args[0]!r} failed with exit {completed.returncode}; "
                f"stderr hash {hashlib.sha256(completed.stderr).hexdigest()}"
            )
        return result

    def _head(self, cwd: Path | None = None) -> str:
        return require_git_commit(
            self._git(("rev-parse", "HEAD"), cwd=cwd).stdout_text().strip(),
            "repository HEAD",
        )

    def _ensure_clean_stable_repository(self) -> None:
        status = self._git(
            ("status", "--porcelain=v1", "--untracked-files=all")
        ).stdout
        if status:
            raise GitOperationError("stable repository must be clean before preparation")

    def _verify_commit(self, commit: str) -> None:
        commit = require_git_commit(commit, "candidate base commit")
        resolved = self._git(("rev-parse", f"{commit}^{{commit}}")).stdout_text().strip()
        if resolved != commit:
            raise GitOperationError("candidate base commit did not resolve exactly")

    @staticmethod
    def _branch_and_path(
        worktree_root: Path,
        campaign_id: str,
        proposal_id: str,
    ) -> tuple[str, Path]:
        campaign = require_identifier(campaign_id, "campaign_id")
        proposal = require_identifier(proposal_id, "proposal_id")
        return (
            f"hypothesis/{campaign}/{proposal}",
            worktree_root / f"{campaign}--{proposal}",
        )

    def _branch_must_not_exist(self, branch_name: str) -> None:
        result = self._git(
            ("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"),
            check=False,
        )
        if result.return_code == 0:
            raise GitOperationError("hypothesis branch already exists")
        if result.return_code != 1:
            raise GitOperationError("could not determine whether hypothesis branch exists")

    def discover(self, campaign_id: str, proposal_id: str) -> HypothesisSnapshot:
        """Rediscover deterministic hypothesis state without mutating Git."""

        branch_name, expected_path = self._branch_and_path(
            self.worktree_root,
            campaign_id,
            proposal_id,
        )
        branch = self._git(
            ("show-ref", "--verify", "--hash", f"refs/heads/{branch_name}"),
            check=False,
        )
        if branch.return_code not in (0, 1):
            raise GitOperationError("could not inspect hypothesis branch")
        branch_commit = (
            require_git_commit(branch.stdout_text().strip(), "hypothesis branch commit")
            if branch.return_code == 0
            else None
        )
        worktree_path: str | None = None
        worktree_head: str | None = None
        changed_paths: tuple[str, ...] = ()
        if expected_path.exists():
            if not expected_path.is_dir():
                raise GitOperationError("hypothesis path exists but is not a directory")
            top = self._git(
                ("rev-parse", "--show-toplevel"), cwd=expected_path
            ).stdout_text().strip()
            if Path(top).resolve() != expected_path.resolve():
                raise GitOperationError("hypothesis path is not its Git worktree root")
            symbolic = self._git(
                ("symbolic-ref", "--short", "HEAD"), cwd=expected_path
            ).stdout_text().strip()
            if symbolic != branch_name:
                raise GitOperationError("hypothesis worktree is on an unexpected branch")
            if branch_commit is None:
                raise GitOperationError("hypothesis worktree exists without its branch")
            worktree_path = str(expected_path)
            worktree_head = self._head(expected_path)
            changed_paths = self._changed_paths(expected_path)
        return HypothesisSnapshot(
            campaign_id=require_identifier(campaign_id, "snapshot.campaign_id"),
            proposal_id=require_identifier(proposal_id, "snapshot.proposal_id"),
            branch_name=branch_name,
            branch_commit=branch_commit,
            worktree_path=worktree_path,
            worktree_head=worktree_head,
            changed_paths=changed_paths,
        )

    @staticmethod
    def _safe_target(worktree: Path, relative_path: str) -> Path:
        relative = require_safe_relative_path(relative_path, "candidate target path")
        parts = _pure_path_parts(relative)
        if "/".join(parts) != relative:
            raise GitOperationError("candidate target path is not canonical POSIX syntax")
        target = worktree.joinpath(*parts)
        current = worktree
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise GitOperationError(f"candidate path traverses a symlink: {relative}")
        resolved = target.resolve(strict=False)
        if resolved != worktree and worktree not in resolved.parents:
            raise GitOperationError("candidate target escapes its worktree")
        return target

    def _changed_paths(self, worktree: Path) -> tuple[str, ...]:
        tracked = self._git(
            ("diff", "--name-only", "--no-renames", "-z"), cwd=worktree
        ).stdout
        staged = self._git(
            ("diff", "--cached", "--name-only", "--no-renames", "-z"), cwd=worktree
        ).stdout
        untracked = self._git(
            ("ls-files", "--others", "--exclude-standard", "-z"), cwd=worktree
        ).stdout
        values = set()
        for blob in (tracked, staged, untracked):
            for raw in blob.split(b"\x00"):
                if not raw:
                    continue
                try:
                    path = raw.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise GitOperationError("candidate path is not UTF-8") from error
                values.add(require_safe_relative_path(path, "Git changed path"))
        return tuple(sorted(values))

    def _verify_exact_changes(
        self,
        worktree: Path,
        expected_paths: Sequence[str],
    ) -> tuple[str, ...]:
        changed = self._changed_paths(worktree)
        expected = tuple(sorted(expected_paths))
        if changed != expected:
            raise GitOperationError(
                f"candidate changed paths {changed} do not match expected paths {expected}"
            )
        for path in changed:
            target = self._safe_target(worktree, path)
            if not target.is_file():
                raise GitOperationError(f"candidate target is not a regular file: {path}")
        return changed

    def _validate_candidate_content(
        self,
        proposal: Proposal,
        worktree: Path,
        materialized: MaterializedConfig | None,
    ) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []
        if proposal.edit_mode == EditMode.ACTOR_OBJECTIVE_CODE:
            for path in proposal.changed_paths:
                target = self._safe_target(worktree, path)
                violations.extend(
                    self.enforcer.validate_candidate_source(path, target.read_bytes())
                )
        else:
            if materialized is None:
                return (
                    PolicyViolation(
                        "missing_materialization",
                        "config proposal has no materialized configuration",
                    ),
                )
            target = self._safe_target(worktree, materialized.target_path)
            try:
                decoded = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return (
                    PolicyViolation(
                        "invalid_config_artifact",
                        "materialized configuration is not readable canonical JSON",
                        materialized.target_path,
                    ),
                )
            if fingerprint(decoded) != materialized.resolved_config_hash:
                violations.append(
                    PolicyViolation(
                        "config_hash_mismatch",
                        "materialized configuration no longer matches its resolved hash",
                        materialized.target_path,
                    )
                )
        return tuple(violations)

    def _run_check(self, check: HarnessCheck, worktree: Path) -> CheckResult:
        started = time.monotonic()
        argv_hash = fingerprint(list(check.argv))
        try:
            completed = subprocess.run(
                list(check.argv),
                cwd=worktree,
                env=self._environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=check.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or b""
            stderr = error.stderr or b""
            return CheckResult(
                check_id=check.check_id,
                argv=check.argv,
                argv_hash=argv_hash,
                exit_code=None,
                elapsed_seconds=time.monotonic() - started,
                stdout_hash=hashlib.sha256(stdout).hexdigest(),
                stderr_hash=hashlib.sha256(stderr).hexdigest(),
                passed=False,
                error=f"check exceeded {check.timeout_seconds}-second timeout",
            )
        if (
            len(completed.stdout) > MAX_COMMAND_OUTPUT_BYTES
            or len(completed.stderr) > MAX_COMMAND_OUTPUT_BYTES
        ):
            return CheckResult(
                check_id=check.check_id,
                argv=check.argv,
                argv_hash=argv_hash,
                exit_code=completed.returncode,
                elapsed_seconds=time.monotonic() - started,
                stdout_hash=hashlib.sha256(completed.stdout).hexdigest(),
                stderr_hash=hashlib.sha256(completed.stderr).hexdigest(),
                passed=False,
                error="check output exceeded one MiB",
            )
        return CheckResult(
            check_id=check.check_id,
            argv=check.argv,
            argv_hash=argv_hash,
            exit_code=completed.returncode,
            elapsed_seconds=time.monotonic() - started,
            stdout_hash=hashlib.sha256(completed.stdout).hexdigest(),
            stderr_hash=hashlib.sha256(completed.stderr).hexdigest(),
            passed=completed.returncode == 0,
            error=None if completed.returncode == 0 else "check returned a non-zero exit",
        )

    def prepare(
        self,
        proposal: Proposal,
        campaign: CampaignSpec,
        *,
        incumbent_commit: str,
        base_config: Mapping[str, Any] | None = None,
    ) -> PreparationRecord:
        started_at = timestamp_text(datetime.now(timezone.utc))
        report = self.enforcer.validate(
            proposal,
            campaign,
            incumbent_commit=incumbent_commit,
        )
        if not report.accepted:
            return self._record(
                status=PreparationStatus.REJECTED,
                proposal=proposal,
                report=report,
                incumbent_commit=incumbent_commit,
                errors=tuple(item.message for item in report.violations),
                started_at=started_at,
            )

        materialized: MaterializedConfig | None = None
        if proposal.edit_mode == EditMode.CONFIG_ONLY:
            if base_config is None:
                return self._record(
                    status=PreparationStatus.FAILED,
                    proposal=proposal,
                    report=report,
                    incumbent_commit=incumbent_commit,
                    errors=("config proposal requires a frozen base configuration",),
                    started_at=started_at,
                )
            try:
                materialized = materialize_config(
                    proposal,
                    campaign,
                    base_config,
                    incumbent_commit=incumbent_commit,
                )
            except ContractError as error:
                return self._record(
                    status=PreparationStatus.FAILED,
                    proposal=proposal,
                    report=report,
                    incumbent_commit=incumbent_commit,
                    errors=(str(error),),
                    started_at=started_at,
                )

        stable_head: str | None = None
        branch_name: str | None = None
        worktree: Path | None = None
        checks: list[CheckResult] = []
        errors: list[str] = []
        candidate_commit: str | None = None
        candidate_tree: str | None = None
        staged_diff_hash: str | None = None
        changed_paths: tuple[str, ...] = ()
        try:
            self._ensure_clean_stable_repository()
            stable_head = self._head()
            self._verify_commit(incumbent_commit)
            branch_name, worktree = self._branch_and_path(
                self.worktree_root,
                campaign.campaign_id,
                proposal.proposal_id,
            )
            self._branch_must_not_exist(branch_name)
            if worktree.exists():
                raise GitOperationError("hypothesis worktree path already exists")
            self._git(
                (
                    "-c",
                    "core.hooksPath=/dev/null",
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    str(worktree),
                    incumbent_commit,
                )
            )
            if proposal.edit_mode == EditMode.ACTOR_OBJECTIVE_CODE:
                for path in proposal.changed_paths:
                    self._safe_target(worktree, path)
                patch = (proposal.unified_diff or "").encode("utf-8")
                self._git(
                    ("apply", "--check", "--whitespace=error-all", "-"),
                    cwd=worktree,
                    input_bytes=patch,
                )
                self._git(
                    ("apply", "--whitespace=error-all", "-"),
                    cwd=worktree,
                    input_bytes=patch,
                )
            else:
                assert materialized is not None
                target = self._safe_target(worktree, materialized.target_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(materialized.rendered_json, encoding="utf-8")

            changed_paths = self._verify_exact_changes(
                worktree, proposal.changed_paths
            )
            violations = self._validate_candidate_content(
                proposal, worktree, materialized
            )
            if violations:
                raise GitOperationError(self._violation_message(violations))

            if proposal.edit_mode == EditMode.ACTOR_OBJECTIVE_CODE:
                if self.objective_check is None:
                    raise GitOperationError(
                        "code candidates require the mandatory M6 objective check"
                    )
                objective_result = self._run_check(self.objective_check, worktree)
                checks.append(objective_result)
                if not objective_result.passed:
                    raise GitOperationError("mandatory M6 objective check failed")

            for check_id in proposal.requested_tests:
                result = self._run_check(self.trusted_checks[check_id], worktree)
                checks.append(result)
                if not result.passed:
                    raise GitOperationError(f"trusted check failed: {check_id}")

            changed_paths = self._verify_exact_changes(
                worktree, proposal.changed_paths
            )
            violations = self._validate_candidate_content(
                proposal, worktree, materialized
            )
            if violations:
                raise GitOperationError(self._violation_message(violations))

            self._git(("add", "--", *changed_paths), cwd=worktree)
            staged = self._git(
                ("diff", "--cached", "--name-only", "--no-renames", "-z"),
                cwd=worktree,
            ).stdout_paths()
            if tuple(sorted(staged)) != tuple(sorted(changed_paths)):
                raise GitOperationError("staged paths do not match validated paths")
            self._git(("diff", "--cached", "--check"), cwd=worktree)
            staged_diff = self._git(
                ("diff", "--cached", "--binary", "--no-ext-diff"), cwd=worktree
            ).stdout
            staged_diff_hash = hashlib.sha256(staged_diff).hexdigest()
            self._git(
                (
                    "-c",
                    "user.name=ENPIRE Supervisor",
                    "-c",
                    "user.email=supervisor@invalid.local",
                    "-c",
                    "commit.gpgSign=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "--no-verify",
                    "-m",
                    f"experiment: {proposal.proposal_id}",
                ),
                cwd=worktree,
            )
            candidate_commit = self._head(worktree)
            candidate_tree = self._git(
                ("rev-parse", "HEAD^{tree}"), cwd=worktree
            ).stdout_text().strip()
            if self._changed_paths(worktree):
                raise GitOperationError("candidate worktree is not clean after commit")
        except (GitOperationError, OSError) as error:
            errors.append(str(error))

        stable_after = self._head()
        if stable_head is not None and stable_after != stable_head:
            errors.append("stable repository HEAD moved during candidate preparation")
        status = PreparationStatus.FAILED if errors else PreparationStatus.READY
        return self._record(
            status=status,
            proposal=proposal,
            report=report,
            incumbent_commit=incumbent_commit,
            stable_head_before=stable_head,
            stable_head_after=stable_after,
            branch_name=branch_name,
            worktree_path=str(worktree) if worktree is not None else None,
            candidate_commit=candidate_commit,
            candidate_tree_hash=candidate_tree,
            staged_diff_hash=staged_diff_hash,
            materialized_config_hash=(
                materialized.fingerprint() if materialized is not None else None
            ),
            base_config_hash=(
                materialized.base_config_hash if materialized is not None else None
            ),
            overrides_hash=(
                materialized.overrides_hash if materialized is not None else None
            ),
            resolved_config_hash=(
                materialized.resolved_config_hash if materialized is not None else None
            ),
            changed_paths=changed_paths,
            checks=tuple(checks),
            errors=tuple(errors),
            started_at=started_at,
        )

    @staticmethod
    def _violation_message(violations: Sequence[PolicyViolation]) -> str:
        return "candidate source policy rejected: " + ", ".join(
            f"{item.code}:{item.path or '-'}" for item in violations
        )

    @staticmethod
    def _record(
        *,
        status: PreparationStatus,
        proposal: Proposal,
        report: ValidationReport,
        incumbent_commit: str,
        errors: tuple[str, ...],
        started_at: str,
        stable_head_before: str | None = None,
        stable_head_after: str | None = None,
        branch_name: str | None = None,
        worktree_path: str | None = None,
        candidate_commit: str | None = None,
        candidate_tree_hash: str | None = None,
        staged_diff_hash: str | None = None,
        materialized_config_hash: str | None = None,
        base_config_hash: str | None = None,
        overrides_hash: str | None = None,
        resolved_config_hash: str | None = None,
        changed_paths: tuple[str, ...] = (),
        checks: tuple[CheckResult, ...] = (),
    ) -> PreparationRecord:
        return PreparationRecord(
            schema_version=SCHEMA_VERSION,
            status=status,
            campaign_id=report.campaign_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.fingerprint(),
            validation_hash=report.fingerprint(),
            validation_accepted=report.accepted,
            base_commit=require_git_commit(incumbent_commit, "record.base_commit"),
            stable_head_before=stable_head_before,
            stable_head_after=stable_head_after,
            branch_name=branch_name,
            worktree_path=worktree_path,
            candidate_commit=candidate_commit,
            candidate_tree_hash=candidate_tree_hash,
            staged_diff_hash=staged_diff_hash,
            materialized_config_hash=materialized_config_hash,
            base_config_hash=base_config_hash,
            overrides_hash=overrides_hash,
            resolved_config_hash=resolved_config_hash,
            changed_paths=changed_paths,
            checks=checks,
            errors=errors,
            started_at=started_at,
            completed_at=timestamp_text(datetime.now(timezone.utc)),
        )


@dataclass(frozen=True)
class _DecodedGitResult:
    return_code: int
    stdout: bytes
    stderr: bytes

    def stdout_text(self) -> str:
        try:
            return self.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GitOperationError("Git output is not UTF-8") from error

    def stdout_paths(self) -> tuple[str, ...]:
        paths: list[str] = []
        for raw in self.stdout.split(b"\x00"):
            if not raw:
                continue
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise GitOperationError("Git path output is not UTF-8") from error
            paths.append(require_safe_relative_path(decoded, "Git output path"))
        return tuple(paths)


def _pure_path_parts(path: str) -> tuple[str, ...]:
    """Return already-validated POSIX components without host separator ambiguity."""

    return tuple(path.split("/"))


def append_preparation_to_ledger(
    ledger: EventLedger,
    record: PreparationRecord,
    *,
    actor: str = "git-experiment-manager",
    at: datetime | None = None,
) -> tuple[LedgerEvent, ...]:
    """Idempotently bind a preparation outcome to the M1 trial lifecycle."""

    if ledger.entity_type != EntityType.TRIAL:
        raise GitOperationError("preparation records require a trial ledger")
    if ledger.campaign_id != record.campaign_id:
        raise GitOperationError("preparation record campaign does not match ledger")
    snapshot = ledger.read()
    preparation_hash = record.fingerprint()
    if record.status == PreparationStatus.READY:
        targets = (TrialState.PROPOSAL_VALIDATED, TrialState.QUEUED)
    elif record.validation_accepted:
        targets = (TrialState.PROPOSAL_VALIDATED, TrialState.FAILED)
    else:
        targets = (TrialState.FAILED,)

    final_target = targets[-1]
    if snapshot.state == final_target:
        if not snapshot.events:
            raise GitOperationError("terminal trial ledger has no events")
        stored_hash = snapshot.events[-1].metadata.get("preparation_hash")
        if stored_hash != preparation_hash:
            raise GitOperationError(
                "trial ledger already contains a different preparation outcome"
            )
        return ()

    if snapshot.state == TrialState.PROPOSING:
        next_index = 0
    elif (
        snapshot.state == TrialState.PROPOSAL_VALIDATED
        and targets[0] == TrialState.PROPOSAL_VALIDATED
    ):
        prior = snapshot.events[-1].metadata
        if (
            prior.get("proposal_hash") != record.proposal_hash
            or prior.get("validation_hash") != record.validation_hash
        ):
            raise GitOperationError(
                "proposal-validated ledger event belongs to a different preparation"
            )
        next_index = 1
    else:
        raise GitOperationError(
            f"trial ledger state {snapshot.state.value!r} cannot accept preparation"
        )

    events: list[LedgerEvent] = []
    event_time = at or datetime.now(timezone.utc)
    for target in targets[next_index:]:
        is_final = target == final_target
        metadata: dict[str, Any] = {
            "proposal_hash": record.proposal_hash,
            "validation_hash": record.validation_hash,
        }
        if is_final:
            metadata.update(
                preparation_hash=preparation_hash,
                preparation=record.to_dict(),
            )
        events.append(
            ledger.append_transition(
                target,
                actor=actor,
                reason=(
                    "candidate is validated and ready for a worker"
                    if target == TrialState.QUEUED
                    else "proposal passed static validation"
                    if target == TrialState.PROPOSAL_VALIDATED
                    else "proposal or candidate preparation failed"
                ),
                at=event_time,
                metadata=metadata,
            )
        )
    return tuple(events)
