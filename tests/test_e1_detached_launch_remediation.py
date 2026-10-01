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
    / "e1-modal-l40s-detached-launch-remediation-v1.json"
)


def sha256_at_commit(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


class E1DetachedLaunchRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_receipt_binds_detached_sources(self) -> None:
        correction = self.payload["correction"]
        commit = correction["source_commit"]
        self.assertEqual(
            sha256_at_commit(commit, correction["launcher_path"]),
            correction["launcher_sha256"],
        )
        self.assertEqual(
            sha256_at_commit(commit, correction["monitor_path"]),
            correction["monitor_sha256"],
        )

    def test_gate_used_no_compute_and_preserves_cost_cap(self) -> None:
        correction = self.payload["correction"]
        gate = self.payload["gate"]
        self.assertEqual(gate["status"], "offline_passed")
        self.assertFalse(gate["gpu_used"])
        self.assertFalse(gate["checkpoint_accessed"])
        self.assertFalse(gate["detached_function_call_spawned_during_gate"])
        self.assertTrue(gate["detached_acknowledgement_required"])
        self.assertFalse(gate["monitor_can_cancel"])
        self.assertLessEqual(correction["max_gpu_runtime_cost_usd"], 10.0)
        self.assertGreaterEqual(correction["function_timeout_seconds"], 5400)


if __name__ == "__main__":
    unittest.main()
