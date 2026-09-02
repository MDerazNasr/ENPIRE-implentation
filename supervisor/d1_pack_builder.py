"""Deterministic D1 Stage-7 pack publication and legacy readiness reporting."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    require_exact_keys,
    require_identifier,
    require_safe_relative_path,
    require_sha256,
)
from supervisor.contracts import ArtifactRef, Decision, SCHEMA_VERSION
from supervisor.d1_gate import D1EvidencePack, REQUIRED_STAGE7_ARTIFACTS


DEFAULT_SOURCE_DIRECTORY = Path("results/d1-evidence-pack")
DEFAULT_BUILD_SPEC = Path("results/d1-stage7/evidence_pack.source.json")
DEFAULT_PACK_OUTPUT = Path("results/d1-stage7/evidence_pack.json")
DEFAULT_READINESS_OUTPUT = Path("results/d1-stage7/readiness.json")
REQUIRED_PAIRED_SEED_COUNT = 3

LEGACY_SOURCE_FILES = (
    "artifact-index.json",
    "cost-resources.csv",
    "fixed-eval-success.svg",
    "raw/candidate-c-corrected-final-summary.json",
    "raw/control-b-completion-summary.md",
    "raw/control-b-gate-report.json",
    "raw/reference-a-matched-metrics.log",
    "raw/stage6r-schedule-resume-gate.json",
    "resume-counter.svg",
    "run-table.csv",
)

ROLE_SOURCE_MAP: Mapping[str, tuple[str, ...]] = {
    "commands": (
        "configs/d1/stage2_5c_reference_h100_chain.yaml",
        "configs/d1/stage2_5d_control_h100_chain.yaml",
        "configs/d1/stage2_6_candidate_modal_multiprocess.yaml",
        "modal_stage6.py",
    ),
    "configs": (
        "configs/d1/stage2_5c_reference_h100_chain.yaml",
        "configs/d1/stage2_5d_control_h100_chain.yaml",
        "configs/d1/stage2_6_candidate_modal_multiprocess.yaml",
        "configs/d1/assets/maniskill_peginsertionside_joint.norm_stats.json",
    ),
    "tracker": ("results/d1-evidence-pack/artifact-index.json",),
    "run-table": ("results/d1-evidence-pack/run-table.csv",),
    "plots": (
        "results/d1-evidence-pack/fixed-eval-success.svg",
        "results/d1-evidence-pack/resume-counter.svg",
    ),
    "cost-report": ("results/d1-evidence-pack/cost-resources.csv",),
    "limitations": (
        "docs/d1-evidence-pack.md",
        "results/d1-evidence-pack/raw/candidate-c-corrected-final-summary.json",
    ),
}


class D1PackBuildError(ContractError):
    """Raised when reviewed inputs cannot produce a canonical D1 pack."""


@dataclass(frozen=True)
class ArtifactSource:
    artifact_id: str
    kind: str
    path: str

    @classmethod
    def from_dict(cls, value: Any, field: str) -> "ArtifactSource":
        data = require_exact_keys(value, field, {"artifact_id", "kind", "path"})
        return cls(
            artifact_id=require_identifier(data["artifact_id"], f"{field}.artifact_id"),
            kind=require_identifier(data["kind"], f"{field}.kind"),
            path=require_safe_relative_path(data["path"], f"{field}.path"),
        )


@dataclass(frozen=True)
class BuildSpec:
    pack: Mapping[str, Any]
    runtime_identity_hashes: Mapping[str, str]
    artifact_sources: tuple[ArtifactSource, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "BuildSpec":
        data = require_exact_keys(
            value,
            "d1_pack_source",
            {"schema_version", "pack", "runtime_identity_hashes", "artifact_sources"},
        )
        if data["schema_version"] != SCHEMA_VERSION:
            raise D1PackBuildError(
                f"d1_pack_source.schema_version must be {SCHEMA_VERSION}"
            )
        pack = require_exact_keys(
            data["pack"],
            "d1_pack_source.pack",
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
            },
        )
        runtime = require_exact_keys(
            data["runtime_identity_hashes"],
            "d1_pack_source.runtime_identity_hashes",
            {"reference", "control", "candidate"},
        )
        runtime_hashes = {
            condition: require_sha256(
                runtime[condition],
                f"d1_pack_source.runtime_identity_hashes.{condition}",
            )
            for condition in ("reference", "control", "candidate")
        }
        raw_sources = data["artifact_sources"]
        if not isinstance(raw_sources, list) or not raw_sources:
            raise D1PackBuildError("d1_pack_source.artifact_sources must be a list")
        sources = tuple(
            ArtifactSource.from_dict(item, f"d1_pack_source.artifact_sources[{index}]")
            for index, item in enumerate(raw_sources)
        )
        return cls(pack=pack, runtime_identity_hashes=runtime_hashes, artifact_sources=sources)


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    category: str
    detail: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "detail": self.detail,
            "evidence": list(self.evidence),
        }


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise D1PackBuildError(
            f"Git command failed: git {' '.join(arguments)}: {detail}"
        )
    return completed.stdout.strip()


def _repository_path(repository: Path, relative: Path | str, field: str) -> tuple[Path, str]:
    text = require_safe_relative_path(Path(relative).as_posix(), field)
    root = repository.resolve()
    target = (root / text).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise D1PackBuildError(f"{field} escapes the repository") from error
    cursor = root
    for part in Path(text).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise D1PackBuildError(f"{field} traverses a symbolic link")
    return target, text


def _require_tracked_clean_file(repository: Path, relative: str, field: str) -> Path:
    target, normalized = _repository_path(repository, relative, field)
    if not target.is_file():
        raise D1PackBuildError(f"{field} does not name an existing regular file")
    tracked = _git(
        repository,
        "ls-files",
        "--error-unmatch",
        "--",
        normalized,
        check=False,
    )
    if not tracked:
        raise D1PackBuildError(f"{field} must be tracked by Git")
    if _git(repository, "status", "--porcelain", "--", normalized):
        raise D1PackBuildError(f"{field} must match the tracked Git version")
    return target


def _require_ancestor(repository: Path, commit: str, field: str) -> None:
    exists = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if exists.returncode != 0:
        raise D1PackBuildError(f"{field} does not exist in the repository")
    completed = subprocess.run(
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise D1PackBuildError(f"{field} must be an ancestor of repository HEAD")


def load_build_spec(repository: Path, source_path: Path = DEFAULT_BUILD_SPEC) -> BuildSpec:
    try:
        source, normalized = _repository_path(repository, source_path, "build source path")
        _require_tracked_clean_file(repository, normalized, "build source path")
        raw = json.loads(source.read_text(encoding="utf-8"))
        return BuildSpec.from_dict(raw)
    except json.JSONDecodeError as error:
        raise D1PackBuildError(f"build source is not valid JSON: {error}") from error
    except OSError as error:
        raise D1PackBuildError(f"build source could not be read: {error}") from error
    except ContractError as error:
        if isinstance(error, D1PackBuildError):
            raise
        raise D1PackBuildError(str(error)) from error


def build_canonical_pack(
    repository: Path,
    *,
    source_path: Path = DEFAULT_BUILD_SPEC,
    output_path: Path = DEFAULT_PACK_OUTPUT,
) -> D1EvidencePack:
    """Build and validate a pack in memory without writing repository state."""

    repository = repository.resolve()
    if not (repository / ".git").exists():
        raise D1PackBuildError("repository must be a Git worktree")
    spec = load_build_spec(repository, source_path)
    if len(set(spec.runtime_identity_hashes.values())) != 1:
        raise D1PackBuildError(
            "Reference, Control, and Candidate runtime identities must match"
        )

    source_ids = [item.artifact_id for item in spec.artifact_sources]
    if len(set(source_ids)) != len(source_ids):
        raise D1PackBuildError("artifact source IDs must be unique")
    missing = sorted(REQUIRED_STAGE7_ARTIFACTS - set(source_ids))
    unexpected = sorted(set(source_ids) - REQUIRED_STAGE7_ARTIFACTS)
    if missing or unexpected:
        raise D1PackBuildError(
            f"artifact source IDs must exactly match the seven required roles; "
            f"missing={missing}, unexpected={unexpected}"
        )

    _, normalized_source = _repository_path(
        repository, source_path, "build source path"
    )
    _, normalized_output = _repository_path(
        repository, output_path, "canonical output path"
    )
    artifacts: list[ArtifactRef] = []
    for item in sorted(spec.artifact_sources, key=lambda value: value.artifact_id):
        if item.path in {normalized_source, normalized_output}:
            raise D1PackBuildError(
                f"artifact source {item.artifact_id} cannot reference the build source or output"
            )
        path = _require_tracked_clean_file(
            repository, item.path, f"artifact source {item.artifact_id}"
        )
        content = path.read_bytes()
        artifacts.append(
            ArtifactRef(
                artifact_id=item.artifact_id,
                kind=item.kind,
                uri=f"git:{item.path}",
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        )

    payload = dict(spec.pack)
    payload["artifacts"] = [item.to_dict() for item in artifacts]
    try:
        pack = D1EvidencePack.from_dict(payload)
    except ContractError as error:
        raise D1PackBuildError(f"canonical D1 pack is invalid: {error}") from error
    if len(pack.campaign.seeds) != REQUIRED_PAIRED_SEED_COUNT:
        raise D1PackBuildError(
            f"canonical publication requires exactly {REQUIRED_PAIRED_SEED_COUNT} paired seeds"
        )
    if not pack.baseline_non_degenerate:
        raise D1PackBuildError("canonical publication requires a non-degenerate baseline")
    if pack.legacy_decision not in {Decision.KEEP, Decision.REVERT}:
        raise D1PackBuildError(
            "canonical publication requires a resolved keep or revert decision"
        )
    for field, commit in (
        ("known_good_commit", pack.known_good_commit),
        ("incumbent_commit", pack.incumbent_commit),
        ("candidate_commit", pack.candidate_commit),
    ):
        _require_ancestor(repository, commit, field)
    return pack


def pack_bytes(pack: D1EvidencePack) -> bytes:
    """Return stable human-reviewable bytes for a validated pack."""

    return (json.dumps(pack.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _tracked(repository: Path, relative: str) -> bool:
    return bool(
        _git(
            repository,
            "ls-files",
            "--error-unmatch",
            "--",
            relative,
            check=False,
        )
    )


def _legacy_inventory(repository: Path) -> list[dict[str, Any]]:
    root = repository / DEFAULT_SOURCE_DIRECTORY
    records: list[dict[str, Any]] = []
    if not root.is_dir():
        return records
    for path in sorted(
        item for item in root.rglob("*") if item.is_file() and not item.is_symlink()
    ):
        relative = path.relative_to(repository).as_posix()
        content = path.read_bytes()
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "tracked": _tracked(repository, relative),
            }
        )
    return records


def _read_legacy_rows(repository: Path) -> list[dict[str, str]]:
    path = repository / DEFAULT_SOURCE_DIRECTORY / "run-table.csv"
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return []


def _read_legacy_index(repository: Path) -> dict[str, Any]:
    path = repository / DEFAULT_SOURCE_DIRECTORY / "artifact-index.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def current_readiness_payload(
    repository: Path,
    *,
    source_path: Path = DEFAULT_BUILD_SPEC,
    output_path: Path = DEFAULT_PACK_OUTPUT,
) -> dict[str, Any]:
    """Describe current legacy evidence without treating it as a canonical pack."""

    repository = repository.resolve()
    inventory = _legacy_inventory(repository)
    inventory_paths = {item["path"] for item in inventory}
    rows = _read_legacy_rows(repository)
    control_seeds = {
        int(item["seed"])
        for item in rows
        if item.get("record_type") == "control"
        and item.get("status") == "complete"
        and item.get("validity", "").startswith("valid_one_seed")
        and item.get("seed", "").isdigit()
    }
    candidate_seeds = {
        int(item["seed"])
        for item in rows
        if item.get("record_type") == "candidate_corrected"
        and item.get("status") == "complete"
        and item.get("validity", "").startswith("valid_one_seed")
        and item.get("seed", "").isdigit()
    }
    paired = sorted(control_seeds & candidate_seeds)
    index = _read_legacy_index(repository)
    index_artifacts = index.get("artifacts", [])
    if not isinstance(index_artifacts, list):
        index_artifacts = []

    issues: list[ReadinessIssue] = []
    expected_inventory = {
        (DEFAULT_SOURCE_DIRECTORY / item).as_posix() for item in LEGACY_SOURCE_FILES
    }
    missing_files = sorted(expected_inventory - inventory_paths)
    untracked_files = sorted(item["path"] for item in inventory if not item["tracked"])
    if missing_files:
        issues.append(
            ReadinessIssue(
                "legacy_source_files_missing",
                "packaging",
                f"Expected source-evidence files are missing: {missing_files}",
                tuple(missing_files),
            )
        )
    if untracked_files:
        issues.append(
            ReadinessIssue(
                "legacy_source_files_untracked",
                "packaging",
                f"Source-evidence files are not tracked: {untracked_files}",
                tuple(untracked_files),
            )
        )

    source_relative = Path(source_path).as_posix()
    if not (repository / source_path).is_file():
        issues.append(
            ReadinessIssue(
                "canonical_source_spec_missing",
                "packaging",
                "The reviewed strict build specification does not exist.",
                (source_relative,),
            )
        )
    if len(paired) != REQUIRED_PAIRED_SEED_COUNT:
        issues.append(
            ReadinessIssue(
                "paired_seed_count_incomplete",
                "scientific",
                f"Found {len(paired)} complete paired seed; exactly "
                f"{REQUIRED_PAIRED_SEED_COUNT} are required.",
                ("results/d1-evidence-pack/run-table.csv",),
            )
        )
    issues.extend(
        (
            ReadinessIssue(
                "approved_seed_values_incomplete",
                "approval",
                "Only seed 2026 is recorded; the other two scientific seed values are not approved in project evidence.",
                ("docs/experiment_matrix.md", "docs/baseline_protocol.md"),
            ),
            ReadinessIssue(
                "runtime_identity_mismatch",
                "scientific",
                "Control and corrected Candidate used different runtime, simulator, renderer, and batching paths.",
                ("results/d1-evidence-pack/raw/candidate-c-corrected-final-summary.json",),
            ),
            ReadinessIssue(
                "reset_set_hash_missing",
                "provenance",
                "The exact 256 reset IDs and their SHA-256 are not exported.",
                ("docs/baseline_protocol.md",),
            ),
            ReadinessIssue(
                "campaign_identity_incomplete",
                "approval",
                "Evaluator version, artifact namespace, max concurrency, and frozen GPU/LLM budget envelope are not approved.",
                ("docs/agent-supervisor/d1-evidence-schema-mapping.md",),
            ),
            ReadinessIssue(
                "reference_provenance_incomplete",
                "provenance",
                "Matched Reference lacks an exact run ID, project commit, command hash, timestamps, elapsed time, and attributable GPU cost.",
                ("results/d1-evidence-pack/raw/reference-a-matched-metrics.log",),
            ),
            ReadinessIssue(
                "candidate_provenance_incomplete",
                "provenance",
                "Corrected Candidate is not bound to exact per-segment project commits, commands, full-chain timestamps, or a local complete archive.",
                ("results/d1-evidence-pack/raw/candidate-c-corrected-final-summary.json",),
            ),
            ReadinessIssue(
                "tracker_artifact_incomplete",
                "packaging",
                "W&B is offline and incomplete across eligible runs; no authoritative canonical tracker artifact exists.",
                ("results/d1-evidence-pack/artifact-index.json",),
            ),
            ReadinessIssue(
                "review_approval_missing",
                "approval",
                "No reviewer-signed strict pack, UTC review time, or resolved keep/revert decision exists.",
                ("docs/d1-evidence-pack.md",),
            ),
        )
    )
    remote_candidate = next(
        (
            item
            for item in index_artifacts
            if isinstance(item, dict)
            and item.get("id") == "candidate-c-corrected-policy"
        ),
        None,
    )
    if isinstance(remote_candidate, dict) and str(remote_candidate.get("path", "")).startswith("/"):
        issues.append(
            ReadinessIssue(
                "candidate_policy_remote_only",
                "packaging",
                "The corrected Candidate policy is indexed by a remote absolute path and is not present in this worktree.",
                ("results/d1-evidence-pack/artifact-index.json",),
            )
        )

    roles = []
    for artifact_id in sorted(REQUIRED_STAGE7_ARTIFACTS):
        sources = ROLE_SOURCE_MAP[artifact_id]
        present = [item for item in sources if (repository / item).is_file()]
        roles.append(
            {
                "artifact_id": artifact_id,
                "coverage": "source-present" if len(present) == len(sources) else "source-partial",
                "sources": list(sources),
                "present_sources": present,
                "canonical_artifact_materialized": False,
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked" if issues else "ready",
        "canonical_pack_exists": (repository / output_path).is_file(),
        "canonical_pack_claimed": False,
        "canonical_source_path": source_relative,
        "canonical_output_path": Path(output_path).as_posix(),
        "source_evidence_directory": DEFAULT_SOURCE_DIRECTORY.as_posix(),
        "source_inventory": inventory,
        "source_inventory_count": len(inventory),
        "source_inventory_bytes": sum(item["size_bytes"] for item in inventory),
        "indexed_evidence_count": len(index_artifacts),
        "artifact_role_coverage": roles,
        "paired_seed_summary": {
            "required_count": REQUIRED_PAIRED_SEED_COUNT,
            "control_seeds": sorted(control_seeds),
            "candidate_seeds": sorted(candidate_seeds),
            "paired_seeds": paired,
            "unapproved_seed_values_inferred": False,
        },
        "tracker_authority": "supplementary-or-unavailable",
        "scientific_conclusion": "INCONCLUSIVE",
        "blockers": [item.to_dict() for item in issues],
    }
    return payload


def readiness_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"payload": dict(payload), "sha256": fingerprint(payload)}


def readiness_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(readiness_envelope(payload), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def verify_readiness_envelope(value: Any) -> dict[str, Any]:
    data = require_exact_keys(value, "readiness envelope", {"payload", "sha256"})
    expected = require_sha256(data["sha256"], "readiness envelope hash")
    if fingerprint(data["payload"]) != expected:
        raise D1PackBuildError("readiness envelope hash does not match its payload")
    if not isinstance(data["payload"], dict):
        raise D1PackBuildError("readiness payload must be an object")
    return data["payload"]


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
