import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = (
    ROOT / "results/agent-supervisor/g0/e1-preflight-candidate-v1.json"
)
STORAGE_AMENDMENT = (
    ROOT / "results/agent-supervisor/g0/e1-preflight-storage-amendment-v1.json"
)
PAID_APPROVAL = ROOT / "results/agent-supervisor/g0/e1-stage1-paid-approval-v1.json"
LAUNCH = ROOT / "results/agent-supervisor/g0/e1-stage1-launch-v1.json"
TERMINAL = ROOT / "results/agent-supervisor/g0/e1-stage1-terminal-v1.json"
EVALUATION_PREFLIGHT = (
    ROOT / "results/agent-supervisor/g0/e1-checkpoint-evaluation-preflight-v1.json"
)


class G0E1PreflightReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
        self.payload = self.receipt["payload"]

    def test_envelope_and_source_identity_are_exact(self):
        self.assertEqual(set(self.receipt), {"payload", "sha256"})
        self.assertEqual(fingerprint(self.payload), self.receipt["sha256"])
        self.assertEqual(
            self.payload["source"]["commit"],
            "907ce489d669ef12aa32f7eca819331ad6b448bc",
        )

    def test_receipt_grants_no_execution_or_decision_authority(self):
        self.assertTrue(self.payload["authority"])
        self.assertFalse(any(self.payload["authority"].values()))
        self.assertIn("pending_lifecycle_confirmation", self.payload["status"])

    def test_frozen_e1_boundaries_are_present(self):
        execution = self.payload["execution_contract"]
        evaluation = self.payload["evaluation_contract"]
        self.assertEqual(execution["checkpoint_steps"], [250, 500, 1000, 2000])
        self.assertEqual(execution["seed"], 2026)
        self.assertEqual(execution["compute_cap_usd"], "65.80")
        self.assertEqual(evaluation["development_outcomes_per_checkpoint"], 256)
        self.assertFalse(evaluation["training_worker_constructed"])
        self.assertFalse(evaluation["expert_model_loaded"])
        self.assertFalse(evaluation["final_resets_permitted"])

    def test_worker_is_confined_to_empty_runs_prefix(self):
        evidence = self.payload["durable_evidence"]
        self.assertTrue(evidence["worker_role_assumption_verified"])
        self.assertTrue(evidence["e1_prefix_empty"])
        self.assertTrue(evidence["protected_prefix_list_denied"])
        self.assertEqual(evidence["bucket_object_lock_mode"], "COMPLIANCE")
        self.assertEqual(evidence["bucket_object_lock_days"], 30)

    def test_storage_amendment_is_non_authorizing_and_cross_bound(self):
        amendment = json.loads(STORAGE_AMENDMENT.read_text(encoding="utf-8"))
        payload = amendment["payload"]
        self.assertEqual(fingerprint(payload), amendment["sha256"])
        self.assertEqual(
            payload["superseded_preflight_candidate_sha256"],
            self.receipt["sha256"],
        )
        self.assertFalse(any(payload["authority"].values()))
        self.assertEqual(payload["dry_run"]["objects_uploaded"], 0)
        self.assertTrue(payload["dry_run"]["campaign_prefix_empty_after"])

    def test_paid_approval_is_narrow_and_cross_bound(self):
        approval = json.loads(PAID_APPROVAL.read_text(encoding="utf-8"))
        payload = approval["payload"]
        self.assertEqual(fingerprint(payload), approval["sha256"])
        self.assertEqual(payload["preflight_sha256"], self.receipt["sha256"])
        self.assertTrue(payload["approval_scope"]["gpu_training_authorized"])
        self.assertTrue(payload["approval_scope"]["checkpoint_upload_authorized"])
        for field in (
            "checkpoint_evaluation_authorized",
            "e2_authorized",
            "final_reset_access_authorized",
            "policy_selection_authorized",
            "promotion_authorized",
            "retry_authorized",
        ):
            self.assertFalse(payload["approval_scope"][field])

    def test_launch_is_cross_bound_and_non_evaluating(self):
        approval = json.loads(PAID_APPROVAL.read_text(encoding="utf-8"))
        launch = json.loads(LAUNCH.read_text(encoding="utf-8"))
        payload = launch["payload"]
        self.assertEqual(fingerprint(payload), launch["sha256"])
        self.assertEqual(payload["approval_sha256"], approval["sha256"])
        self.assertFalse(any(payload["authority"].values()))
        self.assertTrue(payload["durable_upload"]["watcher_started"])
        self.assertEqual(payload["container"]["network_mode"], "none")

    def test_terminal_receipt_preserves_execution_and_claim_boundaries(self):
        approval = json.loads(PAID_APPROVAL.read_text(encoding="utf-8"))
        terminal = json.loads(TERMINAL.read_text(encoding="utf-8"))
        payload = terminal["payload"]
        self.assertEqual(fingerprint(payload), terminal["sha256"])
        self.assertEqual(payload["approval_sha256"], approval["sha256"])
        self.assertEqual(payload["container"]["exit_code"], 0)
        self.assertEqual(payload["container"]["training_steps_completed"], 2000)
        self.assertEqual(payload["retry_count"], 0)
        self.assertFalse(any(payload["authority"].values()))
        self.assertEqual(
            [item["step"] for item in payload["durable_evidence"]["checkpoints"]],
            [250, 500, 1000, 2000],
        )
        self.assertEqual(payload["durable_evidence"]["latest_version_count"], 16)
        self.assertEqual(payload["durable_evidence"]["delete_marker_count"], 0)
        self.assertEqual(payload["durable_evidence"]["watcher_missing_steps"], [])
        self.assertTrue(payload["credential_maintenance"]["failure_log_preserved"])
        self.assertFalse(
            payload["independent_verification"]["exact_per_version_retain_until_verified"]
        )
        self.assertFalse(payload["claim_boundary"]["scientific_evaluation_performed"])
        self.assertFalse(payload["claim_boundary"]["policy_improvement_claimed"])

    def test_evaluation_preflight_is_cross_bound_and_non_authorizing(self):
        terminal = json.loads(TERMINAL.read_text(encoding="utf-8"))
        preflight = json.loads(EVALUATION_PREFLIGHT.read_text(encoding="utf-8"))
        payload = preflight["payload"]
        self.assertEqual(fingerprint(payload), preflight["sha256"])
        self.assertFalse(any(payload["authority"].values()))
        self.assertEqual(
            payload["durable_source"]["terminal_receipt_sha256"],
            terminal["sha256"],
        )
        self.assertEqual(
            [checkpoint["step"] for checkpoint in payload["checkpoints"]],
            [250, 500, 1000, 2000],
        )
        self.assertEqual(payload["budget_proposal"]["aggregate_gpu_hours"], 12)
        self.assertEqual(payload["budget_proposal"]["aggregate_max_cost_usd"], "40.00")
        self.assertEqual(payload["budget_proposal"]["retry_count"], 0)
        self.assertEqual(payload["evaluation_contract"]["development_outcomes_per_checkpoint"], 256)
        self.assertFalse(payload["evaluation_contract"]["final_reset_permitted"])
        self.assertIsNone(payload["runtime_proposal"]["instance_id"])
        self.assertIn("blocked_pending", payload["status"])


if __name__ == "__main__":
    unittest.main()
