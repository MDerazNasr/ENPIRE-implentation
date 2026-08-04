from __future__ import annotations

import copy
import json
import unittest

from supervisor.canonical import ContractError
from supervisor.contracts import CampaignSpec
from supervisor.proposals import (
    PROPOSAL_SCHEMA_HASH,
    PROPOSAL_SCHEMA_JSON,
    AttemptAudit,
    Proposal,
    proposal_json_schema,
)


BASE_COMMIT = "8ae2aad5ebfd2153119994f60ada285834e1318e"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"


def config_campaign_data() -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "m2-config-campaign",
        "research_question": "Can one bounded RLT configuration improve Control B?",
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
        "artifact_namespace": "qualia-rlt-m2",
        "created_at": "2026-08-04T12:00:00Z",
        "budget": {
            "max_trials": 3,
            "max_wall_time_seconds": 10800,
            "max_gpu_cost_usd": "12.5",
            "max_llm_cost_usd": "3",
        },
    }


def config_proposal_data() -> dict:
    return {
        "schema_version": 1,
        "proposal_id": "proposal-config-01",
        "campaign_id": "m2-config-campaign",
        "arm_id": "claude-config",
        "base_commit": BASE_COMMIT,
        "edit_mode": "config_only",
        "hypothesis": "A lower actor learning rate will reduce unstable updates.",
        "evidence_ids": ["control-b-summary"],
        "expected_effect": "Lower actor-loss variance without reducing success.",
        "falsification_condition": "Success drops or loss variance does not improve.",
        "rollback_condition": "Revert when the deterministic evaluator does not keep it.",
        "changed_paths": ["candidates/config_override.json"],
        "requested_tests": ["config-contract", "dry-run"],
        "estimated_budget": {
            "wall_time_seconds": 1800,
            "gpu_cost_usd": "2.5",
            "llm_cost_usd": "0.2",
        },
        "config_overrides": {"actor.optim.lr": 0.00005},
    }


def code_campaign_data() -> dict:
    data = config_campaign_data()
    data["campaign_id"] = "m2-code-campaign"
    data["edit_mode"] = "actor_objective_code"
    data["editable_paths"] = ["candidates/actor_objective.py"]
    data["allowed_parameters"] = {}
    return data


def code_proposal_data() -> dict:
    data = config_proposal_data()
    data["proposal_id"] = "proposal-code-01"
    data["campaign_id"] = "m2-code-campaign"
    data["arm_id"] = "claude-code"
    data["edit_mode"] = "actor_objective_code"
    data["changed_paths"] = ["candidates/actor_objective.py"]
    del data["config_overrides"]
    data["unified_diff"] = (
        "diff --git a/candidates/actor_objective.py b/candidates/actor_objective.py\n"
        "--- a/candidates/actor_objective.py\n"
        "+++ b/candidates/actor_objective.py\n"
        "@@ -1 +1 @@\n-old = 1\n+new = 1\n"
    )
    return data


class ProposalContractTests(unittest.TestCase):
    def test_config_proposal_round_trip_and_campaign_validation(self) -> None:
        campaign = CampaignSpec.from_dict(config_campaign_data())
        proposal = Proposal.from_dict(config_proposal_data())
        proposal.validate_for_campaign(campaign, incumbent_commit=BASE_COMMIT)
        self.assertEqual(proposal, Proposal.from_dict(proposal.to_dict()))
        self.assertEqual(len(proposal.fingerprint()), 64)

    def test_code_proposal_round_trip_and_campaign_validation(self) -> None:
        campaign = CampaignSpec.from_dict(code_campaign_data())
        proposal = Proposal.from_dict(code_proposal_data())
        proposal.validate_for_campaign(campaign, incumbent_commit=BASE_COMMIT)
        self.assertEqual(proposal, Proposal.from_dict(proposal.to_dict()))

    def test_config_and_code_payloads_are_mutually_exclusive(self) -> None:
        both = config_proposal_data()
        both["unified_diff"] = code_proposal_data()["unified_diff"]
        with self.assertRaisesRegex(ContractError, "forbid unified_diff"):
            Proposal.from_dict(both)

        neither = code_proposal_data()
        del neither["unified_diff"]
        with self.assertRaisesRegex(ContractError, "require unified_diff"):
            Proposal.from_dict(neither)

    def test_campaign_identity_incumbent_mode_and_paths_are_bound(self) -> None:
        campaign = CampaignSpec.from_dict(config_campaign_data())
        proposal = Proposal.from_dict(config_proposal_data())
        checks = [
            ("campaign_id", "different", "campaign ID"),
            ("base_commit", "b" * 40, "base commit"),
            ("changed_paths", ["agent/d1_rules.py"], "outside campaign scope"),
        ]
        for field, value, message in checks:
            with self.subTest(field=field):
                changed = config_proposal_data()
                changed[field] = value
                with self.assertRaisesRegex(ContractError, message):
                    Proposal.from_dict(changed).validate_for_campaign(
                        campaign, incumbent_commit=BASE_COMMIT
                    )

        code_data = code_proposal_data()
        code_data["campaign_id"] = campaign.campaign_id
        code = Proposal.from_dict(code_data)
        with self.assertRaisesRegex(ContractError, "edit mode"):
            code.validate_for_campaign(campaign, incumbent_commit=BASE_COMMIT)

    def test_parameter_allowlist_type_and_bounds_are_enforced(self) -> None:
        campaign = CampaignSpec.from_dict(config_campaign_data())
        cases = [
            ({"not.allowed": 1}, "not allowlisted"),
            ({"actor.optim.lr": 1.0}, "outside approved bounds"),
            ({"algorithm.actor.update_epoch": 1.5}, "must be integral"),
            ({"algorithm.schedule": "unknown"}, "outside enum choices"),
        ]
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                raw = config_proposal_data()
                raw["config_overrides"] = overrides
                with self.assertRaisesRegex(ContractError, message):
                    Proposal.from_dict(raw).validate_for_campaign(
                        campaign, incumbent_commit=BASE_COMMIT
                    )

    def test_code_diff_requires_header_and_size_limit(self) -> None:
        bad_header = code_proposal_data()
        bad_header["unified_diff"] = "print('not a diff')"
        with self.assertRaisesRegex(ContractError, "Git diff header"):
            Proposal.from_dict(bad_header)

        oversized = code_proposal_data()
        oversized["unified_diff"] = "diff --git a/a b/a\n" + "x" * 65_536
        with self.assertRaisesRegex(ContractError, "may not exceed"):
            Proposal.from_dict(oversized)

    def test_structured_output_schema_is_stable_and_strict(self) -> None:
        schema = proposal_json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(len(schema["oneOf"]), 2)
        self.assertEqual(PROPOSAL_SCHEMA_HASH, __import__("hashlib").sha256(
            PROPOSAL_SCHEMA_JSON.encode("utf-8")
        ).hexdigest())
        self.assertEqual(schema, json.loads(PROPOSAL_SCHEMA_JSON))

    def test_checked_in_proposal_fixtures_are_valid(self) -> None:
        fixtures = [
            ("examples/supervisor/proposal-config.json", config_campaign_data()),
            ("examples/supervisor/proposal-code.json", code_campaign_data()),
        ]
        for path, campaign_data in fixtures:
            with self.subTest(path=path), open(path, encoding="utf-8") as handle:
                proposal = Proposal.from_dict(json.load(handle))
                proposal.validate_for_campaign(
                    CampaignSpec.from_dict(campaign_data), incumbent_commit=BASE_COMMIT
                )


class AttemptAuditTests(unittest.TestCase):
    def test_attempt_round_trip(self) -> None:
        raw = {
            "schema_version": 1,
            "attempt_id": "slot-1.a1",
            "proposal_slot_id": "slot-1",
            "attempt_number": 1,
            "attempt_type": "initial",
            "provider": "fake-provider",
            "model": "opus",
            "context_hash": "a" * 64,
            "schema_hash": "b" * 64,
            "started_at": "2026-08-04T12:00:00Z",
            "completed_at": "2026-08-04T12:00:01Z",
            "timeout_seconds": 600,
            "max_budget_usd": "1",
            "reported_cost_usd": "0.1",
            "input_tokens": 100,
            "output_tokens": 50,
            "response_hash": "c" * 64,
            "status": "accepted",
            "validation_errors": [],
            "proposal_hash": "d" * 64,
        }
        attempt = AttemptAudit.from_dict(raw)
        self.assertEqual(attempt.to_dict(), raw)
        self.assertEqual(len(attempt.fingerprint()), 64)

    def test_attempt_number_and_type_must_agree(self) -> None:
        raw = {
            "schema_version": 1,
            "attempt_id": "slot-1.a1",
            "proposal_slot_id": "slot-1",
            "attempt_number": 1,
            "attempt_type": "repair",
            "provider": "fake-provider",
            "model": "opus",
            "context_hash": "a" * 64,
            "schema_hash": "b" * 64,
            "started_at": "2026-08-04T12:00:00Z",
            "completed_at": "2026-08-04T12:00:01Z",
            "timeout_seconds": 600,
            "max_budget_usd": "1",
            "reported_cost_usd": "0",
            "input_tokens": None,
            "output_tokens": None,
            "response_hash": None,
            "status": "provider_error",
            "validation_errors": ["error"],
            "proposal_hash": None,
        }
        with self.assertRaisesRegex(ContractError, "do not agree"):
            AttemptAudit.from_dict(raw)

    def test_attempt_status_requires_consistent_hashes_errors_and_budget(self) -> None:
        raw = {
            "schema_version": 1,
            "attempt_id": "slot-1.a1",
            "proposal_slot_id": "slot-1",
            "attempt_number": 1,
            "attempt_type": "initial",
            "provider": "fake-provider",
            "model": "opus",
            "context_hash": "a" * 64,
            "schema_hash": "b" * 64,
            "started_at": "2026-08-04T12:00:00Z",
            "completed_at": "2026-08-04T12:00:01Z",
            "timeout_seconds": 600,
            "max_budget_usd": "1",
            "reported_cost_usd": "1.1",
            "input_tokens": 1,
            "output_tokens": 1,
            "response_hash": None,
            "status": "accepted",
            "validation_errors": ["should be empty"],
            "proposal_hash": None,
        }
        with self.assertRaisesRegex(ContractError, "reported cost"):
            AttemptAudit.from_dict(raw)
        raw["reported_cost_usd"] = "0.1"
        with self.assertRaisesRegex(ContractError, "accepted attempts"):
            AttemptAudit.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
