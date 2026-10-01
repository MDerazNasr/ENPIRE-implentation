import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-l40s-step-250-v4-cancelled-v1.json"
)


def sha256_at_commit(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


class E1V4CancelledReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(set(self.envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_receipt_binds_launched_sources(self) -> None:
        launched = self.payload["launched_source"]
        commit = launched["action_remediation_commit"]
        for path_field, hash_field in (
            ("config_path", "config_sha256"),
            ("launcher_path", "launcher_sha256"),
            ("runner_path", "runner_sha256"),
        ):
            self.assertEqual(
                sha256_at_commit(commit, launched[path_field]),
                launched[hash_field],
            )

    def test_partial_rollout_is_not_accepted_as_a_metric(self) -> None:
        outcome = self.payload["outcome"]
        self.assertEqual(outcome["completed_rollout_epochs"], 4)
        self.assertEqual(outcome["completed_trajectories_implied"], 64)
        self.assertTrue(outcome["live_action_preparation_passed"])
        self.assertTrue(outcome["live_simulator_actions_executed"])
        self.assertFalse(outcome["aggregate_metric_produced"])
        self.assertFalse(outcome["partial_results_scientifically_accepted"])
        self.assertFalse(self.payload["evidence"]["terminal_receipt_created"])


if __name__ == "__main__":
    unittest.main()
