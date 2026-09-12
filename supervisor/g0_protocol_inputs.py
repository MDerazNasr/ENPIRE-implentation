"""Validation for non-authorizing G0 runtime and cost freeze candidates."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from supervisor.canonical import fingerprint, require_git_commit, require_sha256


class G0ProtocolInputError(ValueError):
    """Raised when a G0 freeze candidate is malformed or overclaims authority."""


AUTHORITY_FIELDS = (
    "scientific_execution_authorized",
    "campaign_activation_authorized",
    "gpu_execution_authorized",
    "paid_execution_authorized",
    "provider_call_authorized",
    "model_egress_authorized",
    "promotion_authorized",
)


def _envelope(value: Any, kind: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise G0ProtocolInputError(f"{kind} envelope is invalid")
    if not isinstance(value["payload"], dict) or fingerprint(value["payload"]) != value["sha256"]:
        raise G0ProtocolInputError(f"{kind} envelope hash mismatch")
    return value["payload"]


def _false_authority(payload: dict[str, Any], kind: str) -> None:
    for field in AUTHORITY_FIELDS:
        if payload.get(field) is not False:
            raise G0ProtocolInputError(f"{kind} grants forbidden authority")


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise G0ProtocolInputError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise G0ProtocolInputError(f"{field} is invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise G0ProtocolInputError(f"{field} must be finite and non-negative")
    return parsed


def validate_runtime_identity_candidate(value: Any) -> dict[str, Any]:
    payload = _envelope(value, "runtime identity candidate")
    expected = {
        "schema_version", "record_kind", "status", "preferred_option",
        "runtime_options", "shared_identities", "deferred_bindings",
        "evidence_boundary", *AUTHORITY_FIELDS,
    }
    if set(payload) != expected or payload["schema_version"] not in (1, 2):
        raise G0ProtocolInputError("runtime identity candidate fields are invalid")
    if payload["record_kind"] != "g0-runtime-and-assets-freeze-candidate":
        raise G0ProtocolInputError("runtime identity candidate kind is invalid")
    allowed_status = {
        1: "blocked_pending_requalification_commit_and_e1_output",
        2: "blocked_pending_exact_image_route_commit_storage_and_e1_output",
    }
    if payload["status"] != allowed_status[payload["schema_version"]]:
        raise G0ProtocolInputError("runtime identity candidate status is invalid")
    options = payload["runtime_options"]
    if not isinstance(options, list) or {item.get("option_id") for item in options if isinstance(item, dict)} != {
        "modal-rtx-pro-6000", "lambda-h100-pcie"
    }:
        raise G0ProtocolInputError("runtime options are incomplete")
    expected_preferred = "modal-rtx-pro-6000" if payload["schema_version"] == 1 else "lambda-h100-pcie"
    if payload["preferred_option"] != expected_preferred:
        raise G0ProtocolInputError("preferred runtime option is invalid")
    for option in options:
        for field in ("evidence_sha256", "container_image_sha256"):
            require_sha256(option[field], f"runtime option {field}")
        if option.get("fresh_qualification_required") is not True:
            raise G0ProtocolInputError("runtime option does not require fresh qualification")
        if option.get("scientific_execution_authorized") is not False:
            raise G0ProtocolInputError("runtime option grants scientific execution")
    if payload["schema_version"] == 2:
        selected = next(item for item in options if item["option_id"] == "lambda-h100-pcie")
        binding = selected.get("current_host_binding")
        if not isinstance(binding, dict):
            raise G0ProtocolInputError("selected runtime host binding is missing")
        if binding.get("provider") != "Lambda Cloud" or binding.get("region") != "Utah, USA":
            raise G0ProtocolInputError("selected runtime provider binding is invalid")
        if binding.get("instance_id") != "15c6fcfe96f946baa1e440d55ac9b688" or binding.get("ip") != "209.20.157.138":
            raise G0ProtocolInputError("selected runtime host identity is invalid")
        require_sha256(binding.get("host_qualification_sha256"), "host qualification SHA-256")
        if binding.get("host_qualified") is not True or binding.get("exact_image_qualified") is not False:
            raise G0ProtocolInputError("selected runtime qualification state is invalid")
    identities = payload["shared_identities"]
    for field in ("rlinf_commit", "maniskill_commit"):
        require_git_commit(identities[field], f"shared identity {field}")
    for field in (
        "base_model_sha256", "norm_stats_sha256", "development_reset_sha256",
        "final_reset_sha256",
    ):
        require_sha256(identities[field], f"shared identity {field}")
    deferred = payload["deferred_bindings"]
    expected_deferred = {
        "clean_scientific_project_commit",
        "fresh_runtime_qualification_receipt",
        "production_evaluator_environment_sha256",
        "e1_selected_actor_sha256_before_e2",
    }
    if payload["schema_version"] == 2:
        expected_deferred |= {
            "durable_off_host_checkpoint_and_evidence_store",
            "lambda_storage_and_egress_pricing",
        }
    if not isinstance(deferred, list) or set(deferred) != expected_deferred:
        raise G0ProtocolInputError("runtime deferred bindings are invalid")
    _false_authority(payload, "runtime identity candidate")
    return value


def validate_cost_retention_candidate(value: Any) -> dict[str, Any]:
    payload = _envelope(value, "cost retention candidate")
    expected = {
        "schema_version", "record_kind", "status", "pricing_snapshot",
        "historical_basis", "proposed_envelope", "retention_policy",
        "approval_requirements", *AUTHORITY_FIELDS,
    }
    if set(payload) != expected or payload["schema_version"] not in (1, 2):
        raise G0ProtocolInputError("cost retention candidate fields are invalid")
    if payload["record_kind"] != "g0-cost-and-retention-freeze-candidate":
        raise G0ProtocolInputError("cost retention candidate kind is invalid")
    if payload["status"] != "proposal_requires_fresh_qualification_and_human_acceptance":
        raise G0ProtocolInputError("cost retention candidate status is invalid")
    envelope = payload["proposed_envelope"]
    e1 = _decimal(envelope.get("e1_retry_inclusive_compute_usd"), "E1 compute ceiling")
    e2 = _decimal(envelope.get("e2_retry_inclusive_compute_usd"), "E2 compute ceiling")
    compute = _decimal(envelope.get("total_compute_usd"), "total compute ceiling")
    if compute != e1 + e2:
        raise G0ProtocolInputError("cost envelope totals do not reconcile")
    pricing = payload["pricing_snapshot"]
    if payload["schema_version"] == 1:
        if pricing.get("provider") != "Modal" or pricing.get("checked_at") != "2026-09-11":
            raise G0ProtocolInputError("cost pricing snapshot identity is invalid")
        gpu = _decimal(pricing.get("gpu_usd_per_second"), "GPU price")
        cpu = _decimal(pricing.get("cpu_core_usd_per_second"), "CPU price")
        memory = _decimal(pricing.get("memory_gib_usd_per_second"), "memory price")
        total = _decimal(pricing.get("selected_runtime_usd_per_hour"), "runtime hourly price")
        if total != (gpu + 16 * cpu + 96 * memory) * Decimal(3600):
            raise G0ProtocolInputError("runtime hourly price arithmetic mismatch")
        storage = _decimal(envelope.get("one_month_storage_usd"), "storage ceiling")
        total_program = _decimal(envelope.get("total_program_usd"), "total program ceiling")
        if total_program != compute + storage:
            raise G0ProtocolInputError("cost envelope totals do not reconcile")
    else:
        if pricing.get("provider") != "Lambda Cloud" or pricing.get("checked_at") != "2026-09-12":
            raise G0ProtocolInputError("cost pricing snapshot identity is invalid")
        hourly = _decimal(pricing.get("instance_usd_per_hour"), "instance hourly price")
        if hourly != Decimal("3.29") or pricing.get("gpu") != "NVIDIA H100 PCIe":
            raise G0ProtocolInputError("Lambda runtime price or GPU identity is invalid")
        if pricing.get("storage_usd_per_gib_month") is not None or pricing.get("egress_pricing_status") != "unresolved":
            raise G0ProtocolInputError("unverified Lambda storage or egress pricing was asserted")
        if envelope.get("one_month_storage_usd") is not None or envelope.get("total_program_usd") is not None:
            raise G0ProtocolInputError("unresolved storage cannot produce a total program ceiling")
        if _decimal(envelope.get("compute_only_ceiling_usd"), "compute-only ceiling") != compute:
            raise G0ProtocolInputError("compute-only ceiling mismatch")
        if e1 != hourly * Decimal(24) * 2 or e2 != hourly * Decimal(48) * 6 * 2:
            raise G0ProtocolInputError("Lambda retry-inclusive arithmetic mismatch")
    if envelope.get("maximum_attempts_per_run") != 2 or envelope.get("maximum_concurrency") != 3:
        raise G0ProtocolInputError("cost envelope attempt or concurrency limit is invalid")
    retention = payload["retention_policy"]
    if retention.get("compact_evidence") != "indefinite-in-git":
        raise G0ProtocolInputError("compact evidence retention is invalid")
    if retention.get("automatic_large_artifact_deletion") is not False:
        raise G0ProtocolInputError("large artifact deletion must require review")
    if retention.get("private_models_in_git") is not False:
        raise G0ProtocolInputError("private models must not enter Git")
    if not isinstance(payload["approval_requirements"], list) or not payload["approval_requirements"]:
        raise G0ProtocolInputError("cost approval requirements are missing")
    _false_authority(payload, "cost retention candidate")
    return value
