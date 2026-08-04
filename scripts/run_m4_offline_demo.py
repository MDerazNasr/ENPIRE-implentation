#!/usr/bin/env python3
"""Run the complete M4 supervisor using deterministic synthetic fixtures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from supervisor.attempts import ProposalAttemptController
from supervisor.canonical import fingerprint
from supervisor.context import build_context
from supervisor.contracts import CampaignSpec, TrialEvidence
from supervisor.coordinator import OfflineCampaignCoordinator
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator
from supervisor.git_manager import GitExperimentManager, HarnessCheck
from supervisor.providers import FakeProposalProvider, ProviderCallResult
from supervisor.reporting import SYNTHETIC_NOTICE, write_report_bundle
from supervisor.workers import FakeExperimentWorker, WorkerScenario, WorkerState


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def base_config() -> dict:
    return {
        "actor": {"optim": {"lr": 0.0001}},
        "algorithm": {"actor": {"update_epoch": 4}, "schedule": "upstream"},
    }


def campaign_payload(base_commit: str) -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "m4-offline-demo",
        "research_question": "Can a bounded synthetic candidate pass the D1 rule?",
        "baseline_commit": base_commit,
        "rlinf_commit": "c90951a0c799a750cb5294ed10587c61cc2af8bf",
        "edit_mode": "config_only",
        "editable_paths": ["candidates/config_override.json"],
        "allowed_parameters": {
            "actor.optim.lr": {
                "kind": "number", "minimum": "0.000001", "maximum": "0.001"
            }
        },
        "seeds": [2026, 2027, 2028],
        "reset_set_hash": "a" * 64,
        "evaluator_version": "d1-rule-v1",
        "training_budget_steps": 250,
        "evaluation_trajectories": 256,
        "max_concurrency": 2,
        "artifact_namespace": "qualia-rlt-m4-offline",
        "created_at": "2026-08-04T12:00:00Z",
        "budget": {
            "max_trials": 3,
            "max_wall_time_seconds": 10800,
            "max_gpu_cost_usd": "12.5",
            "max_llm_cost_usd": "3",
        },
    }


def proposal_payload(campaign: CampaignSpec, *, learning_rate: float) -> dict:
    return {
        "schema_version": 1,
        "proposal_id": "m4-demo-proposal",
        "campaign_id": campaign.campaign_id,
        "arm_id": "config-arm",
        "base_commit": campaign.baseline_commit,
        "edit_mode": "config_only",
        "hypothesis": "Lower actor learning rate improves the synthetic fixture.",
        "evidence_ids": ["control-fixture"],
        "expected_effect": "Higher fixed-reset success.",
        "falsification_condition": "The frozen D1 rule does not keep it.",
        "rollback_condition": "Retain the incumbent for every non-keep decision.",
        "changed_paths": ["candidates/config_override.json"],
        "requested_tests": ["config-contract", "dry-run"],
        "estimated_budget": {
            "wall_time_seconds": 1800,
            "gpu_cost_usd": "2.5",
            "llm_cost_usd": "0.2",
        },
        "config_overrides": {"actor.optim.lr": learning_rate},
    }


def provider_result(payload: dict, *, suffix: str) -> ProviderCallResult:
    return ProviderCallResult(
        provider="fake-provider",
        model="offline-fixture-model",
        started_at=f"2026-08-04T12:00:0{suffix}Z",
        completed_at=f"2026-08-04T12:00:0{int(suffix) + 1}Z",
        response_hash=fingerprint(payload),
        proposal_payload=payload,
        reported_cost_usd="0.01",
        input_tokens=100,
        output_tokens=50,
    )


def control_evidence(campaign: CampaignSpec) -> list[TrialEvidence]:
    records = []
    for seed in campaign.seeds:
        records.append(
            TrialEvidence.from_dict(
                {
                    "schema_version": 1,
                    "campaign_id": campaign.campaign_id,
                    "trial_id": f"control.s{seed}",
                    "arm_id": "control-arm",
                    "parent_commit": campaign.baseline_commit,
                    "candidate_commit": campaign.baseline_commit,
                    "rlinf_commit": campaign.rlinf_commit,
                    "config_hash": "b" * 64,
                    "command_hash": "c" * 64,
                    "seed": seed,
                    "reset_set_hash": campaign.reset_set_hash,
                    "evaluator_version": campaign.evaluator_version,
                    "started_at": "2026-08-04T11:00:00Z",
                    "finished_at": "2026-08-04T11:01:00Z",
                    "status": "complete", "exit_code": 0, "elapsed_seconds": 60,
                    "gpu_cost_usd": "0.1", "llm_cost_usd": "0",
                    "metrics": {
                        "success_rate": 0.4,
                        "successful_episode_length": 45,
                    },
                    "metric_errors": [], "artifacts": [],
                }
            )
        )
    return records


def initialize_repository(root: Path) -> tuple[Path, str]:
    repository = root / "stable"
    repository.mkdir(parents=True)
    git(repository, "init", "-q", "-b", "main")
    (repository / "candidates").mkdir()
    (repository / "candidates" / "actor_objective.py").write_text(
        "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
        "    return actor_loss + bc_weight * bc_loss\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text("M4 synthetic fixture\n", encoding="utf-8")
    git(repository, "add", ".")
    git(
        repository, "-c", "user.name=M4 Demo", "-c",
        "user.email=m4-demo@invalid.local", "commit", "-q", "-m", "fixture base"
    )
    return repository, git(repository, "rev-parse", "HEAD")


def run(output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    repository, base_commit = initialize_repository(output / "runtime")
    campaign = CampaignSpec.from_dict(campaign_payload(base_commit))
    context = build_context(
        campaign,
        incumbent_commit=base_commit,
        immutable_boundaries=[
            "The base VLA, canonical RLinf, evaluator, and simulator are immutable.",
            "Only the allowlisted actor configuration may change.",
        ],
        metric_definitions={
            "success_rate": "Frozen primary endpoint over approved resets.",
            "successful_episode_length": "Ceiling-case efficiency endpoint.",
        },
        baseline_summary="Synthetic control rates are fixed at 0.4 for three seeds.",
    )
    invalid = proposal_payload(campaign, learning_rate=1.0)
    valid = proposal_payload(campaign, learning_rate=0.00005)
    provider = FakeProposalProvider(
        [provider_result(invalid, suffix="0"), provider_result(valid, suffix="2")]
    )
    session = ProposalAttemptController(
        campaign=campaign,
        context=context,
        incumbent_commit=base_commit,
        provider=provider,
        model="offline-fixture-model",
        proposal_slot_id="m4-demo-slot",
        max_total_cost_usd="1",
    ).run()
    if not session.accepted or session.proposal is None:
        raise RuntimeError("offline provider fixture did not yield an accepted proposal")
    scenarios = {
        f"{session.proposal.proposal_id}.s{seed}": WorkerScenario.create(
            terminal_state=WorkerState.COMPLETED,
            started_at="2026-08-04T12:10:00Z",
            finished_at="2026-08-04T12:11:00Z",
            elapsed_seconds=60,
            metrics={"success_rate": 0.5, "successful_episode_length": 40},
            exit_code=0,
            gpu_cost_usd="0.1",
        )
        for seed in campaign.seeds
    }
    worktrees = output / "runtime" / "worktrees"
    worktrees.mkdir()
    checks = {
        name: HarnessCheck.create(
            check_id=name,
            argv=(sys.executable, "-c", "pass"),
            timeout_seconds=10,
        )
        for name in ("config-contract", "dry-run")
    }
    manager = GitExperimentManager(
        repository=repository,
        worktree_root=worktrees,
        enforcer=ProposalEnforcer(
            EnforcementPolicy.create(trusted_test_ids=list(checks))
        ),
        trusted_checks=checks,
    )
    store = ArmIncumbentStore(
        output / "runtime" / "state" / "incumbents.json",
        campaign_id=campaign.campaign_id,
        initial_incumbents={"config-arm": base_commit, "code-arm": base_commit},
    )
    coordinator = OfflineCampaignCoordinator(
        campaign=campaign,
        git_manager=manager,
        worker=FakeExperimentWorker(worker_id="m4-fake-worker", scenarios=scenarios),
        evaluator=OfflineD1Evaluator(),
        incumbents=store,
        ledger_root=output / "runtime" / "ledgers",
    )
    result = coordinator.run(
        iteration_id="m4-demo-iteration",
        proposal_session=session,
        control_evidence=control_evidence(campaign),
        decision_id="m4-demo-decision",
        base_config=base_config(),
    )
    bundle = write_report_bundle(
        output / "report",
        campaign=campaign,
        proposal_sessions=[session],
        iterations=[result],
        incumbent_snapshot=store.snapshot(),
    )
    return {
        "notice": SYNTHETIC_NOTICE,
        "status": result.status.value,
        "decision": result.evaluation.decision_record.decision.value,
        "invalid_attempts_before_acceptance": sum(
            item.status.value == "invalid" for item in session.attempts
        ),
        "stable_head_unchanged": git(repository, "rev-parse", "HEAD") == base_commit,
        "report": bundle.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/enpire-m4-offline-demo")
    )
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
