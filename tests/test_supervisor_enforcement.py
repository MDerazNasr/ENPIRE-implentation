from __future__ import annotations

import copy
import json
import unittest

from supervisor.canonical import ContractError
from supervisor.contracts import CampaignSpec
from supervisor.enforcement import (
    EnforcementPolicy,
    PolicyError,
    ProposalEnforcer,
    materialize_config,
    parse_unified_diff,
    validate_python_source,
)
from supervisor.proposals import Proposal
from tests.test_supervisor_proposals import (
    BASE_COMMIT,
    code_campaign_data,
    code_proposal_data,
    config_campaign_data,
    config_proposal_data,
)


def policy() -> EnforcementPolicy:
    return EnforcementPolicy.create(
        trusted_test_ids=["config-contract", "dry-run"]
    )


def base_config() -> dict:
    return {
        "actor": {"optim": {"lr": 0.0001}},
        "algorithm": {
            "actor": {"update_epoch": 2},
            "schedule": "upstream",
        },
    }


class DiffParserTests(unittest.TestCase):
    def test_valid_patch_returns_exact_paths_and_hunks(self) -> None:
        files = parse_unified_diff(code_proposal_data()["unified_diff"])
        self.assertEqual([item.path for item in files], ["candidates/actor_objective.py"])
        self.assertEqual(files[0].hunk_count, 1)

    def test_renames_binary_modes_submodules_and_duplicate_sections_fail(self) -> None:
        cases = {
            "rename": (
                "diff --git a/a.py b/b.py\n--- a/a.py\n+++ b/b.py\n"
                "@@ -1 +1 @@\n-a\n+b\n"
            ),
            "binary": (
                "diff --git a/a.py b/a.py\nGIT binary patch\n"
                "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
            ),
            "mode": (
                "diff --git a/a.py b/a.py\nold mode 100644\nnew mode 100755\n"
                "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
            ),
            "submodule": (
                "diff --git a/a.py b/a.py\nindex 1111111..2222222 160000\n"
                "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n"
                "-Subproject commit 1111111\n+Subproject commit 2222222\n"
            ),
            "duplicate": code_proposal_data()["unified_diff"] * 2,
        }
        for name, diff in cases.items():
            with self.subTest(name=name), self.assertRaises(PolicyError):
                parse_unified_diff(diff)

    def test_missing_headers_hunks_and_noncanonical_paths_fail(self) -> None:
        cases = [
            "diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-a\n+b\n",
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n",
            (
                "diff --git a/a//b.py b/a//b.py\n--- a/a//b.py\n+++ b/a//b.py\n"
                "@@ -1 +1 @@\n-a\n+b\n"
            ),
        ]
        for diff in cases:
            with self.subTest(diff=diff), self.assertRaises(PolicyError):
                parse_unified_diff(diff)


class ProposalEnforcerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enforcer = ProposalEnforcer(policy())

    def test_valid_config_and_code_proposals_are_accepted(self) -> None:
        cases = [
            (config_campaign_data(), config_proposal_data()),
            (code_campaign_data(), code_proposal_data()),
        ]
        for campaign_data, proposal_data in cases:
            with self.subTest(mode=proposal_data["edit_mode"]):
                report = self.enforcer.validate(
                    Proposal.from_dict(proposal_data),
                    CampaignSpec.from_dict(campaign_data),
                    incumbent_commit=BASE_COMMIT,
                )
                self.assertTrue(report.accepted)
                self.assertFalse(report.violations)
                self.assertEqual(len(report.fingerprint()), 64)

    def test_untrusted_tests_budget_and_stale_incumbent_are_rejected(self) -> None:
        cases = []
        untrusted = config_proposal_data()
        untrusted["requested_tests"] = ["agent-authored-test"]
        cases.append((untrusted, BASE_COMMIT, "untrusted_test"))
        expensive = config_proposal_data()
        expensive["estimated_budget"]["gpu_cost_usd"] = "99"
        cases.append((expensive, BASE_COMMIT, "budget_exceeded"))
        cases.append((config_proposal_data(), "b" * 40, "proposal_contract"))
        campaign = CampaignSpec.from_dict(config_campaign_data())
        for raw, incumbent, code in cases:
            with self.subTest(code=code):
                report = self.enforcer.validate(
                    Proposal.from_dict(raw), campaign, incumbent_commit=incumbent
                )
                self.assertFalse(report.accepted)
                self.assertIn(code, {item.code for item in report.violations})

    def test_declared_and_parsed_paths_must_match_exactly(self) -> None:
        raw = code_proposal_data()
        raw["unified_diff"] = raw["unified_diff"].replace(
            "candidates/actor_objective.py", "agent/d1_rules.py"
        )
        report = self.enforcer.validate(
            Proposal.from_dict(raw),
            CampaignSpec.from_dict(code_campaign_data()),
            incumbent_commit=BASE_COMMIT,
        )
        self.assertFalse(report.accepted)
        self.assertIn("path_mismatch", {item.code for item in report.violations})

    def test_multiple_files_and_non_json_config_target_are_rejected(self) -> None:
        campaign_data = config_campaign_data()
        campaign_data["editable_paths"] = ["a.json", "b.yaml"]
        raw = config_proposal_data()
        raw["changed_paths"] = ["a.json", "b.yaml"]
        report = self.enforcer.validate(
            Proposal.from_dict(raw),
            CampaignSpec.from_dict(campaign_data),
            incumbent_commit=BASE_COMMIT,
        )
        codes = {item.code for item in report.violations}
        self.assertIn("too_many_files", codes)
        self.assertIn("config_target", codes)


class SourcePolicyTests(unittest.TestCase):
    def test_safe_actor_objective_source_is_accepted(self) -> None:
        source = b"import torch\n\ndef objective(a, b):\n    return torch.add(a, b)\n"
        self.assertEqual(
            validate_python_source("candidates/actor_objective.py", source, policy()),
            (),
        )

    def test_forbidden_import_calls_dunder_syntax_binary_and_size_fail(self) -> None:
        cases = {
            "import": b"import os\n",
            "call": b"def f():\n    return open('secret')\n",
            "dunder": b"def f(x):\n    return x.__class__\n",
            "syntax": b"def broken(:\n",
            "binary": b"abc\x00def",
            "size": b"x" * 131_073,
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                self.assertTrue(
                    validate_python_source(
                        "candidates/actor_objective.py", source, policy()
                    )
                )


class ConfigMaterializationTests(unittest.TestCase):
    def test_materialization_is_deterministic_and_changes_only_allowlisted_leaf(self) -> None:
        proposal = Proposal.from_dict(config_proposal_data())
        campaign = CampaignSpec.from_dict(config_campaign_data())
        first = materialize_config(
            proposal,
            campaign,
            base_config(),
            incumbent_commit=BASE_COMMIT,
        )
        second = materialize_config(
            proposal,
            campaign,
            copy.deepcopy(base_config()),
            incumbent_commit=BASE_COMMIT,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.target_path, "candidates/config_override.json")
        resolved = json.loads(first.rendered_json)
        self.assertEqual(resolved["actor"]["optim"]["lr"], 0.00005)
        self.assertEqual(len(first.resolved_config_hash), 64)

    def test_missing_leaf_container_leaf_and_stale_incumbent_fail(self) -> None:
        campaign = CampaignSpec.from_dict(config_campaign_data())
        proposal = Proposal.from_dict(config_proposal_data())
        with self.assertRaisesRegex(PolicyError, "does not exist"):
            materialize_config(
                proposal,
                campaign,
                {},
                incumbent_commit=BASE_COMMIT,
            )
        nested = base_config()
        nested["actor"]["optim"]["lr"] = {"nested": True}
        with self.assertRaisesRegex(PolicyError, "not a scalar"):
            materialize_config(
                proposal,
                campaign,
                nested,
                incumbent_commit=BASE_COMMIT,
            )
        with self.assertRaisesRegex(ContractError, "base commit"):
            materialize_config(
                proposal,
                campaign,
                base_config(),
                incumbent_commit="b" * 40,
            )


if __name__ == "__main__":
    unittest.main()
