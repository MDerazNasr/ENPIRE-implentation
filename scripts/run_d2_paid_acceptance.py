#!/usr/bin/env python3
"""Prepare, then explicitly execute, the non-promotable D2 Modal acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import load_d1_config  # noqa: E402
from supervisor.attempts import ProposalSessionResult  # noqa: E402
from supervisor.c1_acceptance import repository_snapshot  # noqa: E402
from supervisor.canonical import canonical_json, fingerprint, timestamp_text  # noqa: E402
from supervisor.contracts import (  # noqa: E402
    ApprovalEnvelope,
    CampaignSpec,
    EngineeringAcceptanceApproval,
)
from supervisor.coordinator import IterationStatus, OfflineCampaignCoordinator  # noqa: E402
from supervisor.d1_backend import (  # noqa: E402
    D1CoordinatorContractFactory,
    D1ExperimentBackend,
    D1LaunchPlan,
    D1PlanBuilder,
    D1ProcessWorker,
    ExecutionMode,
    M5Authorization,
)
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer  # noqa: E402
from supervisor.evaluation import ArmIncumbentStore  # noqa: E402
from supervisor.git_manager import (  # noqa: E402
    GitExperimentManager,
    HarnessCheck,
    PreparationRecord,
    PreparationStatus,
)
from supervisor.modal_acceptance import (  # noqa: E402
    ModalAcceptanceRequest,
    ModalAcceptanceTransport,
)
from supervisor.proposals import Proposal  # noqa: E402


CAMPAIGN_ID = "d2-paid-config-attachment-v1"
PROPOSAL_ID = "d2-paid-config-fixture-01"
ARM_ID = "paid-acceptance-config"
TARGET_PATH = "candidates/config_override.json"
PROFILE_PATH = ROOT / "results/provider-acceptance/d2/profile.json"
PREFLIGHT_PATH = ROOT / "results/provider-acceptance/d2/preflight.json"
RESULT_PATH = ROOT / "results/provider-acceptance/d2/result.json"
WORKTREE_ROOT = Path("/private/tmp/enpire-d2-worktrees")
REMOTE_ROOT = Path("/private/tmp/enpire-d2-paid-acceptance")
RESULTS_ROOT = REMOTE_ROOT / "results"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
MODAL_PROFILE = "deraznasr776"


class ForbiddenEvaluator:
    def evaluate(self, **kwargs):
        raise AssertionError("D2 paid acceptance cannot invoke the evaluator")


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def branch_refs() -> dict[str, str]:
    output = git("for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(line.split(" ", 1) for line in output.splitlines() if line)


def profile_hash() -> str:
    return hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()


def campaign(base_commit: str) -> CampaignSpec:
    return CampaignSpec.from_dict(
        {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "research_question": (
                "Engineering acceptance only: can one allowlisted configuration "
                "execute through the immutable Modal adapter without evaluation?"
            ),
            "baseline_commit": base_commit,
            "rlinf_commit": RLINF_COMMIT,
            "edit_mode": "config_only",
            "editable_paths": [TARGET_PATH],
            "allowed_parameters": {
                "scientific_values.online_bc_weight": {
                    "kind": "number", "minimum": "2.25", "maximum": "2.25"
                }
            },
            "seeds": [2026],
            "reset_set_hash": fingerprint(
                {"profile_sha256": profile_hash(), "acceptance_reset_count": 1}
            ),
            "evaluator_version": "d2-acceptance-evaluation-forbidden-v1",
            "training_budget_steps": 1,
            "evaluation_trajectories": 1,
            "max_concurrency": 1,
            "artifact_namespace": "enpire-d2-paid-acceptance-v1",
            "created_at": "2026-09-02T21:09:03Z",
            "budget": {
                "max_trials": 1,
                "max_wall_time_seconds": 1800,
                "max_gpu_cost_usd": "1.5156",
                "max_llm_cost_usd": "0.01",
            },
        }
    )


def proposal(spec: CampaignSpec, base_commit: str) -> Proposal:
    return Proposal.from_dict(
        {
            "schema_version": 1,
            "proposal_id": PROPOSAL_ID,
            "campaign_id": spec.campaign_id,
            "arm_id": ARM_ID,
            "base_commit": base_commit,
            "edit_mode": "config_only",
            "hypothesis": (
                "Acceptance fixture: online BC 2.25 reaches the executed RLinf command."
            ),
            "evidence_ids": ["d1-subprocess-acceptance"],
            "expected_effect": "Attachment evidence only; no performance claim.",
            "falsification_condition": "Any identity, artifact, runtime, or cost check fails.",
            "rollback_condition": "Retain the result and never update an incumbent.",
            "changed_paths": [TARGET_PATH],
            "requested_tests": ["config-contract", "resolved-command"],
            "estimated_budget": {
                "wall_time_seconds": 1800,
                "gpu_cost_usd": "1.5156",
                "llm_cost_usd": "0",
            },
            "config_overrides": {"scientific_values.online_bc_weight": 2.25},
        }
    )


def environment() -> dict[str, str]:
    return {
        "RLINF_HOME": "/opt/RLinf",
        "MODAL_ADAPTER_ROOT": "/opt/qualia",
        "STAGE1_CHECKPOINT": str(REMOTE_ROOT / "checkpoints/stage1-step-500-actor"),
        "NORM_STATS_PATH": "/opt/qualia/norm_stats.json",
        "WANDB_PROJECT": "qualia-rlt-d2-acceptance",
        "D1_SEED": "2026",
    }


def checks() -> dict[str, HarnessCheck]:
    python = str(Path(sys.executable).resolve())
    checker = str(ROOT / "scripts/check_d2_candidate_config.py")
    return {
        name: HarnessCheck.create(
            check_id=name,
            argv=(python, checker, TARGET_PATH),
            timeout_seconds=60,
        )
        for name in ("config-contract", "resolved-command")
    }


def manager() -> GitExperimentManager:
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    trusted = checks()
    return GitExperimentManager(
        repository=ROOT,
        worktree_root=WORKTREE_ROOT,
        enforcer=ProposalEnforcer(
            EnforcementPolicy.create(trusted_test_ids=list(trusted))
        ),
        trusted_checks=trusted,
    )


def prepare(output: Path) -> dict:
    if output.exists():
        raise SystemExit(f"preflight output already exists: {output}")
    stable_before = repository_snapshot(ROOT)
    if not stable_before["clean"]:
        raise SystemExit("integration repository must be clean before D2 preflight")
    refs_before = branch_refs()
    base_commit = stable_before["head"]
    spec = campaign(base_commit)
    proposed = proposal(spec, base_commit)
    session = ProposalSessionResult(
        proposal_slot_id="d2-paid-acceptance-fixture-slot",
        accepted=True,
        proposal=proposed,
        attempts=(),
        total_cost_usd="0",
    )
    preparation = manager().prepare(
        proposed,
        spec,
        incumbent_commit=base_commit,
        base_config=load_d1_config(ROOT / "configs/d1/d2_paid_acceptance.yaml"),
    )
    if preparation.status != PreparationStatus.READY:
        raise RuntimeError(f"D2 preparation failed: {preparation.to_dict()}")
    assert preparation.worktree_path and preparation.candidate_commit
    plan = D1PlanBuilder(
        results_root=RESULTS_ROOT,
        python_executable=Path(sys.executable),
        environment=environment(),
    ).build(
        campaign=spec,
        workspace=Path(preparation.worktree_path),
        source_config_relative_path=TARGET_PATH,
        trial_id=f"{PROPOSAL_ID}.s2026",
        arm_id=ARM_ID,
        parent_commit=base_commit,
        candidate_commit=preparation.candidate_commit,
        seed=2026,
        max_wall_time_seconds=1800,
        max_gpu_cost_usd="1.5156",
        mode=ExecutionMode.PAID_ACCEPTANCE,
    )
    request = ModalAcceptanceRequest.create(plan)
    stable_after = repository_snapshot(ROOT)
    refs_after = branch_refs()
    expected_branch = preparation.branch_name
    assert expected_branch
    passed = all(
        (
            stable_before == stable_after,
            all(refs_after.get(name) == value for name, value in refs_before.items()),
            set(refs_after) - set(refs_before) == {expected_branch},
            all(item.passed for item in preparation.checks),
            plan.mode == ExecutionMode.PAID_ACCEPTANCE,
            not plan.synthetic,
        )
    )
    report = {
        "schema_version": 1,
        "status": "ready_for_explicit_approval" if passed else "blocked",
        "claim_scope": "D2 engineering attachment acceptance only",
        "execution_authorized": False,
        "promotion_authorized": False,
        "profile_sha256": profile_hash(),
        "campaign": spec.to_dict(),
        "campaign_hash": spec.fingerprint(),
        "proposal_session": session.to_dict(),
        "preparation": preparation.to_dict(),
        "launch_plan": plan.to_dict(),
        "plan_hash": plan.fingerprint(),
        "modal_request": request.to_dict(),
        "modal_request_hash": request.fingerprint(),
        "approval_terms": {
            "provider": "Modal",
            "provider_profile": MODAL_PROFILE,
            "maximum_total_cost_usd": "3",
            "maximum_gpu_cost_usd": "1.5156",
            "maximum_wall_time_seconds": 1800,
            "maximum_trials": 1,
            "promotion_allowed": False,
        },
        "stable_before": stable_before,
        "stable_after": stable_after,
        "paid_process_launched": False,
        "gpu_used": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def execute(preflight_path: Path, output: Path, approved_by: str) -> dict:
    if output.exists():
        raise SystemExit(f"result output already exists: {output}")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "ready_for_explicit_approval":
        raise SystemExit("D2 preflight is not ready for approval")
    spec = CampaignSpec.from_dict(preflight["campaign"])
    proposed = Proposal.from_dict(preflight["proposal_session"]["proposal"])
    preparation = PreparationRecord.from_dict(preflight["preparation"])
    frozen_plan = D1LaunchPlan.from_dict(preflight["launch_plan"])
    frozen_request = ModalAcceptanceRequest.from_dict(preflight["modal_request"])
    if profile_hash() != preflight["profile_sha256"]:
        raise SystemExit("D2 profile changed after preflight")
    if frozen_plan.fingerprint() != preflight["plan_hash"]:
        raise SystemExit("D2 plan changed after preflight")
    if frozen_request.fingerprint() != preflight["modal_request_hash"]:
        raise SystemExit("D2 Modal request changed after preflight")
    if ModalAcceptanceRequest.create(frozen_plan) != frozen_request:
        raise SystemExit("D2 candidate source/config changed after preflight")
    stable_before = repository_snapshot(ROOT)
    if not stable_before["clean"]:
        raise SystemExit("integration repository must be clean before paid execution")
    now = datetime.now(timezone.utc)
    campaign_approval = ApprovalEnvelope.from_dict(
        {
            "schema_version": 1,
            "campaign_id": spec.campaign_id,
            "campaign_spec_hash": spec.fingerprint(),
            "approved_by": approved_by,
            "approved_at": timestamp_text(now),
            "expires_at": timestamp_text(now + timedelta(hours=2)),
            "edit_mode": spec.edit_mode.value,
            "max_concurrency": 1,
            "budget": spec.budget.to_dict(),
        }
    )
    approval = EngineeringAcceptanceApproval.from_dict(
        {
            "schema_version": 1,
            "campaign_approval": campaign_approval.to_dict(),
            "profile_hash": preflight["profile_sha256"],
            "provider": "Modal",
            "provider_profile": MODAL_PROFILE,
            "max_total_cost_usd": "3",
            "promotion_allowed": False,
        }
    )
    authorization = M5Authorization.create(
        campaign=spec,
        mode=ExecutionMode.PAID_ACCEPTANCE,
        authorized_at=now,
        acceptance_approval=approval,
        acknowledge_paid_run=True,
        allow_paid_acceptance=True,
    )
    transport = ModalAcceptanceTransport(
        modal_executable=Path(shutil.which("modal") or "modal"),
        app_path=ROOT / "modal_d2_acceptance.py",
        expected_profile=MODAL_PROFILE,
    )
    worker = D1ProcessWorker(
        worker_id="d2-modal-paid-acceptance-worker",
        backend=D1ExperimentBackend(transport),
    )
    factory = D1CoordinatorContractFactory(
        builder=D1PlanBuilder(
            results_root=RESULTS_ROOT,
            python_executable=Path(sys.executable),
            environment=environment(),
        ),
        worker=worker,
        authorization=authorization,
    )
    store = ArmIncumbentStore(
        REMOTE_ROOT / "local-state/incumbents.json",
        campaign_id=spec.campaign_id,
        initial_incumbents={ARM_ID: spec.baseline_commit},
    )
    session = ProposalSessionResult(
        proposal_slot_id=preflight["proposal_session"]["proposal_slot_id"],
        accepted=True,
        proposal=proposed,
        attempts=(),
        total_cost_usd="0",
    )
    result = OfflineCampaignCoordinator(
        campaign=spec,
        git_manager=manager(),
        worker=worker,
        evaluator=ForbiddenEvaluator(),
        incumbents=store,
        ledger_root=REMOTE_ROOT / "local-ledgers",
        run_contract_factory=factory,
        synthetic=False,
        evaluation_enabled=False,
    ).run(
        iteration_id="d2-paid-acceptance-iteration",
        proposal_session=session,
        control_evidence=(),
        decision_id="evaluation-forbidden",
        base_config=load_d1_config(ROOT / "configs/d1/d2_paid_acceptance.yaml"),
        prepared_candidate=preparation,
    )
    backend = worker.fetch_result(frozen_plan.contract.trial_id)
    stable_after = repository_snapshot(ROOT)
    safe_terminal = result.status in {
        IterationStatus.ACCEPTANCE_RECORDED,
        IterationStatus.WORKER_FAILED,
    }
    passed = (
        safe_terminal
        and result.evaluation is None
        and result.incumbent_after == result.incumbent_before
        and stable_before == stable_after
    )
    report = {
        "schema_version": 1,
        "status": "passed" if passed else "blocked",
        "claim_scope": "D2 engineering attachment acceptance only",
        "preflight_sha256": hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
        "campaign_hash": spec.fingerprint(),
        "profile_sha256": profile_hash(),
        "approval": approval.to_dict(),
        "approval_hash": approval.fingerprint(),
        "authorization": authorization.to_dict(),
        "backend": backend.to_dict(),
        "coordinator": result.to_dict(),
        "stable_before": stable_before,
        "stable_after": stable_after,
        "promotion_attempted": False,
        "incumbent_advanced": result.incumbent_after != result.incumbent_before,
        "result_retained_locally": True,
        "result_retained_on_modal_volume": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-paid-run", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--preflight", type=Path, default=PREFLIGHT_PATH)
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    arguments = parser.parse_args()
    if arguments.prepare == arguments.execute:
        parser.error("choose exactly one of --prepare or --execute")
    if arguments.prepare:
        if arguments.acknowledge_paid_run or arguments.approved_by:
            parser.error("preflight cannot contain paid acknowledgement or approver")
        report = prepare(arguments.preflight)
    else:
        if not arguments.acknowledge_paid_run or not arguments.approved_by:
            parser.error("execution requires acknowledgement and approver identity")
        report = execute(arguments.preflight, arguments.output, arguments.approved_by)
    print(json.dumps({"status": report["status"]}, sort_keys=True))
    return 0 if report["status"] in {"ready_for_explicit_approval", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
