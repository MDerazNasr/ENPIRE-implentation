import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "results/agent-supervisor/g0/e1-modal-l40s-step-2000-v5-failure-v1.json"


class E1Step2000FailureReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(set(self.envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_partial_run_is_not_a_baseline_metric(self) -> None:
        outcome = self.payload["outcome"]
        self.assertEqual(self.payload["checkpoint"]["step"], 2000)
        self.assertEqual(outcome["completed_rollout_epochs"], 5)
        self.assertEqual(outcome["completed_trajectories_implied"], 80)
        self.assertEqual(outcome["signal"], "SIGTERM")
        self.assertEqual(outcome["signal_origin"], "unverified")
        self.assertFalse(outcome["aggregate_metric_produced"])
        self.assertFalse(outcome["partial_results_scientifically_accepted"])
        self.assertEqual(
            self.payload["status"],
            "failed_after_five_of_sixteen_epochs_no_metric",
        )


if __name__ == "__main__":
    unittest.main()
