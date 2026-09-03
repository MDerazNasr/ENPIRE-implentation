#!/usr/bin/env python3
"""Run the bounded no-GPU E2 proposal-to-live-objective acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import RLINF_COMMIT, load_d1_config  # noqa: E402
from supervisor.canonical import fingerprint  # noqa: E402
from supervisor.contracts import CampaignSpec  # noqa: E402
from supervisor.d1_backend import (  # noqa: E402
    D1PlanBuilder,
    D1ProcessWorker,
    ExecutionMode,
    M5Authorization,
)
from supervisor.e2_acceptance import verify_e2_identity  # noqa: E402
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer  # noqa: E402
from supervisor.git_manager import (  # noqa: E402
    GitExperimentManager,
    HarnessCheck,
    PreparationStatus,
)
from supervisor.proposals import Proposal  # noqa: E402


OBJECTIVE_PATH = "supervisor/objectives/actor_objective.py"
CONFIG_PATH = "configs/d1/control.json"
DEFAULT_SOURCE = (
    '"""Default objective fixture."""\n\n'
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss\n"
)
REJECTED_SOURCE = (
    '"""Forbidden E2 fixture."""\n\n'
    "import os\n\n"
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss\n"
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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


def _proposal(campaign: CampaignSpec, base: str, proposal_id: str, source: str):
    return Proposal.from_dict(
        {
            "schema_version": 1,
            "proposal_id": proposal_id,
            "campaign_id": campaign.campaign_id,
            "arm_id": "e2-objective-code",
            "base_commit": base,
            "edit_mode": "actor_objective_code",
            "hypothesis": "Exercise one bounded non-default BC objective term.",
            "evidence_ids": ["e1-default-equivalence"],
            "expected_effect": "Change a finite forward value and policy gradient.",
            "falsification_condition": "No behavior change or any invalid tensor.",
            "rollback_condition": "Acceptance fixture is never promoted.",
            "changed_paths": [OBJECTIVE_PATH],
            "requested_tests": ["config-contract", "dry-run"],
            "estimated_budget": {
                "wall_time_seconds": 60,
                "gpu_cost_usd": "0.01",
                "llm_cost_usd": "0",
            },
            "unified_diff": _diff(DEFAULT_SOURCE, source),
        }
    )


def _campaign(base: str) -> CampaignSpec:
    return CampaignSpec.from_dict(
        {
            "schema_version": 1,
            "campaign_id": "e2-live-objective-acceptance",
            "research_question": (
                "Can one bounded M6 candidate reach the exact live objective seam "
                "with complete identity provenance?"
            ),
            "baseline_commit": base,
            "rlinf_commit": RLINF_COMMIT,
            "edit_mode": "actor_objective_code",
            "editable_paths": [OBJECTIVE_PATH],
            "allowed_parameters": {},
            "seeds": [2026],
            "reset_set_hash": (
                "e152b29420e18841c55f81b403640958f196844253d8fc58421fe19b629e907b"
            ),
            "evaluator_version": "e2-attachment-only-v1",
            "training_budget_steps": 1,
            "evaluation_trajectories": 256,
            "max_concurrency": 1,
            "artifact_namespace": "e2-live-objective-acceptance",
            "created_at": "2026-09-03T00:00:00Z",
            "budget": {
                "max_trials": 1,
                "max_wall_time_seconds": 60,
                "max_gpu_cost_usd": "0.01",
                "max_llm_cost_usd": "0.01",
            },
        }
    )


def _manager(repository: Path, worktrees: Path) -> GitExperimentManager:
    checks = {
        name: HarnessCheck.create(
            check_id=name,
            argv=(sys.executable, "-c", "pass"),
            timeout_seconds=10,
        )
        for name in ("config-contract", "dry-run")
    }
    return GitExperimentManager(
        repository=repository,
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
            timeout_seconds=20,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--rlinf-root", required=True, type=Path)
    parser.add_argument("--torch-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.work_root.exists():
        raise SystemExit(f"E2 work root already exists: {args.work_root}")
    if not args.torch_python.is_file():
        raise SystemExit(f"PyTorch interpreter is missing: {args.torch_python}")

    repository = args.work_root / "stable"
    worktrees = args.work_root / "worktrees"
    results = args.work_root / "results"
    (repository / "supervisor" / "objectives").mkdir(parents=True)
    (repository / "configs" / "d1").mkdir(parents=True)
    worktrees.mkdir(parents=True)
    _git(repository, "init", "-q", "-b", "main")
    (repository / OBJECTIVE_PATH).write_text(DEFAULT_SOURCE)
    config = load_d1_config(ROOT / "configs/d1/control.yaml")
    config.update(
        fixture_success_rate=0.4,
        fixture_code_success_rate=0.41,
        fixture_episode_length=40,
    )
    (repository / CONFIG_PATH).write_text(json.dumps(config, indent=2) + "\n")
    _git(repository, "add", ".")
    _git(
        repository,
        "-c",
        "user.name=E2 Fixture",
        "-c",
        "user.email=e2@invalid.local",
        "commit",
        "-q",
        "-m",
        "E2 fixture baseline",
    )
    base = _git(repository, "rev-parse", "HEAD")
    campaign = _campaign(base)
    manager = _manager(repository, worktrees)

    rejected = manager.prepare(
        _proposal(campaign, base, "e2-rejected-import", REJECTED_SOURCE),
        campaign,
        incumbent_commit=base,
    )
    if rejected.status not in {PreparationStatus.REJECTED, PreparationStatus.FAILED}:
        raise AssertionError("invalid E2 control was not retained as a rejection")

    candidate_source = (
        ROOT / "examples" / "agent-supervisor" / "e2_actor_objective_candidate.py"
    ).read_text()
    proposal = _proposal(campaign, base, "e2-bounded-bc-term", candidate_source)
    preparation = manager.prepare(proposal, campaign, incumbent_commit=base)
    if preparation.status != PreparationStatus.READY:
        raise AssertionError(f"E2 candidate preparation failed: {preparation.errors}")
    candidate_workspace = Path(preparation.worktree_path)
    candidate_objective = candidate_workspace / OBJECTIVE_PATH
    objective_hash = hashlib.sha256(candidate_objective.read_bytes()).hexdigest()

    builder = D1PlanBuilder(
        results_root=results,
        python_executable=Path(sys.executable),
        fixture_launcher=ROOT / "scripts" / "m5_fixture_launcher.py",
    )
    plan = builder.build(
        campaign=campaign,
        workspace=candidate_workspace,
        source_config_relative_path=CONFIG_PATH,
        objective_relative_path=OBJECTIVE_PATH,
        trial_id="e2-live-objective-s2026",
        arm_id=proposal.arm_id,
        parent_commit=base,
        candidate_commit=preparation.candidate_commit,
        seed=2026,
        max_wall_time_seconds=60,
        max_gpu_cost_usd="0.01",
        mode=ExecutionMode.FIXTURE,
    )
    authorization = M5Authorization.create(
        campaign=campaign,
        mode=ExecutionMode.FIXTURE,
        authorized_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        allow_fixture_execution=True,
    )
    worker = D1ProcessWorker(worker_id="e2-local-worker")
    worker.register(plan, authorization)
    worker.prepare(plan.contract)
    worker.launch(plan.contract.trial_id)
    backend_result = worker.fetch_result(plan.contract.trial_id)
    if backend_result.evidence is None:
        raise AssertionError(f"E2 fixture produced no evidence: {backend_result.errors}")

    runtime_path = results / "e2-runtime-attachment.json"
    probe = subprocess.run(
        [
            str(args.torch_python),
            str(ROOT / "scripts" / "probe_e2_objective_candidate.py"),
            "--rlinf-root",
            str(args.rlinf_root),
            "--plugin",
            str(candidate_objective),
            "--objective-sha256",
            objective_hash,
            "--output",
            str(runtime_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        raise AssertionError(f"E2 PyTorch probe failed: {probe.stderr or probe.stdout}")

    manifest = json.loads(Path(plan.manifest_path).read_text())
    runtime = json.loads(runtime_path.read_text())
    evidence = backend_result.evidence.to_dict()
    identity_checks = verify_e2_identity(
        objective_sha256=objective_hash,
        plan=plan.to_dict(),
        manifest=manifest,
        runtime=runtime,
        evidence=evidence,
    )
    record = {
        "authorization": authorization.to_dict(),
        "candidate": {
            "candidate_commit": preparation.candidate_commit,
            "candidate_tree_hash": preparation.candidate_tree_hash,
            "objective_sha256": objective_hash,
            "proposal_hash": proposal.fingerprint(),
            "source_fixture": "examples/agent-supervisor/e2_actor_objective_candidate.py",
        },
        "evidence": evidence,
        "evidence_hash": backend_result.evidence.fingerprint(),
        "gpu_used": False,
        "identity_checks": identity_checks,
        "llm_used": False,
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(Path(plan.manifest_path).read_bytes()).hexdigest(),
        "non_promotable": True,
        "plan": plan.to_dict(),
        "plan_hash": plan.fingerprint(),
        "proposal_origin": "deterministic-e2-acceptance-fixture",
        "rejected_candidates": [rejected.to_dict()],
        "rlinf_training_steps": 0,
        "runtime_attachment": runtime,
        "runtime_attachment_sha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
        "schema_version": 1,
        "stable_head_after": _git(repository, "rev-parse", "HEAD"),
        "stable_head_before": base,
        "status": "passed",
        "summary": (
            "Engineering provenance acceptance only; no policy performance or "
            "promotion conclusion."
        ),
    }
    if record["stable_head_after"] != base:
        raise AssertionError("E2 stable fixture repository moved")
    record["record_fingerprint"] = fingerprint(record)
    encoded = json.dumps(record, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
