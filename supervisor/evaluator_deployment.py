"""Fail-closed checks for G0 evaluator custody and deployment rehearsals."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from supervisor.canonical import fingerprint, require_sha256
from supervisor.evaluator_integrity import ResetSetArtifact


class EvaluatorDeploymentError(ValueError):
    """Raised when evaluator custody or isolation is weaker than declared."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _outside(path: Path, repository: Path) -> bool:
    try:
        path.relative_to(repository)
        return False
    except ValueError:
        return True


def _path_fingerprint(path: Path) -> str:
    return hashlib.sha256(os.fsencode(str(path))).hexdigest()


def _require_external_real_path(path: Path, repository: Path, field: str) -> Path:
    if path.is_symlink():
        raise EvaluatorDeploymentError(f"{field} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not _outside(resolved, repository.resolve()):
        raise EvaluatorDeploymentError(f"{field} must be outside the repository")
    return resolved


def _assert_read_only_tree(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        if path.stat().st_mode & 0o222:
            raise EvaluatorDeploymentError("evaluator bundle contains a writable path")


def build_local_isolation_receipt(
    *,
    repository: Path,
    private_final: Path,
    bundle_root: Path,
    bundle_manifest: dict[str, Any],
    ledger_root: Path,
    anchor_root: Path,
) -> dict[str, Any]:
    """Audit a same-user rehearsal without claiming production isolation."""

    repo = repository.resolve(strict=True)
    final_path = _require_external_real_path(private_final, repo, "private final artifact")
    bundle = _require_external_real_path(bundle_root, repo, "evaluator bundle")
    ledger = _require_external_real_path(ledger_root, repo, "ledger root")
    anchor = _require_external_real_path(anchor_root, repo, "anchor root")
    if not final_path.is_file():
        raise EvaluatorDeploymentError("private final artifact must be a regular file")
    if not all(path.is_dir() for path in (bundle, ledger, anchor)):
        raise EvaluatorDeploymentError("bundle, ledger, and anchor roots must be directories")
    if ledger == anchor or ledger in anchor.parents or anchor in ledger.parents:
        raise EvaluatorDeploymentError("ledger and anchor roots must be distinct and unnested")
    if final_path.is_relative_to(bundle) or bundle.is_relative_to(final_path.parent):
        raise EvaluatorDeploymentError("final artifact and evaluator bundle must be separate")
    final_mode = stat.S_IMODE(final_path.stat().st_mode)
    parent_mode = stat.S_IMODE(final_path.parent.stat().st_mode)
    if final_mode & 0o277:
        raise EvaluatorDeploymentError("private final artifact must be owner-read-only")
    if parent_mode & 0o077 or parent_mode & 0o200:
        raise EvaluatorDeploymentError("private final parent must be owner-only and non-writable")
    _assert_read_only_tree(bundle)

    if not isinstance(bundle_manifest, dict) or set(bundle_manifest) != {"payload", "sha256"}:
        raise EvaluatorDeploymentError("bundle manifest envelope is invalid")
    if fingerprint(bundle_manifest["payload"]) != bundle_manifest["sha256"]:
        raise EvaluatorDeploymentError("bundle manifest envelope hash mismatch")
    for field in ("evaluation_authorized", "gpu_execution_authorized", "promotion_authorized"):
        if bundle_manifest["payload"].get(field) is not False:
            raise EvaluatorDeploymentError("bundle manifest grants forbidden authority")

    reset = ResetSetArtifact.from_dict(json.loads(final_path.read_text(encoding="utf-8")))
    if reset.role != "final":
        raise EvaluatorDeploymentError("custody artifact must have final role")
    same_owner = len({os.stat(path).st_uid for path in (repo, final_path, bundle, ledger, anchor)}) == 1
    payload = {
        "schema_version": 1,
        "status": "pass_local_isolation_rehearsal",
        "claim_boundary": "same-user-mode-bits-only-not-production-custody",
        "final_reset_artifact": {
            "artifact_sha256": reset.fingerprint(),
            "file_sha256": _sha256(final_path),
            "size_bytes": final_path.stat().st_size,
            "count": len(reset.reset_ids),
            "role": reset.role,
            "mode_octal": format(final_mode, "04o"),
            "path_sha256": _path_fingerprint(final_path),
            "ordered_ids_emitted": False,
        },
        "evaluator_bundle": {
            "manifest_sha256": bundle_manifest["sha256"],
            "path_sha256": _path_fingerprint(bundle),
            "manifest_verified": True,
            "read_only_tree_verified": True,
        },
        "storage_separation": {
            "all_paths_outside_repository": True,
            "final_and_bundle_distinct": True,
            "ledger_and_anchor_distinct": True,
            "independent_os_principal": not same_owner,
            "independent_failure_domain": False,
            "immutable_mount": False,
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable_sha256": _sha256(Path(sys.executable).resolve()),
        },
        "evaluation_executed": False,
        "scientific_evaluation_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
        "production_custody_accepted": False,
        "production_deployment_accepted": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


def verify_local_isolation_receipt(value: Any, expected_final_sha256: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise EvaluatorDeploymentError("isolation receipt envelope is invalid")
    payload = value["payload"]
    if fingerprint(payload) != value["sha256"]:
        raise EvaluatorDeploymentError("isolation receipt hash mismatch")
    if payload.get("status") != "pass_local_isolation_rehearsal":
        raise EvaluatorDeploymentError("isolation rehearsal did not pass")
    if payload.get("claim_boundary") != "same-user-mode-bits-only-not-production-custody":
        raise EvaluatorDeploymentError("isolation receipt claim boundary is invalid")
    if payload.get("final_reset_artifact", {}).get("artifact_sha256") != expected_final_sha256:
        raise EvaluatorDeploymentError("isolation receipt final artifact mismatch")
    if payload.get("final_reset_artifact", {}).get("ordered_ids_emitted") is not False:
        raise EvaluatorDeploymentError("isolation receipt disclosed final IDs")
    for field in (
        "evaluation_executed",
        "scientific_evaluation_authorized",
        "campaign_activation_authorized",
        "gpu_execution_authorized",
        "paid_execution_authorized",
        "provider_call_authorized",
        "model_egress_authorized",
        "promotion_authorized",
        "production_custody_accepted",
        "production_deployment_accepted",
    ):
        if payload.get(field) is not False:
            raise EvaluatorDeploymentError("isolation receipt exceeds rehearsal authority")
    return value


def _exact_payload(value: Any, fields: set[str], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise EvaluatorDeploymentError(f"{label} envelope is invalid")
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != fields:
        raise EvaluatorDeploymentError(f"{label} fields are invalid")
    if fingerprint(payload) != value["sha256"]:
        raise EvaluatorDeploymentError(f"{label} hash mismatch")
    return value, payload


def _require_utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvaluatorDeploymentError(f"{field} must be UTC")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise EvaluatorDeploymentError(f"{field} is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise EvaluatorDeploymentError(f"{field} must be UTC")
    return value


def validate_production_custody_record(
    value: Any, expected_final_sha256: str
) -> dict[str, Any]:
    """Validate a public receipt without consuming or revealing final IDs."""

    envelope, payload = _exact_payload(
        value,
        {
            "schema_version", "record_kind", "custody_class", "artifact_sha256",
            "artifact_count", "custodian_principal", "storage_identity_sha256",
            "independent_os_principal", "independent_failure_domain",
            "immutable_or_evaluator_only_storage", "candidate_access",
            "proposer_access", "worker_access", "ordered_ids_emitted",
            "independent_verifier", "verification_timestamp_utc",
            "evaluation_authorized", "gpu_execution_authorized",
            "promotion_authorized",
        },
        "production custody record",
    )
    if payload["schema_version"] != 1 or payload["record_kind"] != "g0-final-reset-custody":
        raise EvaluatorDeploymentError("production custody record identity is invalid")
    if payload["custody_class"] != "production-independent":
        raise EvaluatorDeploymentError("production custody must be independently controlled")
    expected_final = require_sha256(expected_final_sha256, "expected final artifact")
    artifact_sha256 = require_sha256(payload["artifact_sha256"], "custodied final artifact")
    if artifact_sha256 != expected_final or payload["artifact_count"] != 256:
        raise EvaluatorDeploymentError("production custody artifact identity is invalid")
    for field in ("custodian_principal", "independent_verifier"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise EvaluatorDeploymentError(f"production custody {field} is missing")
    _require_utc_timestamp(payload["verification_timestamp_utc"], "production custody timestamp")
    require_sha256(payload["storage_identity_sha256"], "production custody storage identity")
    for field in (
        "independent_os_principal", "independent_failure_domain",
        "immutable_or_evaluator_only_storage",
    ):
        if payload[field] is not True:
            raise EvaluatorDeploymentError("production custody isolation is incomplete")
    for field in (
        "candidate_access", "proposer_access", "worker_access", "ordered_ids_emitted",
        "evaluation_authorized", "gpu_execution_authorized", "promotion_authorized",
    ):
        if payload[field] is not False:
            raise EvaluatorDeploymentError("production custody record grants forbidden access")
    return envelope


def validate_production_deployment_record(
    value: Any, *, expected_bundle_sha256: str, expected_custody_record_sha256: str
) -> dict[str, Any]:
    envelope, payload = _exact_payload(
        value,
        {
            "schema_version", "record_kind", "deployment_class",
            "bundle_manifest_sha256", "environment_identity_sha256",
            "custody_record_sha256", "evaluator_principal", "source_read_only",
            "final_input_read_only", "candidate_can_modify_evaluator",
            "candidate_can_read_final_inputs", "ledger_identity_sha256",
            "anchor_identity_sha256", "ledger_anchor_independent_failure_domains",
            "independent_verifier", "verification_timestamp_utc",
            "evaluation_authorized", "gpu_execution_authorized",
            "promotion_authorized",
        },
        "production evaluator deployment record",
    )
    if payload["schema_version"] != 1 or payload["record_kind"] != "g0-production-evaluator":
        raise EvaluatorDeploymentError("production deployment record identity is invalid")
    if payload["deployment_class"] != "production-independent":
        raise EvaluatorDeploymentError("production evaluator must be independently controlled")
    expected_bundle = require_sha256(expected_bundle_sha256, "expected evaluator bundle")
    expected_custody = require_sha256(expected_custody_record_sha256, "expected custody record")
    bundle_sha256 = require_sha256(payload["bundle_manifest_sha256"], "deployed evaluator bundle")
    custody_sha256 = require_sha256(payload["custody_record_sha256"], "deployment custody record")
    if bundle_sha256 != expected_bundle:
        raise EvaluatorDeploymentError("production evaluator bundle identity mismatch")
    if custody_sha256 != expected_custody:
        raise EvaluatorDeploymentError("production evaluator custody record mismatch")
    for field in (
        "environment_identity_sha256", "ledger_identity_sha256", "anchor_identity_sha256",
    ):
        require_sha256(payload[field], f"production deployment {field}")
    if payload["ledger_identity_sha256"] == payload["anchor_identity_sha256"]:
        raise EvaluatorDeploymentError("ledger and anchor identities must differ")
    for field in ("evaluator_principal", "independent_verifier"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise EvaluatorDeploymentError(f"production deployment {field} is missing")
    _require_utc_timestamp(payload["verification_timestamp_utc"], "production deployment timestamp")
    for field in (
        "source_read_only", "final_input_read_only",
        "ledger_anchor_independent_failure_domains",
    ):
        if payload[field] is not True:
            raise EvaluatorDeploymentError("production evaluator isolation is incomplete")
    for field in (
        "candidate_can_modify_evaluator", "candidate_can_read_final_inputs",
        "evaluation_authorized", "gpu_execution_authorized", "promotion_authorized",
    ):
        if payload[field] is not False:
            raise EvaluatorDeploymentError("production deployment grants forbidden access")
    return envelope
