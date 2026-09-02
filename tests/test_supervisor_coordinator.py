from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supervisor.attempts import ProposalSessionResult
from supervisor.canonical import fingerprint
from supervisor.contracts import CampaignSpec, Decision, TrialEvidence, TrialState
from supervisor.coordinator import IterationStatus, OfflineCampaignCoordinator
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator
from supervisor.git_manager import GitExperimentManager, HarnessCheck
from supervisor.proposals import Proposal
from supervisor.reporting import SYNTHETIC_NOTICE, write_report_bundle
from supervisor.workers import (
    FakeExperimentWorker,
    RunContract,
    WorkerScenario,
    WorkerState,
)
from tests.test_supervisor_enforcement import base_config
from tests.test_supervisor_proposals import config_campaign_data, config_proposal_data


def run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class AcceptanceOnlyFactory:
    synthetic = False
    promotion_allowed = False

    def create(
        self,
        *,
        campaign,
        proposal,
        preparation,
        trial_id,
        seed,
        incumbent_commit,
        candidate_commit,
        default_config_hash,
        max_gpu_cost_usd,
    ):
        return RunContract.create(
            campaign_id=campaign.campaign_id,
            trial_id=trial_id,
            arm_id=proposal.arm_id,
            parent_commit=incumbent_commit,
            candidate_commit=candidate_commit,
            rlinf_commit=campaign.rlinf_commit,
            config_hash=default_config_hash,
            command_hash=fingerprint(
                {"mode": "paid-acceptance-test", "trial_id": trial_id}
            ),
            seed=seed,
            reset_set_hash=campaign.reset_set_hash,
            evaluator_version=campaign.evaluator_version,
            max_wall_time_seconds=proposal.estimated_budget.wall_time_seconds,
            max_gpu_cost_usd=max_gpu_cost_usd,
        )


class NoEvaluationAllowed:
    def evaluate(self, **kwargs):
        raise AssertionError("paid acceptance must never call the evaluator")


class CoordinatorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "stable"
        self.repository.mkdir()
        run_git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "candidates").mkdir()
        (self.repository / "candidates" / "actor_objective.py").write_text(
            "def objective(actor_loss, bc_loss, weight):\n"
            "    return actor_loss + weight * bc_loss\n",
            encoding="utf-8",
        )
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        run_git(self.repository, "add", ".")
        run_git(
            self.repository,
            "-c", "user.name=Fixture",
            "-c", "user.email=fixture@invalid.local",
            "commit", "-q", "-m", "fixture base",
        )
        self.base_commit = run_git(self.repository, "rev-parse", "HEAD")
        raw = config_campaign_data()
        raw["campaign_id"] = "m4-offline-campaign"
        raw["baseline_commit"] = self.base_commit
        self.campaign = CampaignSpec.from_dict(raw)
        proposal_raw = config_proposal_data()
        proposal_raw["campaign_id"] = self.campaign.campaign_id
        proposal_raw["base_commit"] = self.base_commit
        proposal_raw["proposal_id"] = "m4-proposal-01"
        self.proposal = Proposal.from_dict(proposal_raw)
        self.session = ProposalSessionResult(
            proposal_slot_id="offline-slot-1",
            accepted=True,
            proposal=self.proposal,
            attempts=(),
            total_cost_usd="0",
        )

    def manager(self) -> GitExperimentManager:
        (self.root / "worktrees").mkdir(exist_ok=True)
        checks = {
            name: HarnessCheck.create(
                check_id=name,
                argv=(sys.executable, "-c", "pass"),
                timeout_seconds=10,
            )
            for name in ("config-contract", "dry-run")
        }
        policy = EnforcementPolicy.create(trusted_test_ids=list(checks))
        return GitExperimentManager(
            repository=self.repository,
            worktree_root=self.root / "worktrees",
            enforcer=ProposalEnforcer(policy),
            trusted_checks=checks,
        )

    def scenario(self, success: float, *, state=WorkerState.COMPLETED):
        return WorkerScenario.create(
            terminal_state=state,
            started_at="2026-08-04T12:00:00Z",
            finished_at="2026-08-04T12:01:00Z",
            elapsed_seconds=60,
            metrics={"success_rate": success, "successful_episode_length": 40},
            exit_code=0 if state == WorkerState.COMPLETED else 9,
            gpu_cost_usd="0.1",
        )

    def worker(self, rates, *, lost_seed=None):
        scenarios = {}
        for seed, rate in zip(self.campaign.seeds, rates):
            state = WorkerState.LOST if seed == lost_seed else WorkerState.COMPLETED
            scenarios[f"{self.proposal.proposal_id}.s{seed}"] = self.scenario(
                rate, state=state
            )
        return FakeExperimentWorker(worker_id="offline-worker", scenarios=scenarios)

    def control_evidence(self, rates):
        records = []
        for seed, rate in zip(self.campaign.seeds, rates):
            records.append(
                TrialEvidence.from_dict(
                    {
                        "schema_version": 1,
                        "campaign_id": self.campaign.campaign_id,
                        "trial_id": f"control.s{seed}",
                        "arm_id": "control-arm",
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
                        "gpu_cost_usd": "0.1",
                        "llm_cost_usd": "0",
                        "metrics": {
                            "success_rate": rate,
                            "successful_episode_length": 45,
                        },
                        "metric_errors": [],
                        "artifacts": [],
                    }
                )
            )
        return records

    def coordinator(self, worker):
        store = ArmIncumbentStore(
            self.root / "state" / "incumbents.json",
            campaign_id=self.campaign.campaign_id,
            initial_incumbents={
                self.proposal.arm_id: self.base_commit,
                "code-arm": self.base_commit,
            },
        )
        coordinator = OfflineCampaignCoordinator(
            campaign=self.campaign,
            git_manager=self.manager(),
            worker=worker,
            evaluator=OfflineD1Evaluator(),
            incumbents=store,
            ledger_root=self.root / "ledgers",
        )
        return coordinator, store

    def run_iteration(self, rates, *, lost_seed=None):
        coordinator, store = self.coordinator(
            self.worker(rates, lost_seed=lost_seed)
        )
        result = coordinator.run(
            iteration_id="iteration-01",
            proposal_session=self.session,
            control_evidence=self.control_evidence([0.4, 0.4, 0.4]),
            decision_id="decision-01",
            base_config=base_config(),
        )
        return result, store

    def test_keep_updates_only_arm_pointer_and_never_stable_branch(self) -> None:
        result, store = self.run_iteration([0.5, 0.5, 0.5])
        self.assertEqual(result.status, IterationStatus.DECIDED)
        self.assertEqual(result.evaluation.decision_record.decision, Decision.KEEP)
        self.assertNotEqual(result.incumbent_after, self.base_commit)
        self.assertEqual(store.snapshot()["code-arm"], self.base_commit)
        self.assertEqual(run_git(self.repository, "rev-parse", "HEAD"), self.base_commit)
        self.assertTrue(
            all(anchor.state == TrialState.KEPT.value for anchor in result.ledger_anchors)
        )

    def test_revert_preserves_pointer_but_retains_negative_evidence(self) -> None:
        result, store = self.run_iteration([0.3, 0.3, 0.3])
        self.assertEqual(result.evaluation.decision_record.decision, Decision.REVERT)
        self.assertEqual(result.incumbent_after, self.base_commit)
        self.assertEqual(len(result.evidence), 3)
        self.assertTrue(
            all(
                anchor.state == TrialState.REVERTED.value
                for anchor in result.ledger_anchors
            )
        )
        self.assertEqual(store.snapshot()[self.proposal.arm_id], self.base_commit)

    def test_worker_loss_fails_campaign_set_without_a_decision(self) -> None:
        result, store = self.run_iteration(
            [0.5, 0.5, 0.5], lost_seed=self.campaign.seeds[1]
        )
        self.assertEqual(result.status, IterationStatus.WORKER_FAILED)
        self.assertIsNone(result.evaluation)
        self.assertEqual(result.incumbent_after, self.base_commit)
        self.assertEqual(store.snapshot()[self.proposal.arm_id], self.base_commit)
        self.assertTrue(
            all(anchor.state == TrialState.FAILED.value for anchor in result.ledger_anchors)
        )

    def test_paid_acceptance_records_evidence_without_evaluation_or_promotion(self) -> None:
        worker = self.worker([0.5, 0.5, 0.5])
        store = ArmIncumbentStore(
            self.root / "acceptance-state" / "incumbents.json",
            campaign_id=self.campaign.campaign_id,
            initial_incumbents={
                self.proposal.arm_id: self.base_commit,
                "code-arm": self.base_commit,
            },
        )
        result = OfflineCampaignCoordinator(
            campaign=self.campaign,
            git_manager=self.manager(),
            worker=worker,
            evaluator=NoEvaluationAllowed(),
            incumbents=store,
            ledger_root=self.root / "acceptance-ledgers",
            run_contract_factory=AcceptanceOnlyFactory(),
            synthetic=False,
            evaluation_enabled=False,
        ).run(
            iteration_id="paid-acceptance-iteration",
            proposal_session=self.session,
            control_evidence=(),
            decision_id="must-not-be-used",
            base_config=base_config(),
        )
        self.assertEqual(result.status, IterationStatus.ACCEPTANCE_RECORDED)
        self.assertIsNone(result.evaluation)
        self.assertEqual(result.incumbent_before, result.incumbent_after)
        self.assertEqual(store.snapshot()[self.proposal.arm_id], self.base_commit)
        self.assertEqual(len(result.evidence), len(self.campaign.seeds))
        self.assertTrue(
            all(anchor.state == TrialState.RECORDED.value for anchor in result.ledger_anchors)
        )

    def test_report_bundle_contains_machine_and_human_readable_provenance(self) -> None:
        result, store = self.run_iteration([0.5, 0.5, 0.5])
        bundle = write_report_bundle(
            self.root / "report",
            campaign=self.campaign,
            proposal_sessions=[self.session],
            iterations=[result],
            incumbent_snapshot=store.snapshot(),
        )
        self.assertEqual(
            {item.name for item in bundle.artifacts},
            {"report.html", "report.json", "report.md", "trials.csv"},
        )
        payload = json.loads((self.root / "report" / "report.json").read_text())
        self.assertEqual(payload["notice"], SYNTHETIC_NOTICE)
        self.assertEqual(payload["totals"]["trials_with_evidence"], 3)
        self.assertIn("evidence_hash", (self.root / "report" / "trials.csv").read_text())
        self.assertIn(SYNTHETIC_NOTICE, (self.root / "report" / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()
