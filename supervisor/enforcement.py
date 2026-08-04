"""Independent proposal enforcement and deterministic config materialization."""

from __future__ import annotations

import ast
import copy
import shlex
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    parse_decimal,
    require_identifier,
    require_safe_relative_path,
)
from supervisor.contracts import SCHEMA_VERSION, CampaignSpec, EditMode
from supervisor.proposals import Proposal
from supervisor.objective_validation import (
    OBJECTIVE_RELATIVE_PATH,
    validate_actor_objective_source,
)


POLICY_VERSION = "m6-enforcement-v2"
MAX_CANDIDATE_FILE_BYTES = 131_072
MAX_CHANGED_FILES = 1


class PolicyError(ContractError):
    """Raised when an enforcement policy or materialization input is invalid."""


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    message: str
    path: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.code, "violation.code")
        if not isinstance(self.message, str) or not self.message:
            raise PolicyError("violation.message must be non-empty text")
        if self.path is not None:
            require_safe_relative_path(self.path, "violation.path")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True)
class PatchFile:
    path: str
    hunk_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "hunk_count": self.hunk_count}


@dataclass(frozen=True)
class ValidationReport:
    schema_version: int
    policy_version: str
    campaign_id: str
    campaign_hash: str
    proposal_id: str
    proposal_hash: str
    incumbent_commit: str
    accepted: bool
    parsed_paths: tuple[str, ...]
    violations: tuple[PolicyViolation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "campaign_id": self.campaign_id,
            "campaign_hash": self.campaign_hash,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "incumbent_commit": self.incumbent_commit,
            "accepted": self.accepted,
            "parsed_paths": list(self.parsed_paths),
            "violations": [item.to_dict() for item in self.violations],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class MaterializedConfig:
    target_path: str
    base_config_hash: str
    overrides_hash: str
    resolved_config_hash: str
    rendered_json: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "base_config_hash": self.base_config_hash,
            "overrides_hash": self.overrides_hash,
            "resolved_config_hash": self.resolved_config_hash,
            "rendered_json": self.rendered_json,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class EnforcementPolicy:
    policy_version: str
    trusted_test_ids: frozenset[str]
    allowed_import_roots: frozenset[str]
    max_candidate_file_bytes: int = MAX_CANDIDATE_FILE_BYTES
    max_changed_files: int = MAX_CHANGED_FILES

    @classmethod
    def create(
        cls,
        *,
        trusted_test_ids: Sequence[str],
        allowed_import_roots: Sequence[str] = (
            "collections",
            "dataclasses",
            "functools",
            "math",
            "torch",
            "typing",
        ),
        policy_version: str = POLICY_VERSION,
        max_candidate_file_bytes: int = MAX_CANDIDATE_FILE_BYTES,
        max_changed_files: int = MAX_CHANGED_FILES,
    ) -> "EnforcementPolicy":
        tests = frozenset(
            require_identifier(item, "policy.trusted_test_ids")
            for item in trusted_test_ids
        )
        imports = frozenset(
            require_identifier(item, "policy.allowed_import_roots")
            for item in allowed_import_roots
        )
        if not tests:
            raise PolicyError("policy requires at least one trusted test ID")
        for value, field in (
            (max_candidate_file_bytes, "max_candidate_file_bytes"),
            (max_changed_files, "max_changed_files"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PolicyError(f"policy.{field} must be a positive integer")
        return cls(
            policy_version=require_identifier(policy_version, "policy.policy_version"),
            trusted_test_ids=tests,
            allowed_import_roots=imports,
            max_candidate_file_bytes=max_candidate_file_bytes,
            max_changed_files=max_changed_files,
        )


FORBIDDEN_DIFF_PREFIXES = (
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "GIT binary patch",
    "Binary files ",
)


def _header_path(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise PolicyError(f"{field} must begin with {prefix!r}")
    path = require_safe_relative_path(value[len(prefix) :], field)
    if PurePosixPath(path).as_posix() != path:
        raise PolicyError(f"{field} must use canonical POSIX syntax")
    return path


def parse_unified_diff(diff: str) -> tuple[PatchFile, ...]:
    """Parse the intentionally narrow text-diff subset accepted by M3."""

    lines = diff.splitlines()
    if not lines:
        raise PolicyError("patch is empty")
    files: list[PatchFile] = []
    current_path: str | None = None
    old_header = False
    new_header = False
    hunk_count = 0

    def finish() -> None:
        nonlocal current_path, old_header, new_header, hunk_count
        if current_path is None:
            return
        if not old_header or not new_header or hunk_count == 0:
            raise PolicyError(
                f"patch for {current_path!r} requires matching ---/+++ headers and a hunk"
            )
        files.append(PatchFile(current_path, hunk_count))
        current_path = None
        old_header = False
        new_header = False
        hunk_count = 0

    for line in lines:
        if line.startswith("diff --git "):
            finish()
            try:
                tokens = shlex.split(line)
            except ValueError as error:
                raise PolicyError("diff header contains invalid quoting") from error
            if len(tokens) != 4 or tokens[:2] != ["diff", "--git"]:
                raise PolicyError("diff header must name exactly one old and new path")
            old_path = _header_path(tokens[2], "a/", "diff old path")
            new_path = _header_path(tokens[3], "b/", "diff new path")
            if old_path != new_path:
                raise PolicyError("renames and copies are forbidden")
            current_path = old_path
            continue
        if current_path is None:
            raise PolicyError("patch content precedes the first diff header")
        if line.startswith(FORBIDDEN_DIFF_PREFIXES):
            raise PolicyError(f"forbidden diff metadata for {current_path!r}: {line}")
        if "Subproject commit " in line or " 160000" in line:
            raise PolicyError("submodule changes are forbidden")
        if line.startswith("--- "):
            if old_header:
                raise PolicyError("duplicate old-file header")
            if _header_path(line[4:], "a/", "--- path") != current_path:
                raise PolicyError("old-file header does not match diff header")
            old_header = True
        elif line.startswith("+++ "):
            if not old_header or new_header:
                raise PolicyError("new-file header is missing, duplicated, or out of order")
            if _header_path(line[4:], "b/", "+++ path") != current_path:
                raise PolicyError("new-file header does not match diff header")
            new_header = True
        elif line.startswith("@@"):
            if not old_header or not new_header:
                raise PolicyError("patch hunk precedes file headers")
            hunk_count += 1
    finish()
    paths = [item.path for item in files]
    if len(set(paths)) != len(paths):
        raise PolicyError("patch contains duplicate file sections")
    return tuple(files)


class _SourcePolicyVisitor(ast.NodeVisitor):
    FORBIDDEN_CALLS = {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
    FORBIDDEN_ATTRIBUTES = {
        "Popen",
        "call",
        "check_call",
        "check_output",
        "environ",
        "getenv",
        "popen",
        "run",
        "system",
    }
    FORBIDDEN_DUNDER_ATTRIBUTES = {
        "__bases__",
        "__builtins__",
        "__class__",
        "__code__",
        "__globals__",
        "__mro__",
        "__subclasses__",
    }

    def __init__(self, allowed_import_roots: frozenset[str]) -> None:
        self.allowed_import_roots = allowed_import_roots
        self.violations: list[PolicyViolation] = []

    def reject(self, code: str, message: str) -> None:
        self.violations.append(PolicyViolation(code, message))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root not in self.allowed_import_roots:
                self.reject("forbidden_import", f"import root {root!r} is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.reject("relative_import", "relative imports are forbidden")
        root = (node.module or "").split(".", 1)[0]
        if root not in self.allowed_import_roots:
            self.reject("forbidden_import", f"import root {root!r} is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_CALLS:
            self.reject("forbidden_call", f"call to {node.func.id!r} is forbidden")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in self.FORBIDDEN_ATTRIBUTES
        ):
            self.reject("forbidden_call", f"call to attribute {node.func.attr!r} is forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in self.FORBIDDEN_DUNDER_ATTRIBUTES:
            self.reject("dunder_escape", f"attribute {node.attr!r} is forbidden")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "__builtins__":
            self.reject("dunder_escape", "name '__builtins__' is forbidden")
        self.generic_visit(node)


def validate_python_source(
    path: str,
    content: bytes,
    policy: EnforcementPolicy,
) -> tuple[PolicyViolation, ...]:
    path = require_safe_relative_path(path, "candidate source path")
    if not path.endswith(".py"):
        return (PolicyViolation("non_python_code", "code target must be a Python file", path),)
    if len(content) > policy.max_candidate_file_bytes:
        return (
            PolicyViolation(
                "file_too_large",
                f"candidate file exceeds {policy.max_candidate_file_bytes} bytes",
                path,
            ),
        )
    if b"\x00" in content:
        return (PolicyViolation("binary_source", "candidate source contains NUL bytes", path),)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return (PolicyViolation("non_utf8", "candidate source is not UTF-8", path),)
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return (
            PolicyViolation(
                "syntax_error",
                f"candidate source does not parse at line {error.lineno}",
                path,
            ),
        )
    visitor = _SourcePolicyVisitor(policy.allowed_import_roots)
    visitor.visit(tree)
    violations = [
        PolicyViolation(item.code, item.message, path) for item in visitor.violations
    ]
    if path.endswith("actor_objective.py"):
        violations.extend(
            PolicyViolation(item.code, item.message, path)
            for item in validate_actor_objective_source(content)
        )
    return tuple(violations)


class ProposalEnforcer:
    def __init__(self, policy: EnforcementPolicy) -> None:
        self.policy = policy

    def validate(
        self,
        proposal: Proposal,
        campaign: CampaignSpec,
        *,
        incumbent_commit: str,
    ) -> ValidationReport:
        violations: list[PolicyViolation] = []
        parsed_paths: tuple[str, ...] = ()
        try:
            proposal.validate_for_campaign(
                campaign,
                incumbent_commit=incumbent_commit,
            )
        except ContractError as error:
            violations.append(PolicyViolation("proposal_contract", str(error)))

        unknown_tests = sorted(
            set(proposal.requested_tests) - self.policy.trusted_test_ids
        )
        if unknown_tests:
            violations.append(
                PolicyViolation(
                    "untrusted_test",
                    f"proposal requested tests outside the trusted registry: {unknown_tests}",
                )
            )
        if len(proposal.changed_paths) > self.policy.max_changed_files:
            violations.append(
                PolicyViolation(
                    "too_many_files",
                    f"proposal exceeds {self.policy.max_changed_files} changed file(s)",
                )
            )
        for path in proposal.changed_paths:
            if PurePosixPath(path).as_posix() != path:
                violations.append(
                    PolicyViolation(
                        "noncanonical_path",
                        "proposal paths must use canonical POSIX syntax",
                        path,
                    )
                )
        self._validate_budget(proposal, campaign, violations)

        if proposal.edit_mode == EditMode.CONFIG_ONLY:
            if len(proposal.changed_paths) != 1 or not proposal.changed_paths[0].endswith(
                ".json"
            ):
                violations.append(
                    PolicyViolation(
                        "config_target",
                        "config-only M3 proposals require exactly one JSON target",
                    )
                )
            parsed_paths = proposal.changed_paths
        elif proposal.unified_diff is not None:
            try:
                parsed = parse_unified_diff(proposal.unified_diff)
                parsed_paths = tuple(item.path for item in parsed)
            except PolicyError as error:
                violations.append(PolicyViolation("invalid_diff", str(error)))
            if parsed_paths and set(parsed_paths) != set(proposal.changed_paths):
                violations.append(
                    PolicyViolation(
                        "path_mismatch",
                        "parsed diff paths do not exactly match declared changed paths",
                    )
                )
            for path in parsed_paths:
                if path != OBJECTIVE_RELATIVE_PATH:
                    violations.append(
                        PolicyViolation(
                            "objective_target",
                            "code mode may edit only the project-owned actor objective",
                            path,
                        )
                    )

        return ValidationReport(
            schema_version=SCHEMA_VERSION,
            policy_version=self.policy.policy_version,
            campaign_id=campaign.campaign_id,
            campaign_hash=campaign.fingerprint(),
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.fingerprint(),
            incumbent_commit=incumbent_commit,
            accepted=not violations,
            parsed_paths=parsed_paths,
            violations=tuple(violations),
        )

    @staticmethod
    def _validate_budget(
        proposal: Proposal,
        campaign: CampaignSpec,
        violations: list[PolicyViolation],
    ) -> None:
        requested = proposal.estimated_budget
        limits = campaign.budget
        comparisons: tuple[tuple[Decimal | int, Decimal | int, str], ...] = (
            (
                requested.wall_time_seconds,
                limits.max_wall_time_seconds,
                "wall time",
            ),
            (
                parse_decimal(requested.gpu_cost_usd, "proposal GPU cost"),
                limits.gpu_cost(),
                "GPU cost",
            ),
            (
                parse_decimal(requested.llm_cost_usd, "proposal LLM cost"),
                limits.llm_cost(),
                "LLM cost",
            ),
        )
        for value, limit, label in comparisons:
            if value > limit:
                violations.append(
                    PolicyViolation(
                        "budget_exceeded",
                        f"proposal estimated {label} exceeds the campaign cap",
                    )
                )

    def validate_candidate_source(
        self,
        path: str,
        content: bytes,
    ) -> tuple[PolicyViolation, ...]:
        return validate_python_source(path, content, self.policy)


def materialize_config(
    proposal: Proposal,
    campaign: CampaignSpec,
    base_config: Mapping[str, Any],
    *,
    incumbent_commit: str,
) -> MaterializedConfig:
    proposal.validate_for_campaign(campaign, incumbent_commit=incumbent_commit)
    if proposal.edit_mode != EditMode.CONFIG_ONLY or proposal.config_overrides is None:
        raise PolicyError("materialization requires a config-only proposal")
    if len(proposal.changed_paths) != 1:
        raise PolicyError("materialization requires exactly one target path")
    if not isinstance(base_config, Mapping):
        raise PolicyError("base config must be an object")
    try:
        resolved = copy.deepcopy(dict(base_config))
        canonical_json(resolved)
    except (TypeError, ContractError) as error:
        raise PolicyError("base config must be canonical JSON") from error

    for dotted_key, value in sorted(proposal.config_overrides.items()):
        parts = dotted_key.split(".")
        if not parts or any(not part for part in parts):
            raise PolicyError(f"invalid dotted configuration key: {dotted_key!r}")
        cursor: Any = resolved
        for part in parts[:-1]:
            if not isinstance(cursor, dict) or part not in cursor:
                raise PolicyError(
                    f"configuration key does not exist in the frozen base: {dotted_key!r}"
                )
            cursor = cursor[part]
        leaf = parts[-1]
        if not isinstance(cursor, dict) or leaf not in cursor:
            raise PolicyError(
                f"configuration key does not exist in the frozen base: {dotted_key!r}"
            )
        if isinstance(cursor[leaf], (dict, list)):
            raise PolicyError(f"configuration key is not a scalar: {dotted_key!r}")
        cursor[leaf] = value

    rendered = canonical_json(resolved)
    overrides = dict(sorted(proposal.config_overrides.items()))
    return MaterializedConfig(
        target_path=proposal.changed_paths[0],
        base_config_hash=fingerprint(dict(base_config)),
        overrides_hash=fingerprint(overrides),
        resolved_config_hash=fingerprint(resolved),
        rendered_json=rendered,
    )
