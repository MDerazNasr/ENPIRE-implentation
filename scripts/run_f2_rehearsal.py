#!/usr/bin/env python3
"""Validate and freeze the no-launch F2 matched-runtime rehearsal."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import load_d1_config, scientific_diff  # noqa: E402
from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.workers import RunContract  # noqa: E402


DEFAULT_PROFILE = ROOT / "results/runtime-qualification/f2/profile.json"
DEFAULT_OUTPUT = ROOT / "results/runtime-qualification/f2/preflight.json"
RUNTIME_CONTRACT = ROOT / "results/runtime-qualification/f0/runtime-contract.json"
MODAL_PYTHON = Path("/opt/homebrew/Cellar/modal/1.5.3_1/libexec/bin/python")
EXPECTED_APP = "enpire-f2-matched-runtime-rehearsal-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _override_map(config: dict[str, Any]) -> dict[str, str]:
    return {
        value.split("=", 1)[0]: value.split("=", 1)[1]
        for value in config["hydra_overrides"]
    }


def _normalized_arm(config: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(config)
    value.pop("experiment_id")
    value.pop("condition")
    overrides = _override_map(value)
    overrides.pop("algorithm.actor_weight_schedule.warmup_bc_weight")
    overrides.pop("algorithm.actor_weight_schedule.online_bc_weight")
    value["hydra_overrides"] = overrides
    value["scientific_values"].pop("warmup_bc_weight")
    value["scientific_values"].pop("online_bc_weight")
    return value


def validate_profile(profile_path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text())
    if profile.get("schema_version") != 1 or profile.get("app_name") != EXPECTED_APP:
        raise ValueError("F2 profile identity is invalid")
    if profile.get("function_name") != "run_fixed_rehearsal":
        raise ValueError("F2 function is not the fixed rehearsal endpoint")
    if profile.get("approval") != {
        "deployment_authorized": False,
        "gpu_execution_authorized": False,
        "promotion_authorized": False,
        "explicit_approval_required": True,
    }:
        raise ValueError("F2 approval boundary is invalid")

    runtime_raw = RUNTIME_CONTRACT.read_bytes()
    runtime = json.loads(runtime_raw)
    if _sha256(RUNTIME_CONTRACT) != profile["runtime_contract_sha256"]:
        raise ValueError("F0 runtime contract hash drifted")
    expected_resources = {
        "gpu": runtime["provider"]["gpu_request"],
        "gpu_count": runtime["provider"]["gpu_count"],
        "cpu_physical_cores": runtime["provider"]["cpu_physical_cores"],
        "memory_mib": runtime["provider"]["memory_mib"],
    }
    for key, expected in expected_resources.items():
        if profile["resources"].get(key) != expected:
            raise ValueError(f"F2 resource {key} differs from F0")
    if profile["resources"]["maximum_concurrent_functions"] != 1:
        raise ValueError("F2 must serialize all paid execution")

    billing = profile["billing"]
    rate = (
        Decimal(billing["gpu_usd_per_second"])
        + Decimal(profile["resources"]["cpu_physical_cores"])
        * Decimal(billing["cpu_physical_core_usd_per_second"])
        + Decimal(profile["resources"]["memory_mib"] / 1024)
        * Decimal(billing["memory_gib_usd_per_second"])
    )
    if rate * Decimal(3600) != Decimal(billing["selected_runtime_usd_per_hour"]):
        raise ValueError("F2 hourly price is internally inconsistent")
    ceiling = rate * Decimal(profile["resources"]["function_timeout_seconds"])
    if ceiling != Decimal(billing["maximum_runtime_resource_cost_usd"]):
        raise ValueError("F2 resource ceiling is internally inconsistent")
    if Decimal(billing["maximum_total_provider_cost_usd"]) < ceiling:
        raise ValueError("F2 provider ceiling is below the resource ceiling")

    control_path = ROOT / profile["fixed_sequence"][0]["profile"]
    candidate_path = ROOT / profile["fixed_sequence"][1]["profile"]
    control = load_d1_config(control_path)
    candidate = load_d1_config(candidate_path)
    expected_diff = {
        "online_bc_weight": (Decimal("2.5"), Decimal("2")),
        "warmup_bc_weight": (Decimal("7"), Decimal("5.6")),
    }
    observed_diff = {
        key: (Decimal(str(values[0])), Decimal(str(values[1])))
        for key, values in scientific_diff(control, candidate).items()
    }
    if observed_diff != expected_diff:
        raise ValueError(f"F2 scientific diff is not the intervention: {observed_diff}")
    if _normalized_arm(control) != _normalized_arm(candidate):
        raise ValueError("F2 arms differ outside identity labels and BC intervention")
    for arm in (control, candidate):
        overrides = _override_map(arm)
        required = {
            "actor.enable_offload": "false",
            "+weight_syncer.patch.transport_device": "cpu",
            "env.train.total_num_envs": "16",
            "env.train.rollout_epoch": "4",
            "env.eval.total_num_envs": "16",
            "env.eval.rollout_epoch": "16",
            "runner.resume_dir": "null",
            "runner.max_steps": "1",
            "runner.val_check_interval": "-1",
            "runner.save_interval": "1",
        }
        if any(overrides.get(key) != expected for key, expected in required.items()):
            raise ValueError("F2 arm does not preserve the bounded matched shape")
        if arm["evaluation"].get("executed_during_rehearsal") is not False:
            raise ValueError("F2 rehearsal must not execute policy evaluation")
        if arm["scientific_values"].get("calibration_only") is not True:
            raise ValueError("F2 arm is not marked calibration-only")
        for key, expected in runtime["execution"]["environment"].items():
            if arm["runtime_environment"].get(key) != expected:
                raise ValueError(f"F2 environment {key} differs from F0")

    return {"profile": profile, "runtime": runtime}


def _verify_modal_import(profile: dict[str, Any]) -> None:
    if not MODAL_PYTHON.is_file():
        raise ValueError("pinned Modal client interpreter is unavailable")
    imported = subprocess.run(
        [
            str(MODAL_PYTHON),
            "-c",
            "import modal,modal_f2_rehearsal; print(modal.__version__); print(modal_f2_rehearsal.APP_NAME)",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    ).stdout.splitlines()
    if imported != [profile["deployment"]["modal_client_version"], EXPECTED_APP]:
        raise ValueError("Modal client or F2 application identity mismatch")


def build_preflight(profile_path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    validated = validate_profile(profile_path)
    profile = validated["profile"]
    if _git("status", "--porcelain"):
        raise ValueError("F2 preflight requires a clean worktree")
    head = _git("rev-parse", "HEAD")
    _verify_modal_import(profile)
    source_hashes = {
        relative: _sha256(ROOT / relative) for relative in profile["source_paths"]
    }
    contracts = []
    for item in profile["fixed_sequence"]:
        arm = item["arm"]
        config_hash = _sha256(ROOT / item["profile"])
        command_hash = fingerprint(
            {
                "app": profile["app_name"],
                "function": profile["function_name"],
                "kind": item["kind"],
                "run_id": item.get("run_id"),
                "run_ids": item.get("run_ids"),
            }
        )
        contracts.append(
            RunContract.create(
                campaign_id="f2-matched-runtime-rehearsal-v1",
                trial_id=(item.get("run_id") or item["run_ids"][0] + "-chain"),
                arm_id=arm,
                parent_commit=head,
                candidate_commit=head,
                rlinf_commit="c90951a0c799a750cb5294ed10587c61cc2af8bf",
                config_hash=config_hash,
                command_hash=command_hash,
                seed=2026,
                reset_set_hash=hashlib.sha256(b"f2-evaluation-not-executed").hexdigest(),
                evaluator_version="f2-evaluation-forbidden-v1",
                max_wall_time_seconds=item["maximum_wall_time_seconds"],
                max_gpu_cost_usd=str(
                    Decimal(profile["billing"]["gpu_usd_per_second"])
                    * Decimal(item["maximum_wall_time_seconds"])
                ),
            ).to_dict()
        )
    return {
        "schema_version": 1,
        "status": "ready_for_explicit_approval",
        "claim_scope": profile["claim_scope"],
        "profile": profile,
        "profile_sha256": _sha256(profile_path),
        "head": head,
        "runtime_contract_sha256": profile["runtime_contract_sha256"],
        "source_hashes": source_hashes,
        "source_bundle_sha256": fingerprint(source_hashes),
        "contracts": contracts,
        "deployment": {
            "argv": [
                profile["deployment"]["modal_client"],
                "deploy",
                "--strategy",
                profile["deployment"]["strategy"],
                profile["deployment"]["application"],
            ],
            "run_argv": [
                profile["deployment"]["modal_client"],
                "run",
                profile["deployment"]["application"],
            ],
            "app": profile["app_name"],
            "function": profile["function_name"],
        },
        "required_live_checks": [
            "runtime and large-input hash verification",
            "Control full-shape step and checkpoint",
            "Candidate full-shape step and checkpoint",
            "only approved BC intervention differs",
            "resume counter continuity",
            "replay RNG state presence and restore marker",
            "measured end-to-end cost projection",
            "tagged provider billing",
            "scale to zero",
        ],
        "execution_authorized": False,
        "gpu_execution_authorized": False,
        "promotion_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-preflight", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_preflight:
            payload = build_preflight(args.profile.resolve())
            args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
            args.output.resolve().write_text(canonical_json(payload) + "\n")
            print(
                canonical_json(
                    {
                        "status": payload["status"],
                        "source_bundle_sha256": payload["source_bundle_sha256"],
                        "maximum_total_provider_cost_usd": payload["profile"]["billing"]["maximum_total_provider_cost_usd"],
                        "execution_authorized": False,
                    }
                )
            )
        else:
            profile = validate_profile(args.profile.resolve())["profile"]
            print(
                canonical_json(
                    {
                        "status": "valid_no_launch",
                        "profile_id": profile["profile_id"],
                        "maximum_total_provider_cost_usd": profile["billing"]["maximum_total_provider_cost_usd"],
                        "execution_authorized": False,
                    }
                )
            )
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"F2_PREFLIGHT_REJECTED={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
