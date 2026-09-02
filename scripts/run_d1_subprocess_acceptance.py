#!/usr/bin/env python3
"""Run D1 coordinator acceptance against real local no-GPU subprocesses."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import load_d1_config  # noqa: E402
from supervisor.attempts import ProposalSessionResult  # noqa: E402
from supervisor.c1_acceptance import repository_snapshot  # noqa: E402
from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.contracts import CampaignSpec, Decision, TrialEvidence  # noqa: E402
from supervisor.coordinator import IterationStatus, OfflineCampaignCoordinator  # noqa: E402
from supervisor.d1_backend import (  # noqa: E402
    BackendStatus,
    D1CoordinatorContractFactory,
    D1PlanBuilder,
    D1ProcessWorker,
    ExecutionMode,
    M5Authorization,
)
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer  # noqa: E402
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator  # noqa: E402
from supervisor.git_manager import GitExperimentManager, HarnessCheck  # noqa: E402
from supervisor.proposals import Proposal  # noqa: E402


SCENARIOS = (
    "happy",
    "timeout",
    "missing-artifact",
    "hash-mismatch",
    "cost-overrun",
    "failure-normalization",
)
TARGET_PATH = "candidates/config_override.json"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def initialize_repository(path: Path) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("D1 isolated acceptance fixture\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(
        path,
        "-c", "user.name=D1 Acceptance",
        "-c", "user.email=d1-acceptance@invalid.local",
        "commit", "-q", "-m", "Create isolated D1 fixture baseline",
    )
    return git(path, "rev-parse", "HEAD")


def campaign_for(scenario: str, baseline: str) -> CampaignSpec:
    return CampaignSpec.from_dict(
        {
            "schema_version": 1,
            "campaign_id": f"d1-{scenario}-acceptance",
            "research_question": (
                f"D1 fixture only: does the coordinator contain {scenario} correctly?"
            ),
            "baseline_commit": baseline,
            "rlinf_commit": RLINF_COMMIT,
            "edit_mode": "config_only",
            "editable_paths": [TARGET_PATH],
            "allowed_parameters": {
                "scientific_values.online_bc_weight": {
                    "kind": "number",
                    "minimum": "1",
                    "maximum": "3.5",
                }
            },
            "seeds": [2026],
            "reset_set_hash": fingerprint(
                {"fixture": "d1-local-subprocess", "scenario": scenario}
            ),
            "evaluator_version": "d1-local-acceptance-v1",
            "training_budget_steps": 100,
            "evaluation_trajectories": 256,
            "max_concurrency": 1,
            "artifact_namespace": f"enpire-d1-{scenario}-acceptance",
            "created_at": "2026-09-02T00:00:00Z",
            "budget": {
                "max_trials": 1,
                "max_wall_time_seconds": 30,
                "max_gpu_cost_usd": "0.3",
                "max_llm_cost_usd": "0",
            },
        }
    )


def proposal_for(scenario: str, campaign: CampaignSpec, baseline: str) -> Proposal:
    wall_time = 1 if scenario == "timeout" else 30
    return Proposal.from_dict(
        {
            "schema_version": 1,
            "proposal_id": f"d1-{scenario}-config-01",
            "campaign_id": campaign.campaign_id,
            "arm_id": "fixture-config",
            "base_commit": baseline,
            "edit_mode": "config_only",
            "hypothesis": (
                f"Acceptance fixture: the {scenario} subprocess outcome obeys authority."
            ),
            "evidence_ids": ["d0-dry-acceptance"],
            "expected_effect": "No scientific claim; exercise the D1 coordinator boundary.",
            "falsification_condition": "Observed coordinator behavior differs from the gate.",
            "rollback_condition": "Retain evidence and do not advance the incumbent.",
            "changed_paths": [TARGET_PATH],
            "requested_tests": ["config-contract", "dry-run"],
            "estimated_budget": {
                "wall_time_seconds": wall_time,
                "gpu_cost_usd": "0.3",
                "llm_cost_usd": "0",
            },
            "config_overrides": {"scientific_values.online_bc_weight": 2.25},
        }
    )


def control_evidence(campaign: CampaignSpec, baseline: str) -> list[TrialEvidence]:
    return [
        TrialEvidence.from_dict(
            {
                "schema_version": 1,
                "campaign_id": campaign.campaign_id,
                "trial_id": "d1-control.s2026",
                "arm_id": "control",
                "parent_commit": baseline,
                "candidate_commit": baseline,
                "rlinf_commit": campaign.rlinf_commit,
                "config_hash": "a" * 64,
                "command_hash": "b" * 64,
                "seed": 2026,
                "reset_set_hash": campaign.reset_set_hash,
                "evaluator_version": campaign.evaluator_version,
                "started_at": "2026-09-02T00:00:00Z",
                "finished_at": "2026-09-02T00:00:01Z",
                "status": "complete",
                "exit_code": 0,
                "elapsed_seconds": 1,
                "gpu_cost_usd": "0",
                "llm_cost_usd": "0",
                "metrics": {
                    "success_rate": 0.4,
                    "successful_episode_length": 45,
                },
                "metric_errors": [],
                "artifacts": [],
            }
        )
    ]


def run_scenario(root: Path, scenario: str) -> dict:
    scenario_root = root / scenario
    repository = scenario_root / "stable"
    baseline = initialize_repository(repository)
    campaign = campaign_for(scenario, baseline)
    proposal = proposal_for(scenario, campaign, baseline)
    session = ProposalSessionResult(
        proposal_slot_id=f"d1-{scenario}-fixture-slot",
        accepted=True,
        proposal=proposal,
        attempts=(),
        total_cost_usd="0",
    )
    python = Path(sys.executable).resolve()
    checker = ROOT / "scripts/check_d0_candidate_config.py"
    checks = {
        name: HarnessCheck.create(
            check_id=name,
            argv=(
                str(python),
                str(checker),
                TARGET_PATH,
                *(("--dry-resolve",) if name == "dry-run" else ()),
            ),
            timeout_seconds=30,
        )
        for name in ("config-contract", "dry-run")
    }
    manager = GitExperimentManager(
        repository=repository,
        worktree_root=scenario_root / "worktrees",
        enforcer=ProposalEnforcer(
            EnforcementPolicy.create(trusted_test_ids=list(checks))
        ),
        trusted_checks=checks,
    )
    authorization = M5Authorization.create(
        campaign=campaign,
        mode=ExecutionMode.FIXTURE,
        authorized_at=datetime.now(timezone.utc),
        allow_fixture_execution=True,
    )
    worker = D1ProcessWorker(worker_id=f"d1-{scenario}-worker")
    factory = D1CoordinatorContractFactory(
        builder=D1PlanBuilder(
            results_root=scenario_root / "worker-results",
            python_executable=python,
            fixture_launcher=ROOT / "scripts/d1_adversarial_fixture_launcher.py",
        ),
        worker=worker,
        authorization=authorization,
    )
    incumbents = ArmIncumbentStore(
        scenario_root / "state/incumbents.json",
        campaign_id=campaign.campaign_id,
        initial_incumbents={proposal.arm_id: baseline},
    )
    base_config = load_d1_config(ROOT / "configs/d1/control.yaml")
    base_config["fixture_success_rate"] = 0.5
    base_config["fixture_episode_length"] = 40
    result = OfflineCampaignCoordinator(
        campaign=campaign,
        git_manager=manager,
        worker=worker,
        evaluator=OfflineD1Evaluator(),
        incumbents=incumbents,
        ledger_root=scenario_root / "ledgers",
        run_contract_factory=factory,
        synthetic=True,
    ).run(
        iteration_id=f"d1-{scenario}-iteration",
        proposal_session=session,
        control_evidence=control_evidence(campaign, baseline),
        decision_id=f"d1-{scenario}-decision",
        base_config=base_config,
    )
    trial_id = f"{proposal.proposal_id}.s2026"
    backend = worker.fetch_result(trial_id)
    expected_backend = {
        "happy": BackendStatus.COMPLETE,
        "timeout": BackendStatus.TIMED_OUT,
        "missing-artifact": BackendStatus.FAILED,
        "hash-mismatch": BackendStatus.INVALID_EVIDENCE,
        "cost-overrun": BackendStatus.INVALID_EVIDENCE,
        "failure-normalization": BackendStatus.FAILED,
    }[scenario]
    if scenario == "happy":
        passed = (
            result.status == IterationStatus.DECIDED
            and result.evaluation is not None
            and result.evaluation.decision_record.decision == Decision.KEEP
            and result.incumbent_after == result.preparation.candidate_commit
            and len(result.evidence) == 1
        )
    elif scenario == "failure-normalization":
        passed = (
            result.status == IterationStatus.DECIDED
            and result.evaluation is not None
            and result.evaluation.decision_record.decision == Decision.FAILED
            and result.incumbent_after == baseline
            and len(result.evidence) == 1
        )
    else:
        passed = (
            result.status == IterationStatus.WORKER_FAILED
            and result.evaluation is None
            and result.incumbent_after == baseline
            and not result.evidence
        )
    passed = passed and backend.status == expected_backend
    return {
        "scenario": scenario,
        "status": "passed" if passed else "blocked",
        "baseline_commit": baseline,
        "candidate_commit": (
            result.preparation.candidate_commit if result.preparation else None
        ),
        "campaign_hash": campaign.fingerprint(),
        "proposal_hash": proposal.fingerprint(),
        "authorization_hash": authorization.fingerprint(),
        "backend": backend.to_dict(),
        "coordinator": result.to_dict(),
        "incumbent_advanced": result.incumbent_after != baseline,
        "evaluation_reached": result.evaluation is not None,
        "isolated_repository": str(repository),
    }


def run(output: Path, acceptance_root: Path) -> dict:
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    if acceptance_root.exists():
        raise SystemExit(f"acceptance root already exists: {acceptance_root}")
    acceptance_root.mkdir(parents=True)
    stable_before = repository_snapshot(ROOT)
    if not stable_before["clean"]:
        raise SystemExit("integration repository must be clean before D1 acceptance")
    scenarios = [run_scenario(acceptance_root, item) for item in SCENARIOS]
    stable_after = repository_snapshot(ROOT)
    passed = (
        stable_before == stable_after
        and all(item["status"] == "passed" for item in scenarios)
    )
    report = {
        "schema_version": 1,
        "status": "passed" if passed else "blocked",
        "claim_scope": "D1 local synthetic subprocess acceptance only",
        "stable_before": stable_before,
        "stable_after": stable_after,
        "stable_unchanged": stable_before == stable_after,
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "real_subprocess_adapter_used": True,
        "external_network_used": False,
        "gpu_used": False,
        "provider_call_made": False,
        "ssh_used": False,
        "wandb_contacted": False,
        "paid_service_used": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/provider-acceptance/d1/subprocess.json",
    )
    parser.add_argument(
        "--acceptance-root",
        type=Path,
        default=Path("/private/tmp/enpire-d1-subprocess-acceptance"),
    )
    arguments = parser.parse_args()
    report = run(arguments.output, arguments.acceptance_root)
    print(json.dumps({"status": report["status"], "output": str(arguments.output)}))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
