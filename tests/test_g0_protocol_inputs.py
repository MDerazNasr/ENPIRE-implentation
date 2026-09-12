from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_g0_runtime_cost_candidates import (
    build_candidates,
    build_lambda_h100_candidates,
    build_lambda_h100_qualified_candidates,
)
from supervisor.canonical import fingerprint
from supervisor.g0_protocol_inputs import (
    G0ProtocolInputError,
    validate_cost_retention_candidate,
    validate_runtime_identity_candidate,
)


ROOT = Path(__file__).resolve().parents[1]


class G0ProtocolInputTests(unittest.TestCase):
    def test_candidates_are_deterministic_non_authorizing_and_incomplete(self) -> None:
        first = build_candidates(ROOT)
        second = build_candidates(ROOT)
        self.assertEqual(first, second)
        runtime, cost = first
        validate_runtime_identity_candidate(runtime)
        validate_cost_retention_candidate(cost)
        self.assertEqual(runtime["payload"]["preferred_option"], "modal-rtx-pro-6000")
        self.assertEqual(len(runtime["payload"]["deferred_bindings"]), 4)
        self.assertFalse(runtime["payload"]["evidence_boundary"]["runtime_selected"])
        self.assertEqual(cost["payload"]["proposed_envelope"]["total_program_usd"], "2905")
        for payload in (runtime["payload"], cost["payload"]):
            for field in (
                "scientific_execution_authorized", "campaign_activation_authorized",
                "gpu_execution_authorized", "paid_execution_authorized",
                "provider_call_authorized", "model_egress_authorized",
                "promotion_authorized",
            ):
                self.assertFalse(payload[field])

    def test_runtime_candidate_tampering_and_false_completion_fail_closed(self) -> None:
        runtime, _ = build_candidates(ROOT)
        tampered = json.loads(json.dumps(runtime))
        tampered["payload"]["preferred_option"] = "lambda-h100-pcie"
        with self.assertRaises(G0ProtocolInputError):
            validate_runtime_identity_candidate(tampered)
        forged = json.loads(json.dumps(runtime))
        forged["payload"]["status"] = "ready"
        forged["payload"]["gpu_execution_authorized"] = True
        forged["sha256"] = fingerprint(forged["payload"])
        with self.assertRaises(G0ProtocolInputError):
            validate_runtime_identity_candidate(forged)

    def test_lambda_h100_candidate_is_selected_but_non_authorizing(self) -> None:
        runtime, cost = build_lambda_h100_candidates(ROOT)
        self.assertEqual(runtime["payload"]["schema_version"], 2)
        self.assertEqual(runtime["payload"]["preferred_option"], "lambda-h100-pcie")
        selected = next(
            option for option in runtime["payload"]["runtime_options"]
            if option["option_id"] == "lambda-h100-pcie"
        )
        self.assertTrue(selected["current_host_binding"]["host_qualified"])
        self.assertFalse(selected["current_host_binding"]["exact_image_qualified"])
        self.assertFalse(selected["current_host_binding"]["current_auto_shutdown_sufficient_for_e1_or_e2"])
        self.assertEqual(cost["payload"]["proposed_envelope"]["total_compute_usd"], "2052.96")
        self.assertIsNone(cost["payload"]["proposed_envelope"]["total_program_usd"])
        self.assertIsNone(cost["payload"]["pricing_snapshot"]["storage_usd_per_gib_month"])
        for payload in (runtime["payload"], cost["payload"]):
            for field in (
                "scientific_execution_authorized", "campaign_activation_authorized",
                "gpu_execution_authorized", "paid_execution_authorized",
                "provider_call_authorized", "model_egress_authorized",
                "promotion_authorized",
            ):
                self.assertFalse(payload[field])

    def test_lambda_h100_candidate_rejects_host_and_storage_claim_tampering(self) -> None:
        runtime, cost = build_lambda_h100_candidates(ROOT)
        wrong_host = json.loads(json.dumps(runtime))
        selected = next(
            option for option in wrong_host["payload"]["runtime_options"]
            if option["option_id"] == "lambda-h100-pcie"
        )
        selected["current_host_binding"]["instance_id"] = "0" * 32
        wrong_host["sha256"] = fingerprint(wrong_host["payload"])
        with self.assertRaises(G0ProtocolInputError):
            validate_runtime_identity_candidate(wrong_host)

        invented_storage = json.loads(json.dumps(cost))
        invented_storage["payload"]["pricing_snapshot"]["storage_usd_per_gib_month"] = "0.09"
        invented_storage["sha256"] = fingerprint(invented_storage["payload"])
        with self.assertRaises(G0ProtocolInputError):
            validate_cost_retention_candidate(invented_storage)

    def test_lambda_h100_qualified_candidate_binds_image_but_not_route(self) -> None:
        runtime, cost = build_lambda_h100_qualified_candidates(ROOT)
        self.assertEqual(runtime["payload"]["schema_version"], 3)
        selected = next(
            option for option in runtime["payload"]["runtime_options"]
            if option["option_id"] == "lambda-h100-pcie"
        )
        self.assertTrue(selected["current_host_binding"]["exact_image_qualified"])
        self.assertEqual(
            selected["container_image_sha256"],
            "06232835258702a325f77bbea6fd5d157711b14976bd0c3dec5af3a36cf705fd",
        )
        self.assertFalse(runtime["payload"]["evidence_boundary"]["representative_route_qualified"])
        self.assertIn(
            "representative_no_outcome_route_qualification",
            runtime["payload"]["deferred_bindings"],
        )
        self.assertEqual(cost["payload"]["schema_version"], 2)

    def test_cost_arithmetic_and_retention_weakening_fail_closed(self) -> None:
        _, cost = build_candidates(ROOT)
        wrong_total = json.loads(json.dumps(cost))
        wrong_total["payload"]["proposed_envelope"]["total_program_usd"] = "1"
        wrong_total["sha256"] = fingerprint(wrong_total["payload"])
        with self.assertRaises(G0ProtocolInputError):
            validate_cost_retention_candidate(wrong_total)
        deletion = json.loads(json.dumps(cost))
        deletion["payload"]["retention_policy"]["automatic_large_artifact_deletion"] = True
        deletion["sha256"] = fingerprint(deletion["payload"])
        with self.assertRaises(G0ProtocolInputError):
            validate_cost_retention_candidate(deletion)

    def test_cli_is_direct_create_only_and_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="enpire-g0-inputs-test-") as temporary:
            root = Path(temporary)
            runtime_path = root / "runtime.json"
            cost_path = root / "cost.json"
            command = [
                sys.executable,
                "scripts/build_g0_runtime_cost_candidates.py",
                "--runtime-output", str(runtime_path),
                "--cost-output", str(cost_path),
            ]
            first = subprocess.run(
                command, cwd=ROOT, check=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            output = json.loads(first.stdout)
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            cost = json.loads(cost_path.read_text(encoding="utf-8"))
            self.assertEqual(output["runtime_sha256"], runtime["sha256"])
            self.assertEqual(output["cost_sha256"], cost["sha256"])
            repeated = subprocess.run(
                command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("create-only", repeated.stderr)


if __name__ == "__main__":
    unittest.main()
