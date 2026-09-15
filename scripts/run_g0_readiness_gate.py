#!/usr/bin/env python3
"""Build the fail-closed, non-authorizing G0 readiness inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import fingerprint
from supervisor.evaluator_deployment import (
    validate_production_custody_record,
    validate_production_deployment_record,
)
from supervisor.g0_acceptance import (
    validate_cost_retention_record,
    validate_protocol_acceptance_record,
    validate_runtime_identity_record,
)


BOUND_SOURCES = {
    "readiness_gate": "scripts/run_g0_readiness_gate.py",
    "decision_rule": "supervisor/g0_decision.py",
    "e1_baseline_selector": "supervisor/g0_e1_baseline.py",
    "e1_baseline_selector_cli": "scripts/select_g0_e1_baseline.py",
    "evaluator_integrity": "supervisor/evaluator_integrity.py",
    "independent_runner": "scripts/g0_independent_evaluator.py",
    "bundle_builder": "scripts/build_g0_evaluator_bundle.py",
    "deployment_boundary": "supervisor/evaluator_deployment.py",
    "isolation_rehearsal": "scripts/run_g0_evaluator_isolation_rehearsal.py",
    "protocol_input_boundary": "supervisor/g0_protocol_inputs.py",
    "acceptance_boundary": "supervisor/g0_acceptance.py",
    "runtime_cost_candidate_builder": "scripts/build_g0_runtime_cost_candidates.py",
    "reset_materializer": "scripts/export_g0_reset_sets.py",
    "reset_capture_producer": "scripts/capture_g0_maniskill_episode_seeds.py",
    "reset_repeat_verifier": "scripts/verify_g0_reset_repeat.py",
    "reset_runtime_confirmation": "scripts/run_g0_reset_runtime_confirmation.py",
    "decision_worksheet": "docs/agent-supervisor/g0-decision-worksheet.md",
    "seed_reset_design": "docs/agent-supervisor/g0-seeds-and-reset-sets.md",
    "accepted_design_subset": "docs/agent-supervisor/g0-remaining-decisions-proposal.md",
    "reset_source_audit": "docs/agent-supervisor/g0-reset-source-audit.md",
    "custody_deployment_design": "docs/agent-supervisor/g0-evaluator-custody-and-deployment.md",
    "runtime_cost_candidate_design": "docs/agent-supervisor/g0-runtime-cost-retention-candidate.md",
    "production_acceptance_runbook": "docs/agent-supervisor/g0-production-acceptance-runbook.md",
    "aws_infrastructure_runbook": "infra/aws-g0/README.md",
    "aws_audit_template": "infra/aws-g0/audit-account.template.json",
    "aws_evaluator_template": "infra/aws-g0/evaluator-account.template.json",
    "aws_template_checker": "scripts/check_g0_aws_infrastructure.py",
    "scientific_program": "docs/agent-supervisor/g0-scientific-experiment-test-program.md",
}

REQUIRED_EXTERNAL_INPUTS = {
    "development_reset_artifact": "results/agent-supervisor/g0/reset-sets/development.json",
    "final_reset_artifact_custody": "results/agent-supervisor/g0/final-reset-custody.json",
    "repeat_export_receipt": "results/agent-supervisor/g0/reset-sets/repeat-export.json",
    "production_evaluator_deployment": "results/agent-supervisor/g0/production-evaluator.json",
    "runtime_and_asset_identities": "results/agent-supervisor/g0/runtime-identities.json",
    "cost_and_retention_envelope": "results/agent-supervisor/g0/cost-envelope.json",
    "human_protocol_acceptance": "results/agent-supervisor/g0/protocol-acceptance.json",
}

PREFLIGHT_RELATIVE = "results/agent-supervisor/g0/e0-preflight-lambda-h100-route-v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_readiness(root: Path = ROOT) -> dict:
    source_hashes = {name: _sha256(root / relative) for name, relative in BOUND_SOURCES.items()}
    preflight_path = root / PREFLIGHT_RELATIVE
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if not isinstance(preflight, dict) or set(preflight) != {"payload", "sha256"}:
        raise ValueError("E0 preflight envelope fields are invalid")
    if fingerprint(preflight["payload"]) != preflight["sha256"]:
        raise ValueError("E0 preflight envelope hash mismatch")
    for field in (
        "evaluation_executed", "promotion_executed", "gpu_execution_authorized",
        "paid_execution_authorized", "provider_call_authorized",
        "model_egress_authorized", "campaign_activation_authorized",
    ):
        if preflight["payload"].get(field) is not False:
            raise ValueError("E0 preflight contains forbidden authority")
    missing = [name for name, relative in REQUIRED_EXTERNAL_INPUTS.items() if not (root / relative).is_file()]
    custody_path = root / REQUIRED_EXTERNAL_INPUTS["final_reset_artifact_custody"]
    custody = None
    if custody_path.is_file():
        custody = validate_production_custody_record(
            json.loads(custody_path.read_text(encoding="utf-8")),
            preflight["payload"]["reset_artifacts"]["final"]["sha256"],
        )
    deployment_path = root / REQUIRED_EXTERNAL_INPUTS["production_evaluator_deployment"]
    deployment = None
    if deployment_path.is_file():
        if custody is None:
            raise ValueError("production evaluator deployment exists without validated custody")
        deployment = validate_production_deployment_record(
            json.loads(deployment_path.read_text(encoding="utf-8")),
            expected_bundle_sha256=preflight["payload"]["evaluator_isolation"]["bundle_manifest_sha256"],
            expected_custody_record_sha256=custody["sha256"],
        )
    runtime_path = root / REQUIRED_EXTERNAL_INPUTS["runtime_and_asset_identities"]
    runtime = None
    if runtime_path.is_file():
        if deployment is None:
            raise ValueError("runtime identity record exists without validated evaluator deployment")
        candidate = json.loads(
            (root / "results/agent-supervisor/g0/runtime-identities-candidate-v4.json").read_text(
                encoding="utf-8"
            )
        )
        runtime = validate_runtime_identity_record(
            json.loads(runtime_path.read_text(encoding="utf-8")),
            expected_candidate_sha256=candidate["sha256"],
            expected_evaluator_environment_sha256=deployment["payload"]["environment_identity_sha256"],
            expected_development_reset_sha256=preflight["payload"]["reset_artifacts"]["development"]["sha256"],
            expected_final_reset_sha256=preflight["payload"]["reset_artifacts"]["final"]["sha256"],
        )
    cost_path = root / REQUIRED_EXTERNAL_INPUTS["cost_and_retention_envelope"]
    cost = None
    if cost_path.is_file():
        if runtime is None:
            raise ValueError("cost record exists without validated runtime identity")
        cost = validate_cost_retention_record(
            json.loads(cost_path.read_text(encoding="utf-8")),
            expected_durable_store_identity_sha256=runtime["payload"]["durable_store_identity_sha256"],
        )
    acceptance_path = root / REQUIRED_EXTERNAL_INPUTS["human_protocol_acceptance"]
    acceptance = None
    if acceptance_path.is_file():
        if custody is None or deployment is None or runtime is None or cost is None:
            raise ValueError("protocol acceptance exists without all validated prerequisite records")
        acceptance = validate_protocol_acceptance_record(
            json.loads(acceptance_path.read_text(encoding="utf-8")),
            expected_runtime_sha256=runtime["sha256"],
            expected_cost_sha256=cost["sha256"],
            expected_custody_sha256=custody["sha256"],
            expected_deployment_sha256=deployment["sha256"],
        )
    ready = not missing and all(
        item is not None for item in (custody, deployment, runtime, cost, acceptance)
    )
    payload = {
        "schema_version": 1,
        "gate": "G0",
        "status": "ready_for_e1_preflight_only" if ready else "blocked_missing_external_inputs",
        "accepted_local_design": {
            "training_seeds": [2026, 2027, 2028],
            "stage1_checkpoints": [250, 500, 1000, 2000],
            "stage2_conditions": ["control", "candidate"],
            "stage2_run_count": 6,
            "decision_rule": "g0-paired-seed-t-v1",
        },
        "bound_sources": BOUND_SOURCES,
        "source_hashes": source_hashes,
        "e0_preflight_sha256": preflight["sha256"],
        "required_external_inputs": REQUIRED_EXTERNAL_INPUTS,
        "missing_external_inputs": missing,
        "ready_transition_implemented": True,
        "scientific_evaluation_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_readiness()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
