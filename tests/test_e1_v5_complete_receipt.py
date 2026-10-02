import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "results/agent-supervisor/g0/e1-modal-l40s-step-250-v5-complete-v1.json"


def sha256_at_commit(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


class E1V5CompleteReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_receipt_binds_detached_sources(self) -> None:
        source = self.payload["source"]
        commit = source["launcher_commit"]
        for path_field, hash_field in (
            ("launcher_path", "launcher_sha256"),
            ("monitor_path", "monitor_sha256"),
        ):
            self.assertEqual(
                sha256_at_commit(commit, source[path_field]),
                source[hash_field],
            )

    def test_complete_metric_is_exact_and_not_promoted(self) -> None:
        self.assertEqual(self.payload["status"], "complete_valid_development_baseline")
        self.assertEqual(self.payload["runtime"]["rollout_epochs_completed"], 16)
        self.assertEqual(self.payload["metric"]["num_trajectories"], 256)
        self.assertEqual(self.payload["metric"]["success_once"], 0.0)
        self.assertEqual(self.payload["metric"]["episode_len_mean"], 500.0)
        self.assertLess(self.payload["runtime"]["elapsed_seconds"], 7200)


if __name__ == "__main__":
    unittest.main()
