"""Strict, non-authorizing acceptance records for the G0 protocol freeze."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from supervisor.canonical import fingerprint, require_git_commit, require_sha256


class G0AcceptanceError(ValueError):
    """Raised when a canonical G0 acceptance record is incomplete or inconsistent."""


AUTHORITY_FIELDS = (
    "scientific_execution_authorized",
    "campaign_activation_authorized",
    "gpu_execution_authorized",
    "paid_execution_authorized",
    "provider_call_authorized",
    "model_egress_authorized",
    "promotion_authorized",
)


def _envelope(value: Any, fields: set[str], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise G0AcceptanceError(f"{label} envelope is invalid")
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != fields:
        raise G0AcceptanceError(f"{label} fields are invalid")
    if fingerprint(payload) != value["sha256"]:
        raise G0AcceptanceError(f"{label} hash mismatch")
    return value, payload


def _false_authority(payload: dict[str, Any], label: str) -> None:
    for field in AUTHORITY_FIELDS:
        if payload.get(field) is not False:
            raise G0AcceptanceError(f"{label} grants forbidden authority")


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise G0AcceptanceError(f"{field} must be UTC")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise G0AcceptanceError(f"{field} is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise G0AcceptanceError(f"{field} must be UTC")
    return value


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise G0AcceptanceError(f"{field} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise G0AcceptanceError(f"{field} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise G0AcceptanceError(f"{field} must be finite and non-negative")
    return result


def validate_runtime_identity_record(
    value: Any,
    *,
    expected_candidate_sha256: str,
    expected_evaluator_environment_sha256: str,
    expected_development_reset_sha256: str,
    expected_final_reset_sha256: str,
) -> dict[str, Any]:
    envelope, payload = _envelope(
        value,
        {
            "schema_version", "record_kind", "status", "source_candidate_sha256",
            "accepted_by", "accepted_at_utc", "selected_option",
            "scientific_project_commit", "fresh_host_qualification_sha256",
            "fresh_image_qualification_sha256", "fresh_route_qualification_sha256",
            "container_image_sha256", "evaluator_environment_identity_sha256",
            "durable_store_identity_sha256", "task", "rlinf_commit",
            "maniskill_commit", "sapien", "base_model_sha256", "dataset_identity",
            "dataset_revision", "norm_stats_sha256", "development_reset_sha256",
            "final_reset_sha256", "e2_actor_binding_status",
            *AUTHORITY_FIELDS,
        },
        "runtime identity record",
    )
    if payload["schema_version"] != 1 or payload["record_kind"] != "g0-runtime-and-assets-freeze":
        raise G0AcceptanceError("runtime identity record kind is invalid")
    if payload["status"] != "accepted-for-e1-preflight-only":
        raise G0AcceptanceError("runtime identity status is invalid")
    if payload["selected_option"] != "lambda-h100-pcie":
        raise G0AcceptanceError("runtime selection is invalid")
    if payload["e2_actor_binding_status"] != "pending-e1-output":
        raise G0AcceptanceError("E2 actor must remain pending until E1 completes")
    for field in ("accepted_by", "task", "sapien", "dataset_identity", "dataset_revision"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise G0AcceptanceError(f"runtime {field} is missing")
    _timestamp(payload["accepted_at_utc"], "runtime acceptance timestamp")
    require_git_commit(payload["scientific_project_commit"], "scientific project commit")
    require_git_commit(payload["rlinf_commit"], "RLinf commit")
    require_git_commit(payload["maniskill_commit"], "ManiSkill commit")
    for field in (
        "source_candidate_sha256", "fresh_host_qualification_sha256",
        "fresh_image_qualification_sha256", "fresh_route_qualification_sha256",
        "container_image_sha256", "evaluator_environment_identity_sha256",
        "durable_store_identity_sha256", "base_model_sha256", "norm_stats_sha256",
        "development_reset_sha256", "final_reset_sha256",
    ):
        require_sha256(payload[field], f"runtime {field}")
    expected = {
        "source_candidate_sha256": expected_candidate_sha256,
        "evaluator_environment_identity_sha256": expected_evaluator_environment_sha256,
        "development_reset_sha256": expected_development_reset_sha256,
        "final_reset_sha256": expected_final_reset_sha256,
    }
    for field, expected_value in expected.items():
        if payload[field] != require_sha256(expected_value, f"expected {field}"):
            raise G0AcceptanceError(f"runtime {field} mismatch")
    _false_authority(payload, "runtime identity record")
    return envelope


def validate_cost_retention_record(
    value: Any,
    *,
    expected_durable_store_identity_sha256: str,
) -> dict[str, Any]:
    envelope, payload = _envelope(
        value,
        {
            "schema_version", "record_kind", "status", "accepted_by",
            "accepted_at_utc", "provider", "gpu", "pricing_checked_at_utc",
            "pricing_evidence_sha256", "instance_usd_per_hour",
            "storage_usd_per_gib_month", "egress_ceiling_usd",
            "e1_retry_inclusive_compute_usd", "e2_retry_inclusive_compute_usd",
            "total_compute_usd", "storage_ceiling_usd", "total_program_usd",
            "maximum_storage_gib", "maximum_concurrency", "maximum_attempts_per_run",
            "total_wall_clock_seconds", "durable_store_identity_sha256",
            "large_artifact_minimum_retention_days", "compact_evidence_retention",
            "failed_evidence_retained", "automatic_large_artifact_deletion",
            "private_models_in_git", "deletion_requires_verified_export_and_human_approval",
            *AUTHORITY_FIELDS,
        },
        "cost and retention record",
    )
    if payload["schema_version"] != 1 or payload["record_kind"] != "g0-cost-and-retention-freeze":
        raise G0AcceptanceError("cost and retention record kind is invalid")
    if payload["status"] != "accepted-for-e1-preflight-only":
        raise G0AcceptanceError("cost and retention status is invalid")
    if payload["provider"] != "Lambda Cloud" or payload["gpu"] != "NVIDIA H100 PCIe":
        raise G0AcceptanceError("cost provider identity is invalid")
    for field in ("accepted_by",):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise G0AcceptanceError(f"cost {field} is missing")
    _timestamp(payload["accepted_at_utc"], "cost acceptance timestamp")
    _timestamp(payload["pricing_checked_at_utc"], "pricing timestamp")
    require_sha256(payload["pricing_evidence_sha256"], "pricing evidence")
    store = require_sha256(payload["durable_store_identity_sha256"], "durable store identity")
    if store != require_sha256(expected_durable_store_identity_sha256, "expected durable store"):
        raise G0AcceptanceError("cost durable store identity mismatch")
    hourly = _decimal(payload["instance_usd_per_hour"], "instance price")
    storage_rate = _decimal(payload["storage_usd_per_gib_month"], "storage price")
    egress = _decimal(payload["egress_ceiling_usd"], "egress ceiling")
    e1 = _decimal(payload["e1_retry_inclusive_compute_usd"], "E1 compute ceiling")
    e2 = _decimal(payload["e2_retry_inclusive_compute_usd"], "E2 compute ceiling")
    compute = _decimal(payload["total_compute_usd"], "total compute ceiling")
    storage = _decimal(payload["storage_ceiling_usd"], "storage ceiling")
    total = _decimal(payload["total_program_usd"], "total program ceiling")
    if e1 != hourly * Decimal(24) * 2 or e2 != hourly * Decimal(48) * 6 * 2:
        raise G0AcceptanceError("cost retry-inclusive compute arithmetic mismatch")
    if compute != e1 + e2:
        raise G0AcceptanceError("cost compute totals do not reconcile")
    if payload["maximum_storage_gib"] != 500 or storage != storage_rate * Decimal(500):
        raise G0AcceptanceError("cost storage ceiling does not reconcile")
    if total != compute + storage + egress:
        raise G0AcceptanceError("cost total program ceiling does not reconcile")
    if payload["maximum_concurrency"] != 3 or payload["maximum_attempts_per_run"] != 2:
        raise G0AcceptanceError("cost attempt or concurrency ceiling is invalid")
    if payload["total_wall_clock_seconds"] != 864000:
        raise G0AcceptanceError("cost wall-clock ceiling is invalid")
    if payload["large_artifact_minimum_retention_days"] < 30:
        raise G0AcceptanceError("large artifact retention is too short")
    if payload["compact_evidence_retention"] != "indefinite-in-git":
        raise G0AcceptanceError("compact evidence retention is invalid")
    for field in (
        "failed_evidence_retained", "deletion_requires_verified_export_and_human_approval",
    ):
        if payload[field] is not True:
            raise G0AcceptanceError("cost retention controls are incomplete")
    for field in ("automatic_large_artifact_deletion", "private_models_in_git"):
        if payload[field] is not False:
            raise G0AcceptanceError("cost retention controls are unsafe")
    _false_authority(payload, "cost and retention record")
    return envelope


def validate_protocol_acceptance_record(
    value: Any,
    *,
    expected_runtime_sha256: str,
    expected_cost_sha256: str,
    expected_custody_sha256: str,
    expected_deployment_sha256: str,
) -> dict[str, Any]:
    envelope, payload = _envelope(
        value,
        {
            "schema_version", "record_kind", "status", "reviewer_principal",
            "accepted_at_utc", "runtime_record_sha256", "cost_record_sha256",
            "custody_record_sha256", "deployment_record_sha256", "training_seeds",
            "e1_checkpoint_steps", "e1_selection_rule", "e2_conditions",
            "e2_original_run_count", "decision_rule", "final_reset_use",
            "agent_controls_evaluation", "agent_controls_selection",
            *AUTHORITY_FIELDS,
        },
        "protocol acceptance record",
    )
    if payload["schema_version"] != 1 or payload["record_kind"] != "g0-human-protocol-acceptance":
        raise G0AcceptanceError("protocol acceptance record kind is invalid")
    if payload["status"] != "accepted-for-e1-preflight-only":
        raise G0AcceptanceError("protocol acceptance status is invalid")
    if not isinstance(payload["reviewer_principal"], str) or not payload["reviewer_principal"].strip():
        raise G0AcceptanceError("protocol reviewer principal is missing")
    _timestamp(payload["accepted_at_utc"], "protocol acceptance timestamp")
    expected = {
        "runtime_record_sha256": expected_runtime_sha256,
        "cost_record_sha256": expected_cost_sha256,
        "custody_record_sha256": expected_custody_sha256,
        "deployment_record_sha256": expected_deployment_sha256,
    }
    for field, expected_value in expected.items():
        if require_sha256(payload[field], field) != require_sha256(expected_value, f"expected {field}"):
            raise G0AcceptanceError(f"protocol {field} mismatch")
    if payload["training_seeds"] != [2026, 2027, 2028]:
        raise G0AcceptanceError("protocol training seeds are invalid")
    if payload["e1_checkpoint_steps"] != [250, 500, 1000, 2000]:
        raise G0AcceptanceError("protocol E1 checkpoint grid is invalid")
    if payload["e1_selection_rule"] != "highest-development-success-earliest-exact-tie":
        raise G0AcceptanceError("protocol E1 selection rule is invalid")
    if payload["e2_conditions"] != ["control", "candidate"] or payload["e2_original_run_count"] != 6:
        raise G0AcceptanceError("protocol E2 allocation is invalid")
    if payload["decision_rule"] != "g0-paired-seed-t-v1":
        raise G0AcceptanceError("protocol decision rule is invalid")
    if payload["final_reset_use"] != "independent-evaluator-only-after-frozen-evidence":
        raise G0AcceptanceError("protocol final reset boundary is invalid")
    if payload["agent_controls_evaluation"] is not False or payload["agent_controls_selection"] is not False:
        raise G0AcceptanceError("protocol grants the agent decision authority")
    _false_authority(payload, "protocol acceptance record")
    return envelope
