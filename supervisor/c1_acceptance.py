"""Curated C1 D1 context and mutation-audited provider acceptance helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from supervisor.canonical import canonical_json, fingerprint
from supervisor.context import ContextBundle, SourceExcerpt, build_context
from supervisor.contracts import CampaignSpec


C1_BASE_COMMIT = "d151b404aaeff3507047835eff14f6fa55cb9af0"
C1_CAMPAIGN_ID = "c1-d1-config-acceptance"
C1_PROPOSAL_SLOT_ID = "c1-d1-config-slot-1"
C1_ARM_ID = "claude-config"
C1_TARGET_PATH = "candidates/config_override.json"
C1_RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def build_c1_campaign() -> CampaignSpec:
    return CampaignSpec.from_dict(
        {
            "schema_version": 1,
            "campaign_id": C1_CAMPAIGN_ID,
            "research_question": (
                "Provider acceptance only: can Claude produce one bounded, "
                "configuration-only D1 hypothesis from curated one-seed evidence?"
            ),
            "baseline_commit": C1_BASE_COMMIT,
            "rlinf_commit": C1_RLINF_COMMIT,
            "edit_mode": "config_only",
            "editable_paths": [C1_TARGET_PATH],
            "allowed_parameters": {
                "online_bc_weight": {
                    "kind": "number",
                    "minimum": "1",
                    "maximum": "3.5",
                },
                "warmup_bc_weight": {
                    "kind": "number",
                    "minimum": "3.5",
                    "maximum": "8.5",
                },
            },
            "seeds": [2026],
            "reset_set_hash": fingerprint(
                {
                    "status": "not-packaged",
                    "use": "c1-provider-contract-only-no-execution",
                }
            ),
            "evaluator_version": "c1-structure-only-v1",
            "training_budget_steps": 100,
            "evaluation_trajectories": 256,
            "max_concurrency": 1,
            "artifact_namespace": "enpire-c1-provider-acceptance",
            "created_at": "2026-09-02T00:00:00Z",
            "budget": {
                "max_trials": 1,
                "max_wall_time_seconds": 108000,
                "max_gpu_cost_usd": "150",
                "max_llm_cost_usd": "0.5",
            },
        }
    )


def build_c1_context(repository: Path) -> tuple[CampaignSpec, ContextBundle]:
    campaign = build_c1_campaign()
    summary = _read_json(
        repository
        / "results/d1-evidence-pack/raw/candidate-c-corrected-final-summary.json"
    )
    readiness = _read_json(repository / "results/d1-stage7/readiness.json")
    payload = readiness.get("payload", {})
    blockers = payload.get("blockers", []) if isinstance(payload, dict) else []
    evidence = {
        "control_success": "18/256",
        "candidate_success": "17/256",
        "candidate_success_rate": summary["fixed_evaluation"]["success_rate"],
        "observed_delta_percentage_points": summary["comparison"][
            "success_delta_percentage_points"
        ],
        "formal_decision": summary["comparison"]["formal_decision"],
        "limitations": summary["limitations"],
    }
    readiness_excerpt = {
        "canonical_pack_ready": False,
        "blocker_count": len(blockers),
        "blockers": blockers,
    }
    context = build_context(
        campaign,
        incumbent_commit=C1_BASE_COMMIT,
        immutable_boundaries=[
            "This is provider-contract acceptance only; no proposal is authorized to execute.",
            "Use arm_id claude-config and base_commit d151b404aaeff3507047835eff14f6fa55cb9af0.",
            "Use only evidence IDs d1-one-seed-result and d1-readiness-boundary.",
            "Change only candidates/config_override.json through warmup_bc_weight and/or online_bc_weight.",
            "The base VLA, RLinf, simulator, evaluator, resets, budgets, and promotion rules are immutable.",
            "One seed and mismatched runtimes cannot support a causal or scientific improvement claim.",
            "Requested tests must use identifiers config-contract and/or dry-run; no GPU run is requested in C1.",
        ],
        metric_definitions={
            "eval_success_once": (
                "Fixed-set successful trajectories divided by 256; the eventual "
                "evaluator, not the provider, determines outcomes."
            ),
            "paired_seed_delta": (
                "Candidate success rate minus matched control success rate per "
                "seed; three approved matched seeds are required for a decision."
            ),
        },
        baseline_summary=(
            "Control B seed 2026 achieved 18/256 fixed-set successes. The corrected "
            "0.8x BC-weight Candidate achieved 17/256, a -0.390625 percentage-point "
            "observed delta. This is one-seed, runtime-mismatched engineering evidence "
            "and the formal result remains inconclusive."
        ),
        excerpts=[
            SourceExcerpt.create(
                excerpt_id="d1-one-seed-result",
                kind="evidence_summary",
                title="Corrected D1 one-seed engineering result",
                content=canonical_json(evidence),
            ),
            SourceExcerpt.create(
                excerpt_id="d1-readiness-boundary",
                kind="protocol",
                title="Canonical D1 evidence-pack readiness boundary",
                content=canonical_json(readiness_excerpt),
            ),
        ],
        delta_summary=(
            "The previous tested adjustment reduced warmup_bc_weight from 7 to 5.6 "
            "and online_bc_weight from 2.5 to 2.0. It did not improve the observed "
            "seed-2026 result. Propose a different bounded hypothesis or a justified "
            "return toward the control values; do not claim it will improve performance."
        ),
    )
    return campaign, context


def context_record(campaign: CampaignSpec, context: ContextBundle) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign": campaign.to_dict(),
        "campaign_hash": campaign.fingerprint(),
        "context_hash": context.context_hash,
        "byte_count": context.byte_count,
        "excerpt_hashes": list(context.excerpt_hashes),
        "rendered_prompt": context.rendered_prompt,
    }


def repository_snapshot(repository: Path) -> dict[str, Any]:
    def git_bytes(*args: str) -> bytes:
        completed = subprocess.run(
            ["git", *args],
            cwd=repository,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
            shell=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Git snapshot command failed: {args[0]} "
                f"(stderr SHA-256 {hashlib.sha256(completed.stderr).hexdigest()})"
            )
        return completed.stdout

    status = git_bytes("status", "--porcelain=v1", "-z", "--untracked-files=all")
    index = git_bytes("ls-files", "-s", "-z")
    head = git_bytes("rev-parse", "HEAD").decode("ascii").strip()
    return {
        "head": head,
        "clean": not status,
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "index_sha256": hashlib.sha256(index).hexdigest(),
    }

