from __future__ import annotations

import copy
import unittest

from supervisor.canonical import fingerprint
from supervisor.g0_acceptance import (
    G0AcceptanceError,
    validate_cost_retention_record,
    validate_protocol_acceptance_record,
    validate_runtime_identity_record,
)


SHA = {
    name: character * 64
    for name, character in {
        "candidate": "1", "environment": "2", "development": "3", "final": "4",
        "host": "5", "image_qualification": "6", "route": "7", "image": "8",
        "store": "9", "model": "a", "norm": "b", "pricing": "c",
        "custody": "d", "deployment": "e",
    }.items()
}


def envelope(payload: dict) -> dict:
    return {"payload": payload, "sha256": fingerprint(payload)}


def authority() -> dict:
    return {
        "scientific_execution_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }


def runtime_record() -> dict:
    return envelope({
        "schema_version": 1,
        "record_kind": "g0-runtime-and-assets-freeze",
        "status": "accepted-for-e1-preflight-only",
        "source_candidate_sha256": SHA["candidate"],
        "accepted_by": "human-reviewer",
        "accepted_at_utc": "2026-09-12T12:00:00Z",
        "selected_option": "lambda-h100-pcie",
        "scientific_project_commit": "f" * 40,
        "fresh_host_qualification_sha256": SHA["host"],
        "fresh_image_qualification_sha256": SHA["image_qualification"],
        "fresh_route_qualification_sha256": SHA["route"],
        "container_image_sha256": SHA["image"],
        "evaluator_environment_identity_sha256": SHA["environment"],
        "durable_store_identity_sha256": SHA["store"],
        "task": "PegInsertionSideWideClearance-v1",
        "rlinf_commit": "a" * 40,
        "maniskill_commit": "b" * 40,
        "sapien": "3.0.1",
        "base_model_sha256": SHA["model"],
        "dataset_identity": "rlt-maniskill-PegInsertionSide-v1-400-succ",
        "dataset_revision": "2b92d5ef3fe274d30219130133f9e34c7ab91ebf",
        "norm_stats_sha256": SHA["norm"],
        "development_reset_sha256": SHA["development"],
        "final_reset_sha256": SHA["final"],
        "e2_actor_binding_status": "pending-e1-output",
        **authority(),
    })


def cost_record() -> dict:
    return envelope({
        "schema_version": 1,
        "record_kind": "g0-cost-and-retention-freeze",
        "status": "accepted-for-e1-preflight-only",
        "accepted_by": "human-reviewer",
        "accepted_at_utc": "2026-09-12T12:00:00Z",
        "provider": "Lambda Cloud",
        "gpu": "NVIDIA H100 PCIe",
        "pricing_checked_at_utc": "2026-09-12T11:55:00Z",
        "pricing_evidence_sha256": SHA["pricing"],
        "instance_usd_per_hour": "3.29",
        "storage_usd_per_gib_month": "0.10",
        "egress_ceiling_usd": "100",
        "e1_retry_inclusive_compute_usd": "157.92",
        "e2_retry_inclusive_compute_usd": "1895.04",
        "total_compute_usd": "2052.96",
        "storage_ceiling_usd": "50.00",
        "total_program_usd": "2202.96",
        "maximum_storage_gib": 500,
        "maximum_concurrency": 3,
        "maximum_attempts_per_run": 2,
        "total_wall_clock_seconds": 864000,
        "durable_store_identity_sha256": SHA["store"],
        "large_artifact_minimum_retention_days": 30,
        "compact_evidence_retention": "indefinite-in-git",
        "failed_evidence_retained": True,
        "automatic_large_artifact_deletion": False,
        "private_models_in_git": False,
        "deletion_requires_verified_export_and_human_approval": True,
        **authority(),
    })


class G0AcceptanceTests(unittest.TestCase):
    def test_runtime_record_binds_fresh_runtime_and_remains_non_authorizing(self) -> None:
        record = runtime_record()
        self.assertEqual(
            validate_runtime_identity_record(
                record,
                expected_candidate_sha256=SHA["candidate"],
                expected_evaluator_environment_sha256=SHA["environment"],
                expected_development_reset_sha256=SHA["development"],
                expected_final_reset_sha256=SHA["final"],
            ),
            record,
        )
        tampered = copy.deepcopy(record)
        tampered["payload"]["e2_actor_binding_status"] = "selected"
        tampered["sha256"] = fingerprint(tampered["payload"])
        with self.assertRaises(G0AcceptanceError):
            validate_runtime_identity_record(
                tampered,
                expected_candidate_sha256=SHA["candidate"],
                expected_evaluator_environment_sha256=SHA["environment"],
                expected_development_reset_sha256=SHA["development"],
                expected_final_reset_sha256=SHA["final"],
            )

    def test_cost_record_reconciles_compute_storage_egress_and_retention(self) -> None:
        record = cost_record()
        self.assertEqual(
            validate_cost_retention_record(
                record, expected_durable_store_identity_sha256=SHA["store"]
            ),
            record,
        )
        unsafe = copy.deepcopy(record)
        unsafe["payload"]["automatic_large_artifact_deletion"] = True
        unsafe["sha256"] = fingerprint(unsafe["payload"])
        with self.assertRaises(G0AcceptanceError):
            validate_cost_retention_record(
                unsafe, expected_durable_store_identity_sha256=SHA["store"]
            )

    def test_protocol_acceptance_cross_binds_all_prerequisites(self) -> None:
        runtime = runtime_record()
        cost = cost_record()
        payload = {
            "schema_version": 1,
            "record_kind": "g0-human-protocol-acceptance",
            "status": "accepted-for-e1-preflight-only",
            "reviewer_principal": "human-reviewer",
            "accepted_at_utc": "2026-09-12T12:05:00Z",
            "runtime_record_sha256": runtime["sha256"],
            "cost_record_sha256": cost["sha256"],
            "custody_record_sha256": SHA["custody"],
            "deployment_record_sha256": SHA["deployment"],
            "training_seeds": [2026, 2027, 2028],
            "e1_checkpoint_steps": [250, 500, 1000, 2000],
            "e1_selection_rule": "highest-development-success-earliest-exact-tie",
            "e2_conditions": ["control", "candidate"],
            "e2_original_run_count": 6,
            "decision_rule": "g0-paired-seed-t-v1",
            "final_reset_use": "independent-evaluator-only-after-frozen-evidence",
            "agent_controls_evaluation": False,
            "agent_controls_selection": False,
            **authority(),
        }
        record = envelope(payload)
        self.assertEqual(
            validate_protocol_acceptance_record(
                record,
                expected_runtime_sha256=runtime["sha256"],
                expected_cost_sha256=cost["sha256"],
                expected_custody_sha256=SHA["custody"],
                expected_deployment_sha256=SHA["deployment"],
            ),
            record,
        )
        overreach = copy.deepcopy(record)
        overreach["payload"]["gpu_execution_authorized"] = True
        overreach["sha256"] = fingerprint(overreach["payload"])
        with self.assertRaises(G0AcceptanceError):
            validate_protocol_acceptance_record(
                overreach,
                expected_runtime_sha256=runtime["sha256"],
                expected_cost_sha256=cost["sha256"],
                expected_custody_sha256=SHA["custody"],
                expected_deployment_sha256=SHA["deployment"],
            )


if __name__ == "__main__":
    unittest.main()
