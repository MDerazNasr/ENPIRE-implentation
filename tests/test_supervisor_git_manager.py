from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone

from supervisor.contracts import CampaignSpec, TrialState
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.git_manager import (
    GitExperimentManager,
    GitOperationError,
    HarnessCheck,
    PreparationStatus,
    append_preparation_to_ledger,
)
from supervisor.ledger import EntityType, EventLedger
from supervisor.proposals import Proposal
from tests.test_supervisor_enforcement import base_config
from tests.test_supervisor_proposals import (
    code_campaign_data,
    code_proposal_data,
    config_campaign_data,
    config_proposal_data,
)


BASE_SOURCE = (
    "import torch\n"
    "\n"
    "def objective(actor_loss, bc_loss, weight):\n"
    "    return actor_loss + weight * bc_loss\n"
)


def run_git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class GitManagerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repository = root / "stable"
        self.worktrees = root / "worktrees"
        self.repository.mkdir()
        self.worktrees.mkdir()
        run_git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "candidates").mkdir()
        (self.repository / "candidates" / "actor_objective.py").write_text(
            BASE_SOURCE,
            encoding="utf-8",
        )
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        run_git(self.repository, "add", ".")
        run_git(
            self.repository,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@invalid.local",
            "commit",
            "-q",
            "-m",
            "fixture base",
        )
        self.base_commit = run_git(self.repository, "rev-parse", "HEAD")

    def campaign(self, mode: str) -> CampaignSpec:
        raw = config_campaign_data() if mode == "config" else code_campaign_data()
        raw["campaign_id"] = f"m3-{mode}-campaign"
        raw["baseline_commit"] = self.base_commit
        return CampaignSpec.from_dict(raw)

    def config_proposal(
        self,
        *,
        proposal_id: str = "config-01",
        learning_rate: float = 0.00005,
    ) -> Proposal:
        raw = config_proposal_data()
        raw["proposal_id"] = proposal_id
        raw["campaign_id"] = "m3-config-campaign"
        raw["base_commit"] = self.base_commit
        raw["config_overrides"] = {"actor.optim.lr": learning_rate}
        return Proposal.from_dict(raw)

    def code_proposal(
        self,
        *,
        proposal_id: str = "code-01",
        replacement: str = "    return actor_loss + torch.clamp(weight, max=1.0) * bc_loss",
    ) -> Proposal:
        raw = code_proposal_data()
        raw["proposal_id"] = proposal_id
        raw["campaign_id"] = "m3-code-campaign"
        raw["base_commit"] = self.base_commit
        raw["unified_diff"] = (
            "diff --git a/candidates/actor_objective.py "
            "b/candidates/actor_objective.py\n"
            "--- a/candidates/actor_objective.py\n"
            "+++ b/candidates/actor_objective.py\n"
            "@@ -1,4 +1,4 @@\n"
            " import torch\n"
            " \n"
            " def objective(actor_loss, bc_loss, weight):\n"
            "-    return actor_loss + weight * bc_loss\n"
            f"+{replacement}\n"
        )
        return Proposal.from_dict(raw)

    @staticmethod
    def check(check_id: str, script: str = "pass") -> HarnessCheck:
        return HarnessCheck.create(
            check_id=check_id,
            argv=(sys.executable, "-c", script),
            timeout_seconds=10,
        )

    def manager(
        self,
        *,
        config_script: str = "pass",
        dry_run_script: str = "pass",
    ) -> GitExperimentManager:
        checks = {
            "config-contract": self.check("config-contract", config_script),
            "dry-run": self.check("dry-run", dry_run_script),
        }
        policy = EnforcementPolicy.create(trusted_test_ids=list(checks))
        return GitExperimentManager(
            repository=self.repository,
            worktree_root=self.worktrees,
            enforcer=ProposalEnforcer(policy),
            trusted_checks=checks,
        )

    def test_config_candidate_is_committed_without_moving_stable_head(self) -> None:
        manager = self.manager(
            config_script=(
                "import json, pathlib; "
                "d=json.loads(pathlib.Path('candidates/config_override.json').read_text()); "
                "assert d['actor']['optim']['lr'] == 0.00005"
            )
        )
        record = manager.prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(record.status, PreparationStatus.READY)
        self.assertEqual(record.stable_head_before, self.base_commit)
        self.assertEqual(record.stable_head_after, self.base_commit)
        self.assertNotEqual(record.candidate_commit, self.base_commit)
        self.assertEqual(len(record.checks), 2)
        self.assertTrue(all(item.passed for item in record.checks))
        self.assertEqual(len(record.base_config_hash), 64)
        self.assertEqual(len(record.overrides_hash), 64)
        self.assertEqual(len(record.resolved_config_hash), 64)
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)
        parent = run_git(Path(record.worktree_path), "rev-parse", "HEAD^")
        self.assertEqual(parent, self.base_commit)
        self.assertEqual(len(record.fingerprint()), 64)

    def test_code_candidate_is_applied_source_checked_and_committed(self) -> None:
        record = self.manager().prepare(
            self.code_proposal(),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(record.status, PreparationStatus.READY)
        target = Path(record.worktree_path) / "candidates" / "actor_objective.py"
        self.assertIn("torch.clamp", target.read_text(encoding="utf-8"))
        self.assertEqual(record.changed_paths, ("candidates/actor_objective.py",))
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)
        snapshot = self.manager().discover("m3-code-campaign", "code-01")
        self.assertTrue(snapshot.exists)
        self.assertEqual(snapshot.branch_commit, record.candidate_commit)
        self.assertEqual(snapshot.worktree_head, record.candidate_commit)
        self.assertFalse(snapshot.changed_paths)

    def test_failed_check_retains_hypothesis_and_preserves_incumbent(self) -> None:
        record = self.manager(dry_run_script="raise SystemExit(7)").prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(record.status, PreparationStatus.FAILED)
        self.assertIsNone(record.candidate_commit)
        self.assertTrue(Path(record.worktree_path).is_dir())
        self.assertEqual(
            run_git(self.repository, "show-ref", "--hash", record.branch_name),
            self.base_commit,
        )
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)
        snapshot = self.manager().discover("m3-config-campaign", "config-01")
        self.assertEqual(snapshot.branch_commit, self.base_commit)
        self.assertEqual(
            snapshot.changed_paths, ("candidates/config_override.json",)
        )

    def test_check_cannot_leave_an_undeclared_file(self) -> None:
        script = "from pathlib import Path; Path('unexpected.txt').write_text('x')"
        record = self.manager(dry_run_script=script).prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(record.status, PreparationStatus.FAILED)
        self.assertIn("do not match expected paths", record.errors[0])
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_unsafe_source_is_rejected_after_apply(self) -> None:
        proposal = self.code_proposal(replacement="    return os.getenv('SECRET')")
        raw = proposal.to_dict()
        raw["unified_diff"] = raw["unified_diff"].replace(
            " import torch\n", " import torch\n+import os\n"
        ).replace("@@ -1,4 +1,4 @@", "@@ -1,4 +1,5 @@")
        record = self.manager().prepare(
            Proposal.from_dict(raw),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(record.status, PreparationStatus.FAILED)
        self.assertIn("candidate source policy rejected", record.errors[0])
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_static_rejection_creates_no_branch_or_worktree(self) -> None:
        raw = self.code_proposal().to_dict()
        raw["unified_diff"] = raw["unified_diff"].replace(
            "candidates/actor_objective.py", "agent/d1_rules.py"
        )
        record = self.manager().prepare(
            Proposal.from_dict(raw),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(record.status, PreparationStatus.REJECTED)
        self.assertIsNone(record.branch_name)
        self.assertIsNone(record.worktree_path)
        self.assertFalse(any(self.worktrees.iterdir()))

    def test_two_hypotheses_are_isolated_from_each_other(self) -> None:
        manager = self.manager()
        first = manager.prepare(
            self.config_proposal(proposal_id="config-01", learning_rate=0.00005),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        second = manager.prepare(
            self.config_proposal(proposal_id="config-02", learning_rate=0.00008),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(first.status, PreparationStatus.READY)
        self.assertEqual(second.status, PreparationStatus.READY)
        self.assertNotEqual(first.branch_name, second.branch_name)
        self.assertNotEqual(first.worktree_path, second.worktree_path)
        first_data = json.loads(
            (Path(first.worktree_path) / "candidates/config_override.json").read_text()
        )
        second_data = json.loads(
            (Path(second.worktree_path) / "candidates/config_override.json").read_text()
        )
        self.assertEqual(first_data["actor"]["optim"]["lr"], 0.00005)
        self.assertEqual(second_data["actor"]["optim"]["lr"], 0.00008)
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_dirty_stable_repository_and_unapplicable_patch_fail_closed(self) -> None:
        (self.repository / "dirty.txt").write_text("dirty", encoding="utf-8")
        dirty = self.manager().prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(dirty.status, PreparationStatus.FAILED)
        self.assertIn("must be clean", dirty.errors[0])
        os.unlink(self.repository / "dirty.txt")

        raw = self.code_proposal(proposal_id="bad-patch").to_dict()
        raw["unified_diff"] = raw["unified_diff"].replace(
            "-    return actor_loss + weight * bc_loss",
            "-    return a line that does not exist",
        )
        failed = self.manager().prepare(
            Proposal.from_dict(raw),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(failed.status, PreparationStatus.FAILED)
        self.assertIn("Git operation 'apply' failed", failed.errors[0])
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_repeated_proposal_is_not_duplicated_and_can_be_rediscovered(self) -> None:
        manager = self.manager()
        proposal = self.config_proposal()
        campaign = self.campaign("config")
        first = manager.prepare(
            proposal,
            campaign,
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        second = manager.prepare(
            proposal,
            campaign,
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(first.status, PreparationStatus.READY)
        self.assertEqual(second.status, PreparationStatus.FAILED)
        self.assertIn("branch already exists", second.errors[0])
        snapshot = manager.discover("m3-config-campaign", "config-01")
        self.assertEqual(snapshot.branch_commit, first.candidate_commit)
        self.assertEqual(snapshot.worktree_head, first.candidate_commit)

    def test_symlink_target_is_rejected_without_touching_external_file(self) -> None:
        external = Path(self.temp.name) / "outside.py"
        external.write_text("outside = True\n", encoding="utf-8")
        target = self.repository / "candidates" / "actor_objective.py"
        target.unlink()
        target.symlink_to(external)
        run_git(self.repository, "add", "candidates/actor_objective.py")
        run_git(
            self.repository,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@invalid.local",
            "commit",
            "-q",
            "-m",
            "symlink fixture",
        )
        self.base_commit = run_git(self.repository, "rev-parse", "HEAD")
        record = self.manager().prepare(
            self.code_proposal(proposal_id="symlink-01"),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(record.status, PreparationStatus.FAILED)
        self.assertIn("traverses a symlink", record.errors[0])
        self.assertEqual(external.read_text(encoding="utf-8"), "outside = True\n")
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_ready_preparation_advances_trial_ledger_idempotently(self) -> None:
        record = self.manager().prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        ledger = EventLedger(
            Path(self.temp.name) / "trial-ready.jsonl",
            campaign_id="m3-config-campaign",
            entity_type=EntityType.TRIAL,
            entity_id="trial-ready",
        )
        events = append_preparation_to_ledger(
            ledger,
            record,
            at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
        )
        self.assertEqual([item.to_state for item in events], ["proposal_validated", "queued"])
        self.assertEqual(ledger.read().state, TrialState.QUEUED)
        self.assertEqual(append_preparation_to_ledger(ledger, record), ())
        self.assertEqual(
            ledger.read().events[-1].metadata["preparation_hash"],
            record.fingerprint(),
        )

    def test_static_rejection_advances_trial_directly_to_failed(self) -> None:
        raw = self.code_proposal().to_dict()
        raw["unified_diff"] = raw["unified_diff"].replace(
            "candidates/actor_objective.py", "agent/d1_rules.py"
        )
        record = self.manager().prepare(
            Proposal.from_dict(raw),
            self.campaign("code"),
            incumbent_commit=self.base_commit,
        )
        ledger = EventLedger(
            Path(self.temp.name) / "trial-rejected.jsonl",
            campaign_id="m3-code-campaign",
            entity_type=EntityType.TRIAL,
            entity_id="trial-rejected",
        )
        events = append_preparation_to_ledger(ledger, record)
        self.assertEqual([item.to_state for item in events], ["failed"])
        self.assertEqual(ledger.read().state, TrialState.FAILED)

    def test_public_records_reject_forged_ready_or_rejected_states(self) -> None:
        record = self.manager().prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        with self.assertRaisesRegex(GitOperationError, "ready preparation"):
            replace(record, stable_head_after="b" * 40)
        with self.assertRaisesRegex(GitOperationError, "rejected preparation"):
            replace(
                record,
                status=PreparationStatus.REJECTED,
                errors=("forged rejection",),
            )
        with self.assertRaisesRegex(GitOperationError, "must be absolute"):
            HarnessCheck(
                check_id="forged-check",
                argv=("python", "-c", "pass"),
                timeout_seconds=10,
            )

    def test_repository_hooks_are_disabled_for_worktree_and_commit(self) -> None:
        checkout_marker = Path(self.temp.name) / "post-checkout-ran"
        commit_marker = Path(self.temp.name) / "post-commit-ran"
        hooks = self.repository / ".git" / "hooks"
        hook_data = {
            "post-checkout": checkout_marker,
            "post-commit": commit_marker,
        }
        for name, marker in hook_data.items():
            hook = hooks / name
            hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
            hook.chmod(0o755)
        record = self.manager().prepare(
            self.config_proposal(),
            self.campaign("config"),
            incumbent_commit=self.base_commit,
            base_config=base_config(),
        )
        self.assertEqual(record.status, PreparationStatus.READY)
        self.assertFalse(checkout_marker.exists())
        self.assertFalse(commit_marker.exists())


if __name__ == "__main__":
    unittest.main()
