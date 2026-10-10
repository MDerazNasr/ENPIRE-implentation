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
    / "e1-modal-l40s-v7-staged-remediation-v1.json"
)
APPROVAL = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-l40s-step-2000-v7-staged-approval-v1.json"
)
STAGE_FAILURE = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-checkpoint-stage-v1-import-failure-v1.json"
)
V8_REMEDIATION = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-l40s-v8-stage-packaging-remediation-v1.json"
)
STAGE_V2_APPROVAL = (
    ROOT
    / "results"
    / "agent-supervisor"
    / "g0"
    / "e1-modal-checkpoint-stage-v2-approval-v1.json"
)


def sha256_at_commit(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


class E1V7StagedRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.envelope = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.payload = cls.envelope["payload"]

    def test_receipt_is_canonical_and_non_authorizing(self) -> None:
        self.assertEqual(set(self.envelope), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.envelope["sha256"])
        self.assertTrue(all(value is False for value in self.payload["authority"].values()))
        gate = self.payload["gate"]
        self.assertFalse(gate["checkpoint_accessed"])
        self.assertFalse(gate["cloud_function_spawned"])
        self.assertFalse(gate["gpu_used"])
        self.assertFalse(gate["paid_work_performed"])

    def test_receipt_binds_exact_recovery_sources(self) -> None:
        correction = self.payload["correction"]
        commit = correction["source_commit"]
        for path_field, hash_field in (
            ("documentation_path", "documentation_sha256"),
            ("evaluation_launcher_path", "evaluation_launcher_sha256"),
            ("stage_helper_path", "stage_helper_sha256"),
            ("stage_launcher_path", "stage_launcher_sha256"),
            ("stage_wrapper_path", "stage_wrapper_sha256"),
        ):
            self.assertEqual(
                sha256_at_commit(commit, correction[path_field]),
                correction[hash_field],
            )

    def test_cost_and_shard_bounds_are_strict(self) -> None:
        cost = self.payload["cost_boundary"]
        self.assertLessEqual(
            cost["maximum_proposed_total_d1_cost_usd"],
            cost["total_d1_ceiling_usd"],
        )
        self.assertEqual(
            self.payload["failed_campaign"]["replacement_shards"],
            [1, 2, 3],
        )
        self.assertEqual(self.payload["failed_campaign"]["retained_complete_shard"], 0)
        self.assertEqual(self.payload["gate"]["full_tests_passed"], 412)

    def test_v7_approval_is_exactly_bounded(self) -> None:
        envelope = json.loads(APPROVAL.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(fingerprint(payload), envelope["sha256"])
        authority = payload["authority"]
        self.assertTrue(authority["checkpoint_2000_stage_authorized"])
        self.assertTrue(authority["checkpoint_2000_v7_replacement_shards_authorized"])
        self.assertFalse(authority["automatic_retry_authorized"])
        self.assertFalse(authority["shard_0_duplicate_authorized"])
        self.assertEqual(payload["execution"]["stage_attempts"], 1)
        self.assertEqual(
            [item["index"] for item in payload["execution"]["replacement_shards"]],
            [1, 2, 3],
        )
        self.assertTrue(payload["execution"]["sequential"])
        self.assertEqual(payload["execution"]["modal_retries"], 0)
        self.assertLessEqual(
            payload["budget"]["stage_plus_recorded_maximum_d1_cost_usd"],
            payload["budget"]["maximum_cumulative_d1_cost_usd"],
        )
        self.assertFalse(any(payload["exclusions"].values()))

    def test_stage_v1_import_failure_is_terminal_and_non_authorizing(self) -> None:
        envelope = json.loads(STAGE_FAILURE.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(fingerprint(payload), envelope["sha256"])
        self.assertTrue(all(value is False for value in payload["authority"].values()))
        failure = payload["failure"]
        self.assertEqual(failure["error_type"], "ModuleNotFoundError")
        self.assertFalse(failure["checkpoint_accessed"])
        self.assertFalse(failure["staged_checkpoint_created"])
        self.assertFalse(failure["stage_receipt_created"])
        self.assertFalse(failure["gpu_used"])
        self.assertFalse(failure["metric_produced"])

    def test_v8_remediation_binds_corrected_sources_without_authority(self) -> None:
        envelope = json.loads(V8_REMEDIATION.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(fingerprint(payload), envelope["sha256"])
        self.assertTrue(all(value is False for value in payload["authority"].values()))
        correction = payload["correction"]
        commit = correction["source_commit"]
        for path_field, hash_field in (
            ("documentation_path", "documentation_sha256"),
            ("evaluation_launcher_path", "evaluation_launcher_sha256"),
            ("stage_launcher_path", "stage_launcher_sha256"),
            ("stage_wrapper_path", "stage_wrapper_sha256"),
        ):
            self.assertEqual(
                sha256_at_commit(commit, correction[path_field]),
                correction[hash_field],
            )
        self.assertEqual(payload["gate"]["full_tests_passed"], 417)
        self.assertFalse(payload["gate"]["cloud_function_spawned_during_offline_correction"])

    def test_stage_v2_approval_authorizes_only_one_cpu_attempt(self) -> None:
        envelope = json.loads(STAGE_V2_APPROVAL.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(fingerprint(payload), envelope["sha256"])
        authority = payload["authority"]
        self.assertTrue(authority["checkpoint_2000_stage_v2_authorized"])
        self.assertFalse(authority["automatic_retry_authorized"])
        self.assertFalse(authority["gpu_shards_authorized"])
        self.assertFalse(authority["checkpoint_evaluation_authorized"])
        self.assertEqual(payload["budget"]["stage_attempts"], 1)
        self.assertLessEqual(payload["budget"]["maximum_stage_cost_usd"], 1.0)
        self.assertTrue(payload["execution"]["create_only"])
        self.assertEqual(payload["execution"]["modal_retries"], 0)


if __name__ == "__main__":
    unittest.main()
