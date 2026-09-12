#!/usr/bin/env python3
"""Build the non-authorizing GPU-free G0/E0 integrity preflight."""

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
from supervisor.evaluator_deployment import verify_local_isolation_receipt
from supervisor.evaluator_integrity import ResetSetArtifact
from supervisor.g0_protocol_inputs import (
    validate_cost_retention_candidate,
    validate_runtime_identity_candidate,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_preflight(root: Path = ROOT) -> dict:
    sources = {
        "integrity_boundary": "supervisor/evaluator_integrity.py",
        "independent_runner": "scripts/g0_independent_evaluator.py",
        "bundle_builder": "scripts/build_g0_evaluator_bundle.py",
        "deployment_boundary": "supervisor/evaluator_deployment.py",
        "isolation_rehearsal": "scripts/run_g0_evaluator_isolation_rehearsal.py",
        "protocol_input_boundary": "supervisor/g0_protocol_inputs.py",
        "runtime_cost_candidate_builder": "scripts/build_g0_runtime_cost_candidates.py",
        "reset_capture_materializer": "scripts/export_g0_reset_sets.py",
        "reset_capture_producer": "scripts/capture_g0_maniskill_episode_seeds.py",
        "reset_repeat_verifier": "scripts/verify_g0_reset_repeat.py",
        "reset_runtime_confirmation": "scripts/run_g0_reset_runtime_confirmation.py",
        "g0_decision_rule": "supervisor/g0_decision.py",
        "official_rule": "agent/d1_rules.py",
        "supervisor_evaluator": "supervisor/evaluation.py",
        "seed_reset_design": "docs/agent-supervisor/g0-seeds-and-reset-sets.md",
        "decision_worksheet": "docs/agent-supervisor/g0-decision-worksheet.md",
        "remaining_decisions_proposal": "docs/agent-supervisor/g0-remaining-decisions-proposal.md",
        "reset_source_audit": "docs/agent-supervisor/g0-reset-source-audit.md",
        "custody_deployment_design": "docs/agent-supervisor/g0-evaluator-custody-and-deployment.md",
        "runtime_cost_candidate_design": "docs/agent-supervisor/g0-runtime-cost-retention-candidate.md",
        "scientific_program": "docs/agent-supervisor/g0-scientific-experiment-test-program.md",
    }
    hashes = {name: _sha256(root / relative) for name, relative in sources.items()}
    reset_root = root / "results/agent-supervisor/g0/reset-sets"
    reset_status = {
        "development": {"count": 256, "generator_seed": 2026, "sha256": None},
        "final": {"count": 256, "generator_seed": 2027, "sha256": None},
        "status": "blocked_pending_pinned_simulator_export",
    }
    development_path = reset_root / "development.json"
    repeat_path = reset_root / "repeat-export.json"
    runtime_path = reset_root / "runtime-confirmation.json"
    if development_path.is_file() and repeat_path.is_file():
        development = ResetSetArtifact.from_dict(json.loads(development_path.read_text(encoding="utf-8")))
        repeat = json.loads(repeat_path.read_text(encoding="utf-8"))
        if fingerprint(repeat["payload"]) != repeat["sha256"]:
            raise ValueError("reset repeat receipt hash mismatch")
        if repeat["payload"].get("development_sha256") != development.fingerprint():
            raise ValueError("reset repeat receipt artifact mismatch")
        if repeat["payload"].get("byte_identical") is not True or repeat["payload"].get("simulator_runtime_reset_confirmed") is not False:
            raise ValueError("reset repeat receipt claim boundary is invalid")
        runtime_confirmed = False
        runtime_sha256 = None
        if runtime_path.is_file():
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            if fingerprint(runtime["payload"]) != runtime["sha256"]:
                raise ValueError("reset runtime confirmation hash mismatch")
            if runtime["payload"].get("status") != "pass" or runtime["payload"].get("policy_evaluation_executed") is not False or runtime["payload"].get("gpu_used") is not False:
                raise ValueError("reset runtime confirmation claim boundary is invalid")
            for role in ("development", "final"):
                result = runtime["payload"]["results"][role]
                if result.get("matches_source_derived") is not True or result.get("ordered_ids_sha256") != repeat["payload"][f"{role}_ordered_ids_sha256"]:
                    raise ValueError("reset runtime confirmation does not match source capture")
            runtime_confirmed = True
            runtime_sha256 = runtime["sha256"]
        reset_status = {
            "development": {"count": 256, "generator_seed": 2026, "sha256": development.fingerprint()},
            "final": {"count": 256, "generator_seed": 2027, "sha256": repeat["payload"]["final_sha256"], "ordered_ids_in_repository": False},
            "overlap_count": 0,
            "repeat_export_sha256": repeat["sha256"],
            "simulator_runtime_reset_confirmed": runtime_confirmed,
            "runtime_confirmation_sha256": runtime_sha256,
            "status": "runtime_confirmed_final_custody_pending" if runtime_confirmed else "source_derived_repeat_passed_final_custody_and_runtime_confirmation_pending",
        }
    isolation_status = {
        "status": "not_run",
        "production_custody_accepted": False,
        "production_deployment_accepted": False,
    }
    isolation_path = root / "results/agent-supervisor/g0/evaluator-isolation-rehearsal-v2.json"
    if isolation_path.is_file():
        if reset_status["final"]["sha256"] is None:
            raise ValueError("isolation rehearsal exists without a final reset hash")
        isolation = verify_local_isolation_receipt(
            json.loads(isolation_path.read_text(encoding="utf-8")),
            reset_status["final"]["sha256"],
        )
        isolation_status = {
            "status": isolation["payload"]["status"],
            "receipt_sha256": isolation["sha256"],
            "bundle_manifest_sha256": isolation["payload"]["evaluator_bundle"]["manifest_sha256"],
            "production_custody_accepted": False,
            "production_deployment_accepted": False,
        }
    runtime_candidate = validate_runtime_identity_candidate(json.loads(
        (root / "results/agent-supervisor/g0/runtime-identities-candidate-v2.json").read_text(encoding="utf-8")
    ))
    cost_candidate = validate_cost_retention_candidate(json.loads(
        (root / "results/agent-supervisor/g0/cost-envelope-candidate-v2.json").read_text(encoding="utf-8")
    ))
    protocol_input_status = {
        "runtime_candidate_sha256": runtime_candidate["sha256"],
        "runtime_status": runtime_candidate["payload"]["status"],
        "cost_candidate_sha256": cost_candidate["sha256"],
        "cost_status": cost_candidate["payload"]["status"],
        "canonical_runtime_identity_accepted": False,
        "canonical_cost_retention_accepted": False,
    }
    payload = {
        "schema_version": 1,
        "gate": "G0-E0",
        "status": "implementation_ready_for_human_review",
        "source_files": sources,
        "source_hashes": hashes,
        "protocol_fingerprint": fingerprint({"source_files": sources, "source_hashes": hashes}),
        "accepted_seed_policy": [2026, 2027, 2028],
        "accepted_stage1_policy": "one E1-selected seed-2026 actor fixed across first E2",
        "reset_artifacts": reset_status,
        "evaluator_isolation": isolation_status,
        "runtime_cost_candidates": protocol_input_status,
        "evaluation_executed": False,
        "promotion_executed": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "campaign_activation_authorized": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    preflight = build_preflight()
    rendered = json.dumps(preflight, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
