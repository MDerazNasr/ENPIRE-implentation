"""Frozen, non-authorizing G0 E1 Stage-1 baseline selection rule."""

from __future__ import annotations

import math
from typing import Any

from supervisor.canonical import (
    fingerprint,
    require_exact_keys,
    require_git_commit,
    require_identifier,
    require_sha256,
)


CHECKPOINT_STEPS = (250, 500, 1000, 2000)
TRAINING_SEED = 2026
DEVELOPMENT_OUTCOME_COUNT = 256
NON_DEGENERACY_FLOOR = 0.05
PLATEAU_DELTA = 0.02
SELECTION_RULE = "g0-e1-stage1-horizon-v1"

INPUT_KEYS = {
    "schema_version",
    "record_kind",
    "lineage_id",
    "training_seed",
    "source_commit",
    "stage1_config_sha256",
    "actor_parent_sha256",
    "development_reset_sha256",
    "evaluator_source_sha256",
    "evaluator_environment_sha256",
    "evaluation_set_role",
    "checkpoints",
}
CHECKPOINT_KEYS = {
    "step",
    "checkpoint_sha256",
    "success_once",
    "valid_outcomes",
    "ancestry_complete",
    "loaded_without_fallback",
}


def _rate(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1
    ):
        return None
    return float(value)


def select_e1_baseline(value: Any) -> dict[str, Any]:
    """Select the frozen E1 checkpoint or return a fail-closed result."""

    contract = require_exact_keys(value, "E1 baseline input", INPUT_KEYS)
    if contract["schema_version"] != 1 or contract["record_kind"] != "g0-e1-baseline-input":
        raise ValueError("E1 baseline input identity is invalid")
    require_identifier(contract["lineage_id"], "E1 lineage ID")
    require_git_commit(contract["source_commit"], "E1 source commit")
    for field in (
        "stage1_config_sha256",
        "actor_parent_sha256",
        "development_reset_sha256",
        "evaluator_source_sha256",
        "evaluator_environment_sha256",
    ):
        require_sha256(contract[field], field)
    if contract["training_seed"] != TRAINING_SEED:
        raise ValueError("E1 training seed must be 2026")
    if contract["evaluation_set_role"] != "development":
        raise ValueError("E1 selection may use only the development reset set")
    if not isinstance(contract["checkpoints"], list) or len(contract["checkpoints"]) != 4:
        raise ValueError("E1 input must contain the complete four-checkpoint grid")

    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(contract["checkpoints"]):
        checkpoint = require_exact_keys(raw, f"E1 checkpoint {index}", CHECKPOINT_KEYS)
        expected_step = CHECKPOINT_STEPS[index]
        if checkpoint["step"] != expected_step:
            raise ValueError("E1 checkpoint steps must be exactly [250, 500, 1000, 2000]")
        require_sha256(checkpoint["checkpoint_sha256"], f"checkpoint {expected_step} SHA-256")
        success = _rate(checkpoint["success_once"])
        if success is None:
            errors.append(f"checkpoint {expected_step} has invalid success_once")
        if checkpoint["valid_outcomes"] != DEVELOPMENT_OUTCOME_COUNT:
            errors.append(f"checkpoint {expected_step} does not have 256 valid outcomes")
        if checkpoint["ancestry_complete"] is not True:
            errors.append(f"checkpoint {expected_step} has incomplete ancestry")
        if checkpoint["loaded_without_fallback"] is not True:
            errors.append(f"checkpoint {expected_step} did not load without fallback")
        parsed.append({**checkpoint, "success_once": success})

    input_sha256 = fingerprint(contract)
    plateau_at_step = None
    if not errors:
        improvements = [
            parsed[index]["success_once"] - parsed[index - 1]["success_once"]
            for index in range(1, len(parsed))
        ]
        for index in range(1, len(improvements)):
            if improvements[index - 1] < PLATEAU_DELTA and improvements[index] < PLATEAU_DELTA:
                plateau_at_step = CHECKPOINT_STEPS[index + 1]
                break

    selected = None
    status = "inconclusive"
    reason = "; ".join(errors) if errors else "no checkpoint meets the non-degeneracy floor"
    if not errors:
        best = max(parsed, key=lambda item: (item["success_once"], -item["step"]))
        if best["success_once"] >= NON_DEGENERACY_FLOOR:
            selected = best
            status = "selected"
            reason = "highest development success; exact ties select the earlier checkpoint"

    payload = {
        "schema_version": 1,
        "record_kind": "g0-e1-baseline-selection",
        "selection_rule": SELECTION_RULE,
        "input_sha256": input_sha256,
        "lineage_id": contract["lineage_id"],
        "training_seed": TRAINING_SEED,
        "checkpoint_steps": list(CHECKPOINT_STEPS),
        "development_outcome_count": DEVELOPMENT_OUTCOME_COUNT,
        "non_degeneracy_floor": NON_DEGENERACY_FLOOR,
        "plateau_delta": PLATEAU_DELTA,
        "plateau_at_step": plateau_at_step,
        "status": status,
        "reason": reason,
        "selected_step": selected["step"] if selected else None,
        "selected_checkpoint_sha256": selected["checkpoint_sha256"] if selected else None,
        "selected_success_once": selected["success_once"] if selected else None,
        "final_evaluation_used": False,
        "scientific_evaluation_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}
