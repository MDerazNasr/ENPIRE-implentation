import hashlib
import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-l40s-observation-remediation-v1.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class E1ObservationRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(set(self.envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))
        self.assertEqual(
            self.payload["status"],
            "remediated_gate_passed_pending_retry_authorization",
        )

    def test_receipt_binds_current_correction_sources(self) -> None:
        correction = self.payload["correction"]
        for path_field, hash_field in (
            ("e1_sitecustomize_path", "e1_sitecustomize_sha256"),
            ("global_sitecustomize_path", "global_sitecustomize_sha256"),
            ("launcher_path", "launcher_sha256"),
            ("runner_path", "runner_sha256"),
        ):
            self.assertEqual(
                sha256(ROOT / correction[path_field]),
                correction[hash_field],
            )

        gate = self.payload["gate"]
        self.assertEqual(
            sha256(ROOT / "modal_e1_adapter_gate.py"),
            gate["gate_launcher_sha256"],
        )
        self.assertEqual(
            sha256(ROOT / "scripts" / "e1_observation_contract_gate.py"),
            gate["gate_script_sha256"],
        )

    def test_gate_passed_without_policy_checkpoint_or_metric(self) -> None:
        gate = self.payload["gate"]
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["gpu_used"])
        self.assertFalse(gate["checkpoint_accessed"])
        self.assertFalse(gate["policy_loaded"])
        self.assertFalse(gate["metric_produced"])
        self.assertEqual(gate["simulator_steps"], 0)
        self.assertTrue(gate["direct_openpi_policy"])
        self.assertFalse(gate["rlt_feature_model_loaded"])
        self.assertEqual(gate["observation_shapes"]["states"], [16, 9])


if __name__ == "__main__":
    unittest.main()
