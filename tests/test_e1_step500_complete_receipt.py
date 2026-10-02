import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "results/agent-supervisor/g0/e1-modal-l40s-step-500-v5-complete-v1.json"


class E1Step500CompleteReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_complete_metric_is_exact(self) -> None:
        self.assertEqual(self.payload["checkpoint"]["step"], 500)
        self.assertEqual(self.payload["runtime"]["rollout_epochs_completed"], 16)
        self.assertEqual(self.payload["metric"]["num_trajectories"], 256)
        self.assertEqual(self.payload["metric"]["num_successes"], 23)
        self.assertEqual(self.payload["metric"]["success_once"], 23 / 256)
        self.assertEqual(self.payload["status"], "complete_valid_development_baseline")


if __name__ == "__main__":
    unittest.main()
