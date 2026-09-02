from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent.d1_config import load_d1_config
from supervisor.attempts import ProposalSessionResult
from supervisor.contracts import CampaignSpec, Decision, TrialEvidence
from supervisor.coordinator import IterationStatus, OfflineCampaignCoordinator
from supervisor.d1_backend import (
    D1BackendError,
    D1CoordinatorContractFactory,
    D1PlanBuilder,
    D1ProcessWorker,
    ExecutionMode,
    M5Authorization,
    normalize_d1_evidence,
)
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator
from supervisor.git_manager import GitExperimentManager, HarnessCheck
from supervisor.proposals import Proposal
from tests.test_d1_integration_gate import pack_data


ROOT = Path(__file__).resolve().parents[1]
OBJECTIVE_PATH = "supervisor/objectives/actor_objective.py"
CONFIG_PATH = "configs/d1/control.json"
DEFAULT_OBJECTIVE = (
    '"""Default objective fixture."""\n'
    "\n"
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss\n"
)
CHANGED_OBJECTIVE = (
    '"""Default objective fixture."""\n'
    "\n"
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss + 0.1 * bc_loss\n"
)


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
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@invalid.local",
        "commit",
        "-q",
        "-m",
        message,
    )
    return git(repository, "rev-parse", "HEAD")


class M6CodeBackendIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "stable"
        (self.repository / "supervisor" / "objectives").mkdir(parents=True)
        (self.repository / "configs" / "d1").mkdir(parents=True)
        git(self.repository, "init", "-q", "-b", "main")
        (self.repository / OBJECTIVE_PATH).write_text(
            DEFAULT_OBJECTIVE, encoding="utf-8"
        )
        config = load_d1_config(ROOT / "configs" / "d1" / "control.yaml")
        config["fixture_success_rate"] = 0.4
        config["fixture_code_success_rate"] = 0.55
        config["fixture_episode_length"] = 38
        (self.repository / CONFIG_PATH).write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        self.base_commit = commit(self.repository, "M6 stable fixture")
        campaign_raw = pack_data(
            incumbent=self.base_commit,
            candidate=self.base_commit,
            known_good=self.base_commit,
        )["campaign"]
        campaign_raw.update(
            {
                "campaign_id": "m6-code-fixture",
                "baseline_commit": self.base_commit,
                "edit_mode": "actor_objective_code",
                "editable_paths": [OBJECTIVE_PATH],
                "allowed_parameters": {},
            }
        )
        self.campaign = CampaignSpec.from_dict(campaign_raw)
        self.proposal = Proposal.from_dict(
            {
                "schema_version": 1,
                "proposal_id": "m6-objective-candidate",
                "campaign_id": self.campaign.campaign_id,
                "arm_id": "claude-code",
                "base_commit": self.base_commit,
                "edit_mode": "actor_objective_code",
                "hypothesis": "A small additional BC term improves synthetic success.",
                "evidence_ids": ["control-b"],
                "expected_effect": "Change actor-objective values and gradients.",
                "falsification_condition": "Objective behavior is unchanged or invalid.",
                "rollback_condition": "Revert unless the frozen evaluator keeps it.",
                "changed_paths": [OBJECTIVE_PATH],
                "requested_tests": ["config-contract", "dry-run"],
                "estimated_budget": {
                    "wall_time_seconds": 30,
                    "gpu_cost_usd": "0.3",
                    "llm_cost_usd": "0",
                },
                "unified_diff": self._diff(DEFAULT_OBJECTIVE, CHANGED_OBJECTIVE),
            }
        )
        self.session = ProposalSessionResult(
            proposal_slot_id="m6-code-slot",
            accepted=True,
            proposal=self.proposal,
            attempts=(),
            total_cost_usd="0",
        )

    @staticmethod
    def _diff(before: str, after: str) -> str:
        before_lines = before.splitlines()
        after_lines = after.splitlines()
        return (
            f"diff --git a/{OBJECTIVE_PATH} b/{OBJECTIVE_PATH}\n"
            f"--- a/{OBJECTIVE_PATH}\n"
            f"+++ b/{OBJECTIVE_PATH}\n"
            f"@@ -1,{len(before_lines)} +1,{len(after_lines)} @@\n"
            + "\n".join(f"-{line}" for line in before_lines)
            + "\n"
            + "\n".join(f"+{line}" for line in after_lines)
            + "\n"
        )

    def manager(self) -> GitExperimentManager:
        worktrees = self.root / "worktrees"
        worktrees.mkdir(exist_ok=True)
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
            worktree_root=worktrees,
            enforcer=ProposalEnforcer(
                EnforcementPolicy.create(trusted_test_ids=list(checks))
            ),
            trusted_checks=checks,
            objective_check=HarnessCheck.create(
                check_id="m6-objective-contract",
                argv=(
                    sys.executable,
                    str(ROOT / "scripts" / "validate_m6_objective.py"),
                    "--plugin",
                    OBJECTIVE_PATH,
                    "--require-behavior-change",
                ),
                timeout_seconds=10,
            ),
        )

    def control_evidence(self) -> list[TrialEvidence]:
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

    def test_code_candidate_runs_three_subprocesses_with_bound_objective(self) -> None:
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.FIXTURE,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
            allow_fixture_execution=True,
        )
        worker = D1ProcessWorker(worker_id="m6-code-worker")
        factory = D1CoordinatorContractFactory(
            builder=D1PlanBuilder(
                results_root=self.root / "results",
                python_executable=Path(sys.executable),
                fixture_launcher=ROOT / "scripts" / "m5_fixture_launcher.py",
            ),
            worker=worker,
            authorization=authorization,
            code_base_config_relative_path=CONFIG_PATH,
        )
        store = ArmIncumbentStore(
            self.root / "state" / "incumbents.json",
            campaign_id=self.campaign.campaign_id,
            initial_incumbents={self.proposal.arm_id: self.base_commit},
        )
        result = OfflineCampaignCoordinator(
            campaign=self.campaign,
            git_manager=self.manager(),
            worker=worker,
            evaluator=OfflineD1Evaluator(),
            incumbents=store,
            ledger_root=self.root / "ledgers",
            run_contract_factory=factory,
            synthetic=True,
        ).run(
            iteration_id="m6-code-iteration",
            proposal_session=self.session,
            control_evidence=self.control_evidence(),
            decision_id="m6-code-decision",
        )
        self.assertEqual(result.status, IterationStatus.DECIDED, result.to_dict())
        self.assertEqual(result.evaluation.decision_record.decision, Decision.KEEP)
        self.assertEqual(len(result.evidence), len(self.campaign.seeds))
        objective_hash = hashlib.sha256(CHANGED_OBJECTIVE.encode()).hexdigest()
        self.assertTrue(
            all(
                any(
                    item.kind == "actor-objective" and item.sha256 == objective_hash
                    for item in evidence.artifacts
                )
                for evidence in result.evidence
            )
        )
        self.assertTrue(
            all(evidence.metrics["success_rate"] == 0.55 for evidence in result.evidence)
        )
        self.assertEqual(git(self.repository, "rev-parse", "HEAD"), self.base_commit)

    def test_live_objective_attachment_is_explicitly_deferred(self) -> None:
        preparation = self.manager().prepare(
            self.proposal,
            self.campaign,
            incumbent_commit=self.base_commit,
        )
        self.assertEqual(preparation.status.value, "ready", preparation.to_dict())
        builder = D1PlanBuilder(
            results_root=self.root / "dry-results",
            python_executable=Path(sys.executable),
            environment={
                "RLINF_HOME": "/opt/rlinf",
                "STAGE1_CHECKPOINT": "/opt/checkpoints/stage1",
                "NORM_STATS_PATH": "/opt/checkpoints/norm.json",
                "WANDB_PROJECT": "m6-tests",
                "D1_SEED": "2026",
            },
        )
        with self.assertRaisesRegex(D1BackendError, "compatibility handoff"):
            builder.build(
                campaign=self.campaign,
                workspace=Path(preparation.worktree_path),
                source_config_relative_path=CONFIG_PATH,
                objective_relative_path=OBJECTIVE_PATH,
                trial_id="m6-live-deferred",
                arm_id=self.proposal.arm_id,
                parent_commit=self.base_commit,
                candidate_commit=preparation.candidate_commit,
                seed=2026,
                max_wall_time_seconds=30,
                max_gpu_cost_usd="0.1",
                mode=ExecutionMode.DRY_RUN,
            )

    def test_objective_manifest_tampering_is_rejected(self) -> None:
        preparation = self.manager().prepare(
            self.proposal,
            self.campaign,
            incumbent_commit=self.base_commit,
        )
        builder = D1PlanBuilder(
            results_root=self.root / "tamper-results",
            python_executable=Path(sys.executable),
            fixture_launcher=ROOT / "scripts" / "m5_fixture_launcher.py",
        )
        plan = builder.build(
            campaign=self.campaign,
            workspace=Path(preparation.worktree_path),
            source_config_relative_path=CONFIG_PATH,
            objective_relative_path=OBJECTIVE_PATH,
            trial_id="m6-tampered-objective",
            arm_id=self.proposal.arm_id,
            parent_commit=self.base_commit,
            candidate_commit=preparation.candidate_commit,
            seed=2026,
            max_wall_time_seconds=30,
            max_gpu_cost_usd="0.1",
            mode=ExecutionMode.FIXTURE,
        )
        authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.FIXTURE,
            authorized_at=datetime(2026, 8, 4, 12, tzinfo=timezone.utc),
            allow_fixture_execution=True,
        )
        worker = D1ProcessWorker(worker_id="m6-tamper-worker")
        worker.register(plan, authorization)
        worker.prepare(plan.contract)
        worker.launch(plan.contract.trial_id)
        manifest_path = Path(plan.manifest_path)
        manifest = json.loads(manifest_path.read_text())
        manifest["objective_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(D1BackendError, "objective hash"):
            normalize_d1_evidence(plan, require_wandb=False)


if __name__ == "__main__":
    unittest.main()
