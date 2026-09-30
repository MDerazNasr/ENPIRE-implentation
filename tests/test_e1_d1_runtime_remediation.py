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
    / "e1-modal-l40s-d1-runtime-remediation-v1.json"
)


def sha256_at_commit(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


class E1D1RuntimeRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(set(self.envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))

    def test_receipt_binds_launched_sources(self) -> None:
        correction = self.payload["correction"]
        commit = correction["source_commit"]
        for path_field, hash_field in (
            ("config_path", "config_sha256"),
            ("e1_sitecustomize_path", "e1_sitecustomize_sha256"),
            ("launcher_path", "launcher_sha256"),
            ("runner_path", "runner_sha256"),
        ):
            self.assertEqual(
                sha256_at_commit(commit, correction[path_field]),
                correction[hash_field],
            )
        gate = self.payload["gate"]
        self.assertEqual(
            sha256_at_commit(commit, gate["gate_launcher_path"]),
            gate["gate_launcher_sha256"],
        )
        self.assertEqual(
            sha256_at_commit(commit, gate["gate_script_path"]),
            gate["gate_script_sha256"],
        )

    def test_exact_d1_worker_gate_passed_without_evaluation(self) -> None:
        gate = self.payload["gate"]
        self.assertEqual(gate["status"], "passed")
        self.assertTrue(gate["d1_worker_startup_hook"])
        self.assertEqual(
            gate["runtime_lookup_class"],
            "E1FrozenDevelopmentManiskillRLTEnv",
        )
        self.assertFalse(gate["gpu_used"])
        self.assertFalse(gate["checkpoint_accessed"])
        self.assertFalse(gate["policy_loaded"])
        self.assertFalse(gate["metric_produced"])
        self.assertEqual(gate["simulator_steps"], 0)


if __name__ == "__main__":
    unittest.main()
