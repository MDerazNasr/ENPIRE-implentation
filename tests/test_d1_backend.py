from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agent.d1_config import load_d1_config
from supervisor.contracts import ApprovalEnvelope, EngineeringAcceptanceApproval
from supervisor.attempts import ProposalSessionResult
from supervisor.contracts import CampaignSpec, Decision, TrialEvidence
from supervisor.coordinator import IterationStatus, OfflineCampaignCoordinator
from supervisor.d1_backend import (
    BackendStatus,
    D1BackendError,
    D1ExperimentBackend,
    D1CoordinatorContractFactory,
    D1PlanBuilder,
    D1ProcessWorker,
    ExecutionMode,
    M5Authorization,
    ProcessOutcome,
    synchronize_d1_config,
)
from supervisor.d1_gate import D1EvidencePack, D1GateStatus, run_d1_integration_gate
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator
from supervisor.git_manager import GitExperimentManager, HarnessCheck
from supervisor.proposals import Proposal
from tests.test_d1_integration_gate import pack_data
from tests.test_supervisor_contracts import approval_data


ROOT = Path(__file__).resolve().parents[1]


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def commit(repository: Path, message: str) -> str:
    git(repository, "add", ".")
    git(
        repository,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@invalid.local",
        "commit", "-q", "-m", message,
    )
    return git(repository, "rev-parse", "HEAD")


class NoCallTransport:
    def run(self, argv, *, cwd, timeout_seconds):
        raise AssertionError("dry-run must not invoke a process")


class TimeoutTransport:
    def run(self, argv, *, cwd, timeout_seconds):
        return ProcessOutcome(
            return_code=None,
            started_at="2026-08-04T12:00:00Z",
            finished_at="2026-08-04T12:00:01Z",
            elapsed_seconds=1,
            stdout_hash="a" * 64,
            stderr_hash="b" * 64,
            timed_out=True,
        )


class D1BackendIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "d1"
        self.repository.mkdir()
        git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "candidates").mkdir()
        config = load_d1_config(ROOT / "configs" / "d1" / "control.yaml")
        config["fixture_success_rate"] = 0.5
        config["fixture_episode_length"] = 40
        self.config_path = self.repository / "candidates" / "config_override.json"
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        self.incumbent = commit(self.repository, "control incumbent")
        candidate_config = copy.deepcopy(config)
        candidate_config["condition"] = "candidate"
        candidate_config["scientific_values"]["online_bc_weight"] = 2.0
        self.config_path.write_text(
            json.dumps(candidate_config, indent=2), encoding="utf-8"
        )
        self.candidate = commit(self.repository, "configuration candidate")
        self.workspace = self.root / "candidate-worktree"
        git(
            self.repository,
            "worktree", "add", "--detach", str(self.workspace), self.candidate,
        )
        payload = pack_data(
            incumbent=self.incumbent,
            candidate=self.candidate,
            known_good=self.candidate,
        )
        self.pack = D1EvidencePack.from_dict(payload)
        (self.repository / "docs").mkdir()
        (self.repository / "docs" / "execution_checklist.md").write_text(
            "## Stage 7 — D1 evidence pack\n"
            "- [x] Commands and configs.\n"
            "- [x] Run table and plots.\n"
            "- [x] Costs and limitations.\n"
            "- [x] Conclusion.\n\n## Later\n",
            encoding="utf-8",
        )
        pack_path = self.repository / "results" / "d1-stage7" / "evidence_pack.json"
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        commit(self.repository, "reviewed Stage 7 pack")
        self.gate = run_d1_integration_gate(self.repository)
        self.assertEqual(self.gate.status, D1GateStatus.READY)
        self.campaign = self.pack.campaign
        self.results_root = self.root / "worker-results"
        self.builder = D1PlanBuilder(
            results_root=self.results_root,
            python_executable=Path(sys.executable),
            fixture_launcher=ROOT / "scripts" / "m5_fixture_launcher.py",
            environment={
                "RLINF_HOME": "/opt/rlinf",
                "STAGE1_CHECKPOINT": "/opt/checkpoints/stage1",
                "NORM_STATS_PATH": "/opt/checkpoints/norm.json",
                "WANDB_PROJECT": "m5-tests",
                "D1_SEED": "2027",
            },
        )

    def plan(self, mode: ExecutionMode, trial_id: str):
        return self.builder.build(
            campaign=self.campaign,
            workspace=self.workspace,
            source_config_relative_path="candidates/config_override.json",
            trial_id=trial_id,
            arm_id="config-arm",
            parent_commit=self.incumbent,
            candidate_commit=self.candidate,
            seed=2027,
            max_wall_time_seconds=30,
            max_gpu_cost_usd="1",
            mode=mode,
        )

    def test_config_synchronization_changes_actual_hydra_value_and_seed(self) -> None:
        source = json.loads(
            (self.workspace / "candidates" / "config_override.json").read_text()
        )
        original = copy.deepcopy(source)
        derived = synchronize_d1_config(source, seed=2028)
        overrides = {
            item.split("=", 1)[0]: item.split("=", 1)[1]
            for item in derived["hydra_overrides"]
        }
        self.assertEqual(
            overrides["algorithm.actor_weight_schedule.online_bc_weight"], "2.0"
        )
        self.assertEqual(overrides["actor.seed"], "2028")
        self.assertEqual(source, original)

    def test_dry_run_is_default_and_invokes_no_process(self) -> None:
        plan = self.plan(ExecutionMode.DRY_RUN, "dry-run-2027")
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.DRY_RUN,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
        )
        result = D1ExperimentBackend(NoCallTransport()).run(plan, authorization)
        self.assertEqual(result.status, BackendStatus.PLANNED)
        self.assertIsNone(result.evidence)
        self.assertNotIn("--execute", plan.execution_argv)
        self.assertNotIn("--acknowledge-paid-run", plan.execution_argv)

    def test_paid_authorization_requires_approval_gate_and_acknowledgement(self) -> None:
        approval = ApprovalEnvelope.from_dict(approval_data(self.campaign))
        at = datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
        with self.assertRaisesRegex(D1BackendError, "approval"):
            M5Authorization.create(
                campaign=self.campaign,
                mode=ExecutionMode.PAID,
                authorized_at=at,
                gate=self.gate,
                acknowledge_paid_run=True,
            )
        with self.assertRaisesRegex(D1BackendError, "acknowledgement"):
            M5Authorization.create(
                campaign=self.campaign,
                mode=ExecutionMode.PAID,
                authorized_at=at,
                approval=approval,
                gate=self.gate,
            )
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.PAID,
            authorized_at=at,
            approval=approval,
            gate=self.gate,
            acknowledge_paid_run=True,
        )
        plan = self.plan(ExecutionMode.PAID, "paid-plan-2027")
        self.assertTrue(authorization.paid_acknowledged)
        self.assertIn("--execute", plan.execution_argv)
        self.assertIn("--acknowledge-paid-run", plan.execution_argv)

    def test_paid_acceptance_requires_approval_but_rejects_scientific_gate(self) -> None:
        approval = ApprovalEnvelope.from_dict(approval_data(self.campaign))
        acceptance_approval = EngineeringAcceptanceApproval.from_dict(
            {
                "schema_version": 1,
                "campaign_approval": approval.to_dict(),
                "profile_hash": "d" * 64,
                "provider": "Modal",
                "provider_profile": "fixture-profile",
                "max_total_cost_usd": "100",
                "promotion_allowed": False,
            }
        )
        at = datetime(2026, 8, 4, 13, tzinfo=timezone.utc)
        with self.assertRaisesRegex(D1BackendError, "engineering-test flag"):
            M5Authorization.create(
                campaign=self.campaign,
                mode=ExecutionMode.PAID_ACCEPTANCE,
                authorized_at=at,
                acceptance_approval=acceptance_approval,
                acknowledge_paid_run=True,
            )
        with self.assertRaisesRegex(D1BackendError, "scientific integration gate"):
            M5Authorization.create(
                campaign=self.campaign,
                mode=ExecutionMode.PAID_ACCEPTANCE,
                authorized_at=at,
                acceptance_approval=acceptance_approval,
                gate=self.gate,
                acknowledge_paid_run=True,
                allow_paid_acceptance=True,
            )
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.PAID_ACCEPTANCE,
            authorized_at=at,
            acceptance_approval=acceptance_approval,
            acknowledge_paid_run=True,
            allow_paid_acceptance=True,
        )
        plan = self.plan(ExecutionMode.PAID_ACCEPTANCE, "acceptance-plan-2027")
        D1ExperimentBackend._validate(plan, authorization)
        self.assertIsNotNone(authorization.approval_hash)
        self.assertIsNone(authorization.gate_hash)
        self.assertFalse(authorization.synthetic)
        self.assertIn("--execute", plan.execution_argv)
        self.assertIn("--acknowledge-paid-run", plan.execution_argv)

    def test_blocked_gate_cannot_authorize_paid_execution(self) -> None:
        (self.repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        blocked = run_d1_integration_gate(self.repository)
        approval = ApprovalEnvelope.from_dict(approval_data(self.campaign))
        with self.assertRaisesRegex(D1BackendError, "ready D1"):
            M5Authorization.create(
                campaign=self.campaign,
                mode=ExecutionMode.PAID,
                authorized_at=datetime(2026, 8, 4, 13, tzinfo=timezone.utc),
                approval=approval,
                gate=blocked,
                acknowledge_paid_run=True,
            )

    def test_authorization_cannot_be_reused_for_another_campaign(self) -> None:
        plan = self.plan(ExecutionMode.DRY_RUN, "campaign-bound-dry-run")
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.DRY_RUN,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
        )
        forged = replace(authorization, campaign_hash="f" * 64)
        with self.assertRaisesRegex(D1BackendError, "another campaign"):
            D1ExperimentBackend(NoCallTransport()).run(plan, forged)

    def test_real_fixture_subprocess_produces_strict_synthetic_evidence(self) -> None:
        plan = self.plan(ExecutionMode.FIXTURE, "fixture-2027")
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.FIXTURE,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
            allow_fixture_execution=True,
        )
        result = D1ExperimentBackend().run(plan, authorization)
        self.assertEqual(result.status, BackendStatus.COMPLETE)
        self.assertTrue(result.synthetic)
        self.assertEqual(result.evidence.metrics["success_rate"], 0.5)
        self.assertEqual(
            result.evidence.metrics["successful_episode_length"], 40
        )
        self.assertEqual(result.evidence.seed, 2027)
        self.assertIn("wandb.ai/fixture", result.wandb_run_url)
        self.assertEqual(len(result.evidence.artifacts), 3)

    def test_timeout_fails_without_inventing_evidence(self) -> None:
        plan = self.plan(ExecutionMode.FIXTURE, "timeout-2027")
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.FIXTURE,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
            allow_fixture_execution=True,
        )
        result = D1ExperimentBackend(TimeoutTransport()).run(plan, authorization)
        self.assertEqual(result.status, BackendStatus.TIMED_OUT)
        self.assertIsNone(result.evidence)

    def test_tampered_manifest_and_cost_overrun_are_invalid_evidence(self) -> None:
        for trial_id, mutation in (
            ("tampered-commit", ("project_commit", "9" * 40)),
            ("cost-overrun", ("run_cost_usd", 2)),
        ):
            with self.subTest(trial_id=trial_id):
                plan = self.plan(ExecutionMode.FIXTURE, trial_id)
                authorization = M5Authorization.create(
                    campaign=self.campaign,
                    mode=ExecutionMode.FIXTURE,
                    authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
                    allow_fixture_execution=True,
                )
                initial = D1ExperimentBackend().run(plan, authorization)
                self.assertEqual(initial.status, BackendStatus.COMPLETE)
                manifest_path = Path(plan.manifest_path)
                manifest = json.loads(manifest_path.read_text())
                manifest[mutation[0]] = mutation[1]
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                from supervisor.d1_backend import normalize_d1_evidence
                with self.assertRaises(D1BackendError):
                    normalize_d1_evidence(plan, require_wandb=False)

    def test_wrong_or_dirty_workspace_is_rejected(self) -> None:
        (self.workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(D1BackendError, "clean"):
            self.plan(ExecutionMode.DRY_RUN, "dirty-workspace")


class D1CoordinatorFixtureIntegrationTests(unittest.TestCase):
    """Exercise proposal -> Git -> real subprocess -> evidence -> decision."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "stable"
        self.repository.mkdir()
        git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "README.md").write_text("M5 fixture\n", encoding="utf-8")
        self.base_commit = commit(self.repository, "stable baseline")
        raw = pack_data(
            incumbent=self.base_commit,
            candidate=self.base_commit,
            known_good=self.base_commit,
        )["campaign"]
        raw["campaign_id"] = "m5-subprocess-fixture"
        raw["baseline_commit"] = self.base_commit
        raw["edit_mode"] = "config_only"
        raw["editable_paths"] = ["candidates/config_override.json"]
        raw["allowed_parameters"] = {
            "scientific_values.online_bc_weight": {
                "kind": "number",
                "minimum": "0",
                "maximum": "10",
            }
        }
        self.campaign = CampaignSpec.from_dict(raw)
        proposal_raw = {
            "schema_version": 1,
            "proposal_id": "m5-config-candidate",
            "campaign_id": self.campaign.campaign_id,
            "arm_id": "rlt-config",
            "base_commit": self.base_commit,
            "edit_mode": "config_only",
            "hypothesis": "A bounded BC-weight change improves fixed-reset success.",
            "evidence_ids": ["d1-control-b"],
            "expected_effect": "Increase success rate under the same evaluator.",
            "falsification_condition": "Candidate success does not improve.",
            "rollback_condition": "Revert unless the frozen evaluator keeps it.",
            "changed_paths": ["candidates/config_override.json"],
            "requested_tests": ["config-contract", "dry-run"],
            "estimated_budget": {
                "wall_time_seconds": 30,
                "gpu_cost_usd": "0.3",
                "llm_cost_usd": "0",
            },
            "config_overrides": {"scientific_values.online_bc_weight": 2.0},
        }
        self.proposal = Proposal.from_dict(proposal_raw)
        self.session = ProposalSessionResult(
            proposal_slot_id="m5-fixture-slot",
            accepted=True,
            proposal=self.proposal,
            attempts=(),
            total_cost_usd="0",
        )
        self.base_config = load_d1_config(ROOT / "configs" / "d1" / "control.yaml")
        self.base_config["fixture_success_rate"] = 0.5
        self.base_config["fixture_episode_length"] = 40

    def _manager(self) -> GitExperimentManager:
        (self.root / "worktrees").mkdir(exist_ok=True)
        checks = {
            name: HarnessCheck.create(
                check_id=name,
                argv=(sys.executable, "-c", "pass"),
                timeout_seconds=10,
            )
            for name in ("config-contract", "dry-run")
        }
        return GitExperimentManager(
            repository=self.repository,
            worktree_root=self.root / "worktrees",
            enforcer=ProposalEnforcer(
                EnforcementPolicy.create(trusted_test_ids=list(checks))
            ),
            trusted_checks=checks,
        )

    def _control_evidence(self) -> list[TrialEvidence]:
        return [
            TrialEvidence.from_dict(
                {
                    "schema_version": 1,
                    "campaign_id": self.campaign.campaign_id,
                    "trial_id": f"control.s{seed}",
                    "arm_id": "control",
                    "parent_commit": self.base_commit,
                    "candidate_commit": self.base_commit,
                    "rlinf_commit": self.campaign.rlinf_commit,
                    "config_hash": "a" * 64,
                    "command_hash": "b" * 64,
                    "seed": seed,
                    "reset_set_hash": self.campaign.reset_set_hash,
                    "evaluator_version": self.campaign.evaluator_version,
                    "started_at": "2026-08-04T11:00:00Z",
                    "finished_at": "2026-08-04T11:01:00Z",
                    "status": "complete",
                    "exit_code": 0,
                    "elapsed_seconds": 60,
                    "gpu_cost_usd": "0.01",
                    "llm_cost_usd": "0",
                    "metrics": {
                        "success_rate": 0.4,
                        "successful_episode_length": 45,
                    },
                    "metric_errors": [],
                    "artifacts": [],
                }
            )
            for seed in self.campaign.seeds
        ]

    def test_full_coordinator_path_uses_real_fixture_subprocesses(self) -> None:
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.FIXTURE,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
            allow_fixture_execution=True,
        )
        worker = D1ProcessWorker(worker_id="m5-subprocess-worker")
        factory = D1CoordinatorContractFactory(
            builder=D1PlanBuilder(
                results_root=self.root / "worker-results",
                python_executable=Path(sys.executable),
                fixture_launcher=ROOT / "scripts" / "m5_fixture_launcher.py",
            ),
            worker=worker,
            authorization=authorization,
        )
        store = ArmIncumbentStore(
            self.root / "state" / "incumbents.json",
            campaign_id=self.campaign.campaign_id,
            initial_incumbents={self.proposal.arm_id: self.base_commit},
        )
        result = OfflineCampaignCoordinator(
            campaign=self.campaign,
            git_manager=self._manager(),
            worker=worker,
            evaluator=OfflineD1Evaluator(),
            incumbents=store,
            ledger_root=self.root / "ledgers",
            run_contract_factory=factory,
            synthetic=True,
        ).run(
            iteration_id="m5-fixture-iteration",
            proposal_session=self.session,
            control_evidence=self._control_evidence(),
            decision_id="m5-fixture-decision",
            base_config=self.base_config,
        )
        self.assertEqual(
            result.status,
            IterationStatus.DECIDED,
            result.to_dict(),
        )
        self.assertEqual(result.evaluation.decision_record.decision, Decision.KEEP)
        self.assertTrue(result.synthetic)
        self.assertEqual(len(result.evidence), len(self.campaign.seeds))
        self.assertTrue(all(item.metrics["success_rate"] == 0.5 for item in result.evidence))
        self.assertEqual(git(self.repository, "rev-parse", "HEAD"), self.base_commit)


if __name__ == "__main__":
    unittest.main()
