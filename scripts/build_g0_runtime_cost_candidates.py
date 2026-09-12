#!/usr/bin/env python3
"""Build GPU-free, non-authorizing G0 runtime and cost freeze candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import fingerprint
from supervisor.g0_protocol_inputs import (
    validate_cost_retention_candidate,
    validate_runtime_identity_candidate,
)


def _load(relative: str, root: Path) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _sha256(relative: str, root: Path) -> str:
    return hashlib.sha256((root / relative).read_bytes()).hexdigest()


def _envelope(payload: dict) -> dict:
    return {"payload": payload, "sha256": fingerprint(payload)}


def build_candidates(root: Path = ROOT) -> tuple[dict, dict]:
    f0_path = "results/runtime-qualification/f0/runtime-contract.json"
    h100_path = "results/runtime-qualification/f2/h100-pcie-instance-7-preflight.json"
    terminal_path = "results/runtime-qualification/f2/h100-pcie-attempt-7/terminal.json"
    stage1_path = "results/stage5a-h100/stage5a-stage1-250-seed2026-20260803/manifest.json"
    stage2_path = "results/stage6-modal/stage6-candidate-c-modal-multiprocess-seed2026-r3/summary.json"
    reset_path = "results/agent-supervisor/g0/reset-sets/receipt.json"
    f0 = _load(f0_path, root)
    h100 = _load(h100_path, root)
    terminal = _load(terminal_path, root)
    stage1 = _load(stage1_path, root)
    stage2 = _load(stage2_path, root)
    reset = _load(reset_path, root)

    runtime_payload = {
        "schema_version": 1,
        "record_kind": "g0-runtime-and-assets-freeze-candidate",
        "status": "blocked_pending_requalification_commit_and_e1_output",
        "preferred_option": "modal-rtx-pro-6000",
        "runtime_options": [
            {
                "option_id": "modal-rtx-pro-6000",
                "basis": "F0 selected matched scientific runtime; not currently deployed",
                "gpu": f0["provider"]["gpu_model"],
                "gpu_request": f0["provider"]["gpu_request"],
                "minimum_gpu_memory_bytes": f0["provider"]["minimum_gpu_memory_bytes"],
                "container_image_sha256": f0["container"]["image_platform_digest"].removeprefix("sha256:"),
                "evidence_sha256": _sha256(f0_path, root),
                "fresh_qualification_required": True,
                "scientific_execution_authorized": False,
            },
            {
                "option_id": "lambda-h100-pcie",
                "basis": "F2 attempt-7 engineering rehearsal only",
                "gpu": h100["provider"]["gpu"],
                "minimum_gpu_memory_bytes": h100["qualification"]["gpu_memory_bytes"],
                "container_image_sha256": h100["execution"]["image_id"].removeprefix("sha256:"),
                "evidence_sha256": _sha256(terminal_path, root),
                "fresh_qualification_required": True,
                "scientific_execution_authorized": False,
            },
        ],
        "shared_identities": {
            "task": "PegInsertionSideWideClearance-v1",
            "rlinf_commit": f0["scientific_stack"]["rlinf_commit"],
            "maniskill_commit": f0["scientific_stack"]["maniskill_commit"],
            "sapien": f0["scientific_stack"]["sapien"],
            "base_model_sha256": f0["inputs"]["base_model"]["sha256"],
            "base_model_size_bytes": f0["inputs"]["base_model"]["size_bytes"],
            "dataset_identity": f0["inputs"]["dataset"]["identity"],
            "dataset_revision": f0["inputs"]["dataset"]["revision"],
            "norm_stats_sha256": f0["inputs"]["norm_stats"]["sha256"],
            "development_reset_sha256": reset["payload"]["validation"]["development_sha256"],
            "final_reset_sha256": reset["payload"]["validation"]["final_sha256"],
            "training_seeds": [2026, 2027, 2028],
        },
        "deferred_bindings": [
            "clean_scientific_project_commit",
            "fresh_runtime_qualification_receipt",
            "production_evaluator_environment_sha256",
            "e1_selected_actor_sha256_before_e2",
        ],
        "evidence_boundary": {
            "f0_contract_sha256": _sha256(f0_path, root),
            "h100_preflight_sha256": _sha256(h100_path, root),
            "f2_terminal_sha256": _sha256(terminal_path, root),
            "f2_was_scientific_evidence": False,
            "runtime_selected": False,
            "stage1_actor_selected": False,
        },
        "scientific_execution_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }
    runtime = _envelope(runtime_payload)

    cost_payload = {
        "schema_version": 1,
        "record_kind": "g0-cost-and-retention-freeze-candidate",
        "status": "proposal_requires_fresh_qualification_and_human_acceptance",
        "pricing_snapshot": {
            "provider": "Modal",
            "gpu": "Nvidia RTX PRO 6000",
            "checked_at": "2026-09-11",
            "source": "https://modal.com/pricing",
            "gpu_usd_per_second": "0.000842",
            "cpu_physical_cores": 16,
            "cpu_core_usd_per_second": "0.0000131",
            "memory_gib": 96,
            "memory_gib_usd_per_second": "0.00000222",
            "selected_runtime_usd_per_hour": "4.552992",
            "volume_usd_per_gib_month": "0.09",
            "revalidation_required_before_approval": True,
        },
        "historical_basis": {
            "stage1_250_h100": {
                "elapsed_seconds": str(stage1["elapsed_seconds"]),
                "cost_usd": str(stage1["run_cost_usd"]),
                "evidence_sha256": _sha256(stage1_path, root),
            },
            "stage2_100_modal_inconclusive": {
                "elapsed_seconds": str(stage2["combined_segment_elapsed_seconds"]),
                "launcher_cost_usd": str(stage2["combined_segment_launcher_estimated_cost_usd"]),
                "evidence_sha256": _sha256(stage2_path, root),
                "scientific_budget_basis": False,
            },
            "f2_attempt7_engineering": {
                "elapsed_seconds": str(terminal["lifecycle"]["elapsed_seconds"]),
                "cost_usd": terminal["lifecycle"]["in_container_elapsed_cost_usd"],
                "evidence_sha256": _sha256(terminal_path, root),
                "scientific_budget_basis": False,
            },
        },
        "proposed_envelope": {
            "e0_compute_usd": "0",
            "e1_original_runs": 1,
            "e1_timeout_seconds_per_attempt": 86400,
            "e1_maximum_usd_per_attempt": "110",
            "e1_retry_inclusive_compute_usd": "220",
            "e2_original_runs": 6,
            "e2_timeout_seconds_per_attempt": 172800,
            "e2_maximum_usd_per_attempt": "220",
            "e2_retry_inclusive_compute_usd": "2640",
            "maximum_attempts_per_run": 2,
            "maximum_concurrency": 3,
            "total_wall_clock_seconds": 864000,
            "total_compute_usd": "2860",
            "maximum_storage_gib": 500,
            "one_month_storage_usd": "45",
            "total_program_usd": "2905",
            "notification_percentages": [25, 50, 75, 90],
            "auto_stop_at_compute_or_time_cap": True,
        },
        "retention_policy": {
            "compact_evidence": "indefinite-in-git",
            "failed_interrupted_reverted_inconclusive_evidence": "retain",
            "large_artifact_minimum_days_after_terminal_reconciliation": 30,
            "automatic_large_artifact_deletion": False,
            "large_artifact_deletion_requires_verified_export_and_human_approval": True,
            "private_models_in_git": False,
            "authoritative_store": "hash-bound evaluator evidence; mirrors are non-authoritative",
        },
        "approval_requirements": [
            "fresh runtime qualification and observed rate receipt",
            "fresh provider pricing immediately before approval",
            "human acceptance of every timeout cost concurrency and retention value",
            "separate fingerprinted paid-run approval with UTC window",
        ],
        "scientific_execution_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }
    cost = _envelope(cost_payload)
    validate_runtime_identity_candidate(runtime)
    validate_cost_retention_candidate(cost)
    return runtime, cost


def build_lambda_h100_candidates(root: Path = ROOT) -> tuple[dict, dict]:
    runtime, prior_cost = build_candidates(root)
    host_path = "results/runtime-qualification/g0/lambda-h100-pcie-instance-1-host.json"
    host = _load(host_path, root)
    runtime_payload = json.loads(json.dumps(runtime["payload"]))
    runtime_payload["schema_version"] = 2
    runtime_payload["status"] = "blocked_pending_exact_image_route_commit_storage_and_e1_output"
    runtime_payload["preferred_option"] = "lambda-h100-pcie"
    selected = next(
        item for item in runtime_payload["runtime_options"]
        if item["option_id"] == "lambda-h100-pcie"
    )
    selected["basis"] = "F2 attempt-7 engineering evidence plus fresh read-only G0 host qualification; exact image and no-outcome route remain unqualified"
    selected["current_host_binding"] = {
        "provider": host["provider"]["name"],
        "instance_id": host["provider"]["instance_id"],
        "region": host["provider"]["region"],
        "ip": host["provider"]["ip"],
        "price_usd_per_hour": host["provider"]["price_usd_per_hour"],
        "host_qualification_sha256": _sha256(host_path, root),
        "host_qualified": True,
        "exact_image_qualified": False,
        "current_auto_shutdown_sufficient_for_e1_or_e2": False,
    }
    runtime_payload["evidence_boundary"]["runtime_selected"] = True
    runtime_payload["evidence_boundary"]["selection_scope"] = "preferred design and exact host binding only; not canonical acceptance or execution authority"
    runtime_payload["deferred_bindings"] = [
        "clean_scientific_project_commit",
        "fresh_runtime_qualification_receipt",
        "production_evaluator_environment_sha256",
        "durable_off_host_checkpoint_and_evidence_store",
        "lambda_storage_and_egress_pricing",
        "e1_selected_actor_sha256_before_e2",
    ]
    runtime = _envelope(runtime_payload)

    cost_payload = json.loads(json.dumps(prior_cost["payload"]))
    cost_payload["schema_version"] = 2
    cost_payload["pricing_snapshot"] = {
        "provider": "Lambda Cloud",
        "gpu": "NVIDIA H100 PCIe",
        "checked_at": "2026-09-12",
        "source": "user-supplied provider dashboard",
        "instance_usd_per_hour": "3.29",
        "storage_usd_per_gib_month": None,
        "egress_pricing_status": "unresolved",
        "revalidation_required_before_approval": True,
    }
    cost_payload["proposed_envelope"] = {
        "e0_compute_usd": "0",
        "e1_original_runs": 1,
        "e1_timeout_seconds_per_attempt": 86400,
        "e1_maximum_usd_per_attempt": "78.96",
        "e1_retry_inclusive_compute_usd": "157.92",
        "e2_original_runs": 6,
        "e2_timeout_seconds_per_attempt": 172800,
        "e2_maximum_usd_per_attempt": "157.92",
        "e2_retry_inclusive_compute_usd": "1895.04",
        "maximum_attempts_per_run": 2,
        "maximum_concurrency": 3,
        "total_wall_clock_seconds": 864000,
        "total_compute_usd": "2052.96",
        "compute_only_ceiling_usd": "2052.96",
        "maximum_storage_gib": 500,
        "one_month_storage_usd": None,
        "total_program_usd": None,
        "notification_percentages": [25, 50, 75, 90],
        "auto_stop_at_compute_or_time_cap": True,
        "current_six_hour_auto_shutdown_is_sufficient": False,
    }
    cost_payload["approval_requirements"] = [
        "fresh exact-image and no-outcome route qualification on the bound instance",
        "fresh provider compute storage and egress pricing immediately before approval",
        "durable off-host checkpoint and evidence destination",
        "instance lifetime extension covering the authorized attempt plus reconciliation margin",
        "human acceptance of every timeout cost concurrency and retention value",
        "separate fingerprinted paid-run approval with UTC window",
    ]
    cost = _envelope(cost_payload)
    validate_runtime_identity_candidate(runtime)
    validate_cost_retention_candidate(cost)
    return runtime, cost


def build_lambda_h100_qualified_candidates(root: Path = ROOT) -> tuple[dict, dict]:
    runtime, cost = build_lambda_h100_candidates(root)
    qualification_path = "results/runtime-qualification/g0/lambda-h100-pcie-instance-1/qualification.json"
    qualification = _load(qualification_path, root)
    runtime_payload = json.loads(json.dumps(runtime["payload"]))
    runtime_payload["schema_version"] = 3
    runtime_payload["status"] = "blocked_pending_route_storage_evaluator_and_e1_output"
    selected = next(
        item for item in runtime_payload["runtime_options"]
        if item["option_id"] == "lambda-h100-pcie"
    )
    selected["basis"] = "fresh exact-image public runtime qualification on the selected Lambda H100 PCIe; no-outcome representative route remains pending"
    selected["container_image_sha256"] = qualification["image"]["id"].removeprefix("sha256:")
    selected["current_host_binding"]["exact_image_qualified"] = True
    selected["current_host_binding"]["image_qualification_sha256"] = _sha256(
        qualification_path, root
    )
    selected["current_host_binding"]["project_commit"] = qualification["source"][
        "project_commit"
    ]
    runtime_payload["deferred_bindings"] = [
        "representative_no_outcome_route_qualification",
        "production_evaluator_environment_sha256",
        "durable_off_host_checkpoint_and_evidence_store",
        "lambda_storage_and_egress_pricing",
        "e1_selected_actor_sha256_before_e2",
    ]
    runtime_payload["evidence_boundary"]["exact_image_public_runtime_qualified"] = True
    runtime_payload["evidence_boundary"]["representative_route_qualified"] = False
    runtime = _envelope(runtime_payload)
    validate_runtime_identity_candidate(runtime)
    validate_cost_retention_candidate(cost)
    return runtime, cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-output", type=Path, required=True)
    parser.add_argument("--cost-output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=("modal-v1", "lambda-h100-v2", "lambda-h100-qualified-v3"),
        default="modal-v1",
    )
    args = parser.parse_args()
    if args.runtime_output.exists() or args.cost_output.exists():
        parser.error("candidate outputs are create-only")
    if args.profile == "modal-v1":
        runtime, cost = build_candidates()
    elif args.profile == "lambda-h100-v2":
        runtime, cost = build_lambda_h100_candidates()
    else:
        runtime, cost = build_lambda_h100_qualified_candidates()
    for path, value in ((args.runtime_output, runtime), (args.cost_output, cost)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"runtime_sha256": runtime["sha256"], "cost_sha256": cost["sha256"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
