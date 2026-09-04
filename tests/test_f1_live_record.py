from __future__ import annotations

import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
F1 = ROOT / "results/runtime-qualification/f1"


class F1LiveRecordTests(unittest.TestCase):
    def test_attempt_chain_and_live_acceptance_are_consistent(self) -> None:
        attempts = [json.loads((F1 / f"attempt-{number}.json").read_text()) for number in (1, 2, 3)]
        self.assertEqual([item["status"] for item in attempts], ["failed_pre_gpu", "failed_pre_gpu", "passed"])
        self.assertEqual([item["operations"]["gpu_probe_calls"] for item in attempts], [0, 0, 2])
        for number, attempt in enumerate(attempts, 1):
            approval = F1 / attempt["approval_record"]
            self.assertEqual(
                hashlib.sha256(approval.read_bytes()).hexdigest(),
                attempt["approval_record_sha256"],
                f"attempt {number} approval",
            )
            self.assertEqual(attempt["operations"]["training_calls"], 0)
            self.assertEqual(attempt["operations"]["evaluation_calls"], 0)
            self.assertEqual(attempt["operations"]["promotion_calls"], 0)

        live = attempts[2]
        self.assertEqual(live["operations"]["terminal_status"], "completed")
        self.assertEqual(live["operations"]["late_cancelled_status"], "cancelled")
        self.assertTrue(live["operations"]["identity_spoof_rejected"])
        self.assertTrue(all(item["retrieved_sha256_matches"] for item in live["artifacts"]))
        self.assertEqual(
            {item["artifact_id"] for item in live["artifacts"]},
            {"gpu-telemetry", "probe-log", "provider-cost-estimate"},
        )
        telemetry = live["runtime_telemetry"]
        self.assertEqual(telemetry["python"], "3.11.14")
        self.assertEqual(telemetry["torch"], "2.8.0+cu128")
        self.assertEqual(telemetry["rlinf_commit"], "c90951a0c799a750cb5294ed10587c61cc2af8bf")
        self.assertIn("RTX PRO 6000", telemetry["gpu_name"])
        self.assertGreater(telemetry["sample_count"], 0)
        self.assertGreater(telemetry["utilization_percent_max"], 0)
        self.assertEqual(telemetry["mesa_llvmpipe_vulkan_gate"], "passed")

        billing = live["provider_billing"]
        resource_total = sum(Decimal(value) for value in billing["resources_usd"].values())
        self.assertEqual(resource_total, Decimal(billing["actual_total_provider_cost_usd"]))
        self.assertLessEqual(
            Decimal(billing["actual_gpu_resource_cost_usd"]),
            Decimal(billing["approved_gpu_resource_cost_usd"]),
        )
        self.assertLessEqual(
            Decimal(billing["actual_total_provider_cost_usd"]),
            Decimal(billing["approved_new_total_provider_cost_usd"]),
        )
        self.assertLessEqual(Decimal(billing["provider_billed_gpu_function_seconds"]), Decimal(600))
        cumulative = sum(
            Decimal(item["provider_billing"]["actual_total_provider_cost_usd"])
            for item in attempts
        )
        self.assertEqual(cumulative, Decimal(live["cumulative_f1_provider_cost_usd"]))


if __name__ == "__main__":
    unittest.main()
