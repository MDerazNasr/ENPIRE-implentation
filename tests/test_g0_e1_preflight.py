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


if __name__ == "__main__":
    unittest.main()
