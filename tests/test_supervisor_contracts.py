from __future__ import annotations

import copy
import json
import math
import unittest
from datetime import datetime, timezone

from supervisor.budget import BudgetExceeded, BudgetRequest, BudgetTracker, BudgetUsage
from supervisor.canonical import ContractError, fingerprint
from supervisor.contracts import (
    ApprovalEnvelope,
    CampaignSpec,
    DecisionRecord,
    TrialEvidence,
)


BASE_COMMIT = "8ae2aad5ebfd2153119994f60ada285834e1318e"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"


def campaign_data() -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "d2-config-fixture",
        "research_question": "Can bounded configuration proposals improve Control B?",
        "baseline_commit": BASE_COMMIT,
        "rlinf_commit": RLINF_COMMIT,
        "edit_mode": "config_only",
        "editable_paths": ["candidates/config_override.json"],
        "allowed_parameters": {
            "actor.optim.lr": {
                "kind": "number",
                "minimum": "0.000001",
                "maximum": "0.001",
            },
            "algorithm.actor.update_epoch": {
                "kind": "integer",
                "minimum": "1",
                "maximum": "8",
            },
            "algorithm.schedule": {
                "kind": "enum",
                "choices": ["upstream", "constant"],
            },
        },
        "seeds": [2026, 2027, 2028],
        "reset_set_hash": "a" * 64,
        "evaluator_version": "d1-rule-v1",
        "training_budget_steps": 250,
        "evaluation_trajectories": 256,
        "max_concurrency": 2,
        "artifact_namespace": "qualia-rlt-d2",
        "created_at": "2026-08-04T12:00:00Z",
        "budget": {
            "max_trials": 3,
            "max_wall_time_seconds": 10800,
            "max_gpu_cost_usd": "12.50",
            "max_llm_cost_usd": "3.00",
        },
    }


def approval_data(campaign: CampaignSpec) -> dict:
    return {
        "schema_version": 1,
        "campaign_id": campaign.campaign_id,
        "campaign_spec_hash": campaign.fingerprint(),
        "approved_by": "Mohamed Deraz Nasr",
        "approved_at": "2026-08-04T12:05:00Z",
        "expires_at": "2026-08-05T12:05:00Z",
        "edit_mode": campaign.edit_mode.value,
        "max_concurrency": 2,
        "budget": campaign.budget.to_dict(),
    }


def trial_evidence_data() -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "d2-config-fixture",
        "trial_id": "rule-01-seed-2026",
        "arm_id": "rule-config",
        "parent_commit": BASE_COMMIT,
        "candidate_commit": "b" * 40,
        "rlinf_commit": RLINF_COMMIT,
        "config_hash": "c" * 64,
        "command_hash": "d" * 64,
        "seed": 2026,
        "reset_set_hash": "a" * 64,
        "evaluator_version": "d1-rule-v1",
        "started_at": "2026-08-04T13:00:00Z",
        "finished_at": "2026-08-04T13:10:00Z",
        "status": "complete",
        "exit_code": 0,
        "elapsed_seconds": 600.5,
        "gpu_cost_usd": "0.50",
        "llm_cost_usd": "0",
        "metrics": {"eval/success_once": 0.25, "sac/actor_loss": -0.4},
        "metric_errors": [],
        "artifacts": [
            {
                "artifact_id": "manifest",
                "kind": "manifest",
                "uri": "wandb-artifact://qualia/d2/manifest:v1",
                "sha256": "e" * 64,
                "size_bytes": 1024,
            }
        ],
    }


class CampaignContractTests(unittest.TestCase):
    def test_campaign_round_trip_and_hash_are_deterministic(self) -> None:
        first = campaign_data()
        second = {key: first[key] for key in reversed(first)}
        campaign = CampaignSpec.from_dict(first)
        self.assertEqual(campaign.to_dict(), CampaignSpec.from_dict(second).to_dict())
        self.assertEqual(campaign.fingerprint(), fingerprint(campaign.to_dict()))
        self.assertEqual(campaign, CampaignSpec.from_dict(campaign.to_dict()))
        self.assertEqual(campaign.budget.max_gpu_cost_usd, "12.5")

    def test_campaign_rejects_unknown_missing_and_unsafe_fields(self) -> None:
        unknown = campaign_data()
        unknown["execute"] = True
        with self.assertRaisesRegex(ContractError, "unknown fields"):
            CampaignSpec.from_dict(unknown)

        missing = campaign_data()
        del missing["reset_set_hash"]
        with self.assertRaisesRegex(ContractError, "missing required"):
            CampaignSpec.from_dict(missing)

        unsafe = campaign_data()
        unsafe["editable_paths"] = ["../agent/d1_rules.py"]
        with self.assertRaisesRegex(ContractError, "contain '..'"):
            CampaignSpec.from_dict(unsafe)

    def test_campaign_rejects_bad_parameter_rules_and_seeds(self) -> None:
        bad_bounds = campaign_data()
        bad_bounds["allowed_parameters"]["actor.optim.lr"]["minimum"] = "1"
        with self.assertRaisesRegex(ContractError, "may not exceed"):
            CampaignSpec.from_dict(bad_bounds)

        bad_enum = campaign_data()
        bad_enum["allowed_parameters"]["algorithm.schedule"]["choices"] = ["same", "same"]
        with self.assertRaisesRegex(ContractError, "unique"):
            CampaignSpec.from_dict(bad_enum)

        duplicate_seeds = campaign_data()
        duplicate_seeds["seeds"] = [2026, 2026]
        with self.assertRaisesRegex(ContractError, "unique"):
            CampaignSpec.from_dict(duplicate_seeds)

    def test_campaign_rejects_invalid_budgets_and_timestamps(self) -> None:
        for bad_cost in ("-1", "NaN", math.inf):
            data = campaign_data()
            data["budget"]["max_gpu_cost_usd"] = bad_cost
            with self.assertRaises(ContractError):
                CampaignSpec.from_dict(data)

        zero_trials = campaign_data()
        zero_trials["budget"]["max_trials"] = 0
        with self.assertRaisesRegex(ContractError, "positive integer"):
            CampaignSpec.from_dict(zero_trials)

        local_time = campaign_data()
        local_time["created_at"] = "2026-08-04T12:00:00"
        with self.assertRaisesRegex(ContractError, "must use UTC"):
            CampaignSpec.from_dict(local_time)


class ApprovalContractTests(unittest.TestCase):
    def test_approval_binds_exact_campaign_and_active_window(self) -> None:
        campaign = CampaignSpec.from_dict(campaign_data())
        approval = ApprovalEnvelope.from_dict(approval_data(campaign))
        approval.validate_for(campaign, datetime(2026, 8, 4, 13, tzinfo=timezone.utc))

        changed = campaign_data()
        changed["research_question"] += " Changed after approval."
        with self.assertRaisesRegex(ContractError, "exact campaign"):
            approval.validate_for(
                CampaignSpec.from_dict(changed),
                datetime(2026, 8, 4, 13, tzinfo=timezone.utc),
            )

    def test_approval_rejects_expired_or_expanded_envelope(self) -> None:
        campaign = CampaignSpec.from_dict(campaign_data())
        approval = ApprovalEnvelope.from_dict(approval_data(campaign))
        with self.assertRaisesRegex(ContractError, "not active"):
            approval.validate_for(
                campaign, datetime(2026, 8, 5, 12, 5, tzinfo=timezone.utc)
            )

        expanded = approval_data(campaign)
        expanded["budget"] = copy.deepcopy(expanded["budget"])
        expanded["budget"]["max_trials"] = 4
        with self.assertRaisesRegex(ContractError, "trial cap exceeds"):
            ApprovalEnvelope.from_dict(expanded).validate_for(
                campaign, datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
            )


class EvidenceContractTests(unittest.TestCase):
    def test_trial_evidence_round_trip_and_fingerprint(self) -> None:
        evidence = TrialEvidence.from_dict(trial_evidence_data())
        self.assertEqual(evidence, TrialEvidence.from_dict(evidence.to_dict()))
        self.assertEqual(len(evidence.fingerprint()), 64)
        self.assertEqual(evidence.metrics["eval/success_once"], 0.25)

    def test_nonfinite_metrics_require_explicit_error_record(self) -> None:
        invalid = trial_evidence_data()
        invalid["metrics"]["sac/actor_loss"] = float("nan")
        with self.assertRaisesRegex(ContractError, "metric_errors"):
            TrialEvidence.from_dict(invalid)

        valid = trial_evidence_data()
        del valid["metrics"]["sac/actor_loss"]
        valid["metric_errors"] = ["sac/actor_loss:nonfinite"]
        evidence = TrialEvidence.from_dict(valid)
        self.assertEqual(evidence.metric_errors, ("sac/actor_loss:nonfinite",))

    def test_trial_status_and_exit_code_must_agree(self) -> None:
        complete = trial_evidence_data()
        complete["exit_code"] = 1
        with self.assertRaisesRegex(ContractError, "requires exit_code 0"):
            TrialEvidence.from_dict(complete)

        failed = trial_evidence_data()
        failed["status"] = "failed"
        with self.assertRaisesRegex(ContractError, "non-zero"):
            TrialEvidence.from_dict(failed)

    def test_nonkeep_decision_cannot_change_incumbent(self) -> None:
        evidence = TrialEvidence.from_dict(trial_evidence_data())
        decision = {
            "schema_version": 1,
            "campaign_id": evidence.campaign_id,
            "decision_id": "decision-01",
            "trial_ids": [evidence.trial_id],
            "evaluator_version": evidence.evaluator_version,
            "decision": "revert",
            "reason": "Candidate failed the preregistered rule.",
            "decided_at": "2026-08-04T13:15:00Z",
            "evidence_hashes": [evidence.fingerprint()],
            "incumbent_before": BASE_COMMIT,
            "incumbent_after": "b" * 40,
        }
        with self.assertRaisesRegex(ContractError, "may not change"):
            DecisionRecord.from_dict(decision)

        decision["incumbent_after"] = BASE_COMMIT
        parsed = DecisionRecord.from_dict(decision)
        self.assertEqual(parsed.to_dict(), decision)
        self.assertEqual(len(parsed.fingerprint()), 64)

        keep = copy.deepcopy(decision)
        keep["decision"] = "keep"
        with self.assertRaisesRegex(ContractError, "new incumbent"):
            DecisionRecord.from_dict(keep)


class BudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campaign = CampaignSpec.from_dict(campaign_data())
        self.approval = ApprovalEnvelope.from_dict(approval_data(self.campaign))

    def test_decimal_accounting_has_no_binary_float_drift(self) -> None:
        tracker = BudgetTracker(self.approval)
        tracker.record(
            BudgetUsage.create(
                trial_id="trial-1",
                wall_time_seconds=100,
                gpu_cost_usd="0.1",
                llm_cost_usd="0.1",
            )
        )
        snapshot = tracker.record(
            BudgetUsage.create(
                trial_id="trial-2",
                wall_time_seconds=100,
                gpu_cost_usd="0.2",
                llm_cost_usd="0.2",
            )
        )
        self.assertEqual(snapshot.gpu_cost_usd_used, "0.3")
        self.assertEqual(snapshot.llm_cost_usd_used, "0.3")

    def test_preflight_rejects_each_exceeded_cap(self) -> None:
        cases = [
            BudgetRequest.create(
                wall_time_seconds=10801, gpu_cost_usd="0", llm_cost_usd="0"
            ),
            BudgetRequest.create(
                wall_time_seconds=1, gpu_cost_usd="12.51", llm_cost_usd="0"
            ),
            BudgetRequest.create(
                wall_time_seconds=1, gpu_cost_usd="0", llm_cost_usd="3.01"
            ),
        ]
        for request in cases:
            with self.subTest(request=request), self.assertRaises(BudgetExceeded):
                BudgetTracker(self.approval).assert_can_start(request)

        tracker = BudgetTracker(self.approval)
        for number in range(3):
            tracker.record(
                BudgetUsage.create(
                    trial_id=f"trial-{number}",
                    wall_time_seconds=1,
                    gpu_cost_usd="0",
                    llm_cost_usd="0",
                )
            )
        with self.assertRaisesRegex(BudgetExceeded, "trial cap"):
            tracker.assert_can_start(
                BudgetRequest.create(
                    wall_time_seconds=1, gpu_cost_usd="0", llm_cost_usd="0"
                )
            )

    def test_actual_overrun_is_recorded_and_blocks_future_work(self) -> None:
        tracker = BudgetTracker(self.approval)
        snapshot = tracker.record(
            BudgetUsage.create(
                trial_id="overrun",
                wall_time_seconds=10801,
                gpu_cost_usd="12.51",
                llm_cost_usd="3.01",
            )
        )
        self.assertTrue(snapshot.exceeded)
        with self.assertRaises(BudgetExceeded):
            tracker.assert_can_start(
                BudgetRequest.create(
                    wall_time_seconds=1, gpu_cost_usd="0", llm_cost_usd="0"
                )
            )

    def test_duplicate_usage_is_rejected(self) -> None:
        tracker = BudgetTracker(self.approval)
        usage = BudgetUsage.create(
            trial_id="same", wall_time_seconds=1, gpu_cost_usd="0", llm_cost_usd="0"
        )
        tracker.record(usage)
        with self.assertRaisesRegex(ContractError, "already recorded"):
            tracker.record(usage)


class ExampleContractTests(unittest.TestCase):
    def test_checked_in_example_is_valid_and_non_executable(self) -> None:
        with open("examples/supervisor/campaign.json", encoding="utf-8") as handle:
            example = json.load(handle)
        self.assertEqual(CampaignSpec.from_dict(example).campaign_id, "example-config-campaign")


if __name__ == "__main__":
    unittest.main()
