#!/usr/bin/env python3
"""Run D0 proposal-to-D1 planning without launching an external process."""

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
from supervisor.attempts import ProposalAttemptController  # noqa: E402
from supervisor.c1_acceptance import repository_snapshot  # noqa: E402
from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.context import build_context  # noqa: E402
from supervisor.contracts import CampaignSpec  # noqa: E402
from supervisor.d1_backend import (  # noqa: E402
    BackendStatus,
    D1ExperimentBackend,
    D1PlanBuilder,
    ExecutionMode,
    M5Authorization,
)
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer  # noqa: E402
from supervisor.git_manager import (  # noqa: E402
    GitExperimentManager,
    HarnessCheck,
    PreparationStatus,
)
from supervisor.proposals import Proposal  # noqa: E402
from supervisor.providers import (  # noqa: E402
    FakeProposalProvider,
    ProviderCallResult,
)


CAMPAIGN_ID = "d0-config-dry-acceptance"
PROPOSAL_ID = "d0-fixture-config-01"
TARGET_PATH = "candidates/config_override.json"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"


class NoCallTransport:
    def run(self, argv, *, cwd, timeout_seconds):
        raise AssertionError("D0 dry-run must not launch the D1 process")


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _branch_refs() -> dict[str, str]:
    output = _git(
        "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"
    )
    return dict(line.split(" ", 1) for line in output.splitlines() if line)


def _campaign(base_commit: str) -> CampaignSpec:
    return CampaignSpec.from_dict(
        {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "research_question": (
                "D0 fixture only: can one bounded BC configuration proposal "
                "materialize and dry-resolve through the D1 adapter?"
            ),
            "baseline_commit": base_commit,
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
                {"status": "d0-fixture-only", "execution_authorized": False}
            ),
            "evaluator_version": "d0-no-execution-v1",
            "training_budget_steps": 100,
            "evaluation_trajectories": 256,
            "max_concurrency": 1,
            "artifact_namespace": "enpire-d0-dry-acceptance",
            "created_at": "2026-09-02T00:00:00Z",
            "budget": {
                "max_trials": 1,
                "max_wall_time_seconds": 3600,
                "max_gpu_cost_usd": "15",
                "max_llm_cost_usd": "0.5",
            },
        }
    )


def _proposal(campaign: CampaignSpec, base_commit: str) -> Proposal:
    return Proposal.from_dict(
        {
            "schema_version": 1,
            "proposal_id": PROPOSAL_ID,
            "campaign_id": campaign.campaign_id,
            "arm_id": "fixture-config",
            "base_commit": base_commit,
            "edit_mode": "config_only",
            "hypothesis": (
                "Fixture hypothesis: an intermediate online BC weight can pass "
                "the bounded proposal-to-plan path."
            ),
            "evidence_ids": ["c1-safe-failure", "d1-one-seed-inconclusive"],
            "expected_effect": "No performance claim; D0 expects a valid dry plan.",
            "falsification_condition": (
                "Any scope, config, Git, hash, or dry-run check fails."
            ),
            "rollback_condition": (
                "Discard the fixture branch if the D0 gate does not pass."
            ),
            "changed_paths": [TARGET_PATH],
            "requested_tests": ["config-contract", "dry-run"],
            "estimated_budget": {
                "wall_time_seconds": 1800,
                "gpu_cost_usd": "15",
                "llm_cost_usd": "0",
            },
            "config_overrides": {"scientific_values.online_bc_weight": 2.25},
        }
    )


def run(output: Path, worktree_root: Path, worker_results: Path) -> dict:
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    if worktree_root.exists() and any(worktree_root.iterdir()):
        raise SystemExit(f"worktree root must be empty: {worktree_root}")
    if worker_results.exists() and any(worker_results.iterdir()):
        raise SystemExit(f"worker results must be empty: {worker_results}")
    worktree_root.mkdir(parents=True, exist_ok=True)
    worker_results.mkdir(parents=True, exist_ok=True)

    stable_before = repository_snapshot(ROOT)
    if not stable_before["clean"]:
        raise SystemExit("stable repository must be clean before D0")
    refs_before = _branch_refs()
    base_commit = stable_before["head"]
    campaign = _campaign(base_commit)
    proposal = _proposal(campaign, base_commit)
    context = build_context(
        campaign,
        incumbent_commit=base_commit,
        immutable_boundaries=[
            "D0 uses a deterministic fixture, not a Claude-generated proposal.",
            "No process, GPU, SSH, W&B, provider, or paid execution is authorized.",
            "Only candidates/config_override.json may be materialized.",
        ],
        metric_definitions={
            "d0_gate": "All local validation, isolation, and dry-plan checks pass."
        },
        baseline_summary=(
            "C1 safely rejected a provider error and produced no proposal. D0 "
            "therefore uses a labeled local fixture to validate integration only."
        ),
    )
    provider_result = ProviderCallResult(
        provider="fake-provider",
        model="d0-deterministic-fixture",
        started_at="2026-09-02T00:00:00Z",
        completed_at="2026-09-02T00:00:01Z",
        response_hash=fingerprint(proposal.to_dict()),
        proposal_payload=proposal.to_dict(),
        reported_cost_usd="0",
        input_tokens=0,
        output_tokens=0,
    )
    session = ProposalAttemptController(
        campaign=campaign,
        context=context,
        incumbent_commit=base_commit,
        provider=FakeProposalProvider([provider_result]),
        model="d0-deterministic-fixture",
        proposal_slot_id="d0-fixture-slot-1",
        max_total_cost_usd="0.5",
    ).run()
    if not session.accepted or session.proposal is None:
        raise RuntimeError("D0 fixture proposal did not pass the proposal contract")

    python = Path(sys.executable).resolve()
    checker = ROOT / "scripts/check_d0_candidate_config.py"
    checks = {
        "config-contract": HarnessCheck.create(
            check_id="config-contract",
            argv=(str(python), str(checker), TARGET_PATH),
            timeout_seconds=30,
        ),
        "dry-run": HarnessCheck.create(
            check_id="dry-run",
            argv=(str(python), str(checker), TARGET_PATH, "--dry-resolve"),
            timeout_seconds=30,
        ),
    }
    manager = GitExperimentManager(
        repository=ROOT,
        worktree_root=worktree_root,
        enforcer=ProposalEnforcer(
            EnforcementPolicy.create(trusted_test_ids=list(checks))
        ),
        trusted_checks=checks,
    )
    base_config = load_d1_config(ROOT / "configs/d1/control.yaml")
    preparation = manager.prepare(
        session.proposal,
        campaign,
        incumbent_commit=base_commit,
        base_config=base_config,
    )
    if preparation.status != PreparationStatus.READY:
        raise RuntimeError(f"D0 preparation failed: {preparation.to_dict()}")
    assert preparation.worktree_path is not None
    assert preparation.candidate_commit is not None

    plan = D1PlanBuilder(
        results_root=worker_results,
        python_executable=python,
        environment={
            "RLINF_HOME": "/opt/enpire-d0/rlinf",
            "STAGE1_CHECKPOINT": "/opt/enpire-d0/stage1",
            "NORM_STATS_PATH": "/opt/enpire-d0/norm_stats.json",
            "WANDB_PROJECT": "enpire-d0-no-call",
            "D1_SEED": "2026",
        },
    ).build(
        campaign=campaign,
        workspace=Path(preparation.worktree_path),
        source_config_relative_path=TARGET_PATH,
        trial_id="d0-fixture-seed2026",
        arm_id=session.proposal.arm_id,
        parent_commit=base_commit,
        candidate_commit=preparation.candidate_commit,
        seed=2026,
        max_wall_time_seconds=1800,
        max_gpu_cost_usd="15",
        mode=ExecutionMode.DRY_RUN,
    )
    authorization = M5Authorization.create(
        campaign=campaign,
        mode=ExecutionMode.DRY_RUN,
        authorized_at=datetime.now(timezone.utc),
    )
    backend = D1ExperimentBackend(NoCallTransport()).run(plan, authorization)
    stable_after = repository_snapshot(ROOT)
    refs_after = _branch_refs()
    expected_branch = preparation.branch_name
    assert expected_branch is not None
    other_refs_unchanged = all(refs_after.get(name) == value for name, value in refs_before.items())
    only_expected_ref_added = set(refs_after) - set(refs_before) == {expected_branch}
    derived_outside_candidate = not Path(plan.derived_config_path).is_relative_to(
        Path(preparation.worktree_path)
    )
    no_execute_flags = (
        "--execute" not in plan.execution_argv
        and "--acknowledge-paid-run" not in plan.execution_argv
    )
    passed = all(
        (
            stable_before == stable_after,
            other_refs_unchanged,
            only_expected_ref_added,
            derived_outside_candidate,
            no_execute_flags,
            backend.status == BackendStatus.PLANNED,
            backend.process is None,
            all(check.passed for check in preparation.checks),
        )
    )
    report = {
        "schema_version": 1,
        "status": "passed" if passed else "blocked",
        "claim_scope": "D0 integration fixture only; no Claude or performance claim",
        "campaign": campaign.to_dict(),
        "campaign_hash": campaign.fingerprint(),
        "context_hash": context.context_hash,
        "proposal_session": session.to_dict(),
        "preparation": preparation.to_dict(),
        "launch_plan": plan.to_dict(),
        "authorization": authorization.to_dict(),
        "backend": backend.to_dict(),
        "stable_before": stable_before,
        "stable_after": stable_after,
        "other_refs_unchanged": other_refs_unchanged,
        "only_expected_ref_added": only_expected_ref_added,
        "derived_config_outside_candidate": derived_outside_candidate,
        "execution_flags_absent": no_execute_flags,
        "external_process_launched": False,
        "gpu_used": False,
        "provider_call_made": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/provider-acceptance/d0/dry-run.json",
    )
    parser.add_argument(
        "--worktree-root", type=Path, default=Path("/private/tmp/enpire-d0-worktrees")
    )
    parser.add_argument(
        "--worker-results", type=Path, default=Path("/private/tmp/enpire-d0-results")
    )
    args = parser.parse_args()
    report = run(args.output, args.worktree_root, args.worker_results)
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
