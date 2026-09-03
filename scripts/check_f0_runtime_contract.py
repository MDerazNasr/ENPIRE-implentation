#!/usr/bin/env python3
"""Fail-closed verifier for the selected F0 matched runtime contract."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "results/runtime-qualification/f0/runtime-contract.json"
CONTRACT_ID = "enpire-matched-scientific-runtime-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path = DEFAULT_CONTRACT) -> dict[str, object]:
    contract = json.loads(path.read_text())
    errors: list[str] = []

    if contract.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if contract.get("contract_id") != CONTRACT_ID:
        errors.append("unexpected contract_id")
    if contract.get("status") != "selected_not_deployed":
        errors.append("F0 must not claim deployment")

    provider = contract.get("provider", {})
    expected_provider = {
        "name": "Modal",
        "gpu_request": "RTX-PRO-6000",
        "gpu_count": 1,
        "cpu_physical_cores": 16,
        "memory_mib": 98304,
        "maximum_concurrent_scientific_trials": 1,
    }
    for key, value in expected_provider.items():
        if provider.get(key) != value:
            errors.append(f"provider.{key} must be {value!r}")

    container = contract.get("container", {})
    expected_container = {
        "platform": "linux/amd64",
        "python": "3.11.14",
        "torch": "2.8.0+cu128",
        "cuda_toolkit": "12.8.1",
        "image_platform_digest": "sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7",
    }
    for key, value in expected_container.items():
        if container.get(key) != value:
            errors.append(f"container.{key} must be {value!r}")

    stack = contract.get("scientific_stack", {})
    expected_stack = {
        "rlinf_commit": "c90951a0c799a750cb5294ed10587c61cc2af8bf",
        "maniskill_commit": "33967b9e3ead1f841eec57cc9f31d0d8b8cf0907",
        "sapien": "3.0.1",
        "renderer_backend": "Mesa llvmpipe via Vulkan",
    }
    for key, value in expected_stack.items():
        if stack.get(key) != value:
            errors.append(f"scientific_stack.{key} must be {value!r}")

    execution = contract.get("execution", {})
    required_execution = {
        "multiprocess_adapter": True,
        "train_parallel_environments": 16,
        "train_rollout_epochs": 4,
        "eval_parallel_environments": 16,
        "eval_rollout_epochs": 16,
        "fixed_eval_trajectories": 256,
        "actor_offload": False,
        "weight_transport_device": "cpu",
    }
    for key, value in required_execution.items():
        if execution.get(key) != value:
            errors.append(f"execution.{key} must be {value!r}")

    resume = contract.get("resume", {})
    if resume.get("sidecar_required_for_any_resumed_run") is not True:
        errors.append("resume sidecar must be mandatory")
    if resume.get("missing_or_invalid_sidecar_behavior") != "fail before rollout or update":
        errors.append("resume must fail closed")
    if execution.get("environment", {}).get("QUALIA_RLT_RESUME_STATE") != "1":
        errors.append("resume environment opt-in must be enabled")

    expected_inputs = {
        "base_model": "0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f",
        "stage1_actor": "b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3",
        "norm_stats": "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd",
    }
    inputs = contract.get("inputs", {})
    for key, value in expected_inputs.items():
        if inputs.get(key, {}).get("sha256") != value:
            errors.append(f"inputs.{key}.sha256 mismatch")
    if inputs.get("dataset", {}).get("revision") != "2b92d5ef3fe274d30219130133f9e34c7ab91ebf":
        errors.append("dataset revision mismatch")

    harness = contract.get("harness", {})
    for relative, expected in harness.get("source_sha256", {}).items():
        local_path = ROOT / relative
        if not local_path.is_file():
            errors.append(f"missing harness source: {relative}")
        elif _sha256(local_path) != expected:
            errors.append(f"harness source hash mismatch: {relative}")

    norm = inputs.get("norm_stats", {})
    norm_path = ROOT / str(norm.get("path", ""))
    if not norm_path.is_file():
        errors.append("tracked norm-stat asset is missing")
    else:
        if norm_path.stat().st_size != norm.get("size_bytes"):
            errors.append("tracked norm-stat size mismatch")
        if _sha256(norm_path) != norm.get("sha256"):
            errors.append("tracked norm-stat hash mismatch")

    lifecycle = contract.get("provider_lifecycle", {})
    if lifecycle.get("paid_execution_authorized") is not False:
        errors.append("F0 cannot authorize paid execution")
    if lifecycle.get("pricing_revalidation") != "required before every paid approval and launch":
        errors.append("pricing must be revalidated before paid work")

    gate = contract.get("gate", {})
    if gate.get("passed") is not True or gate.get("same_runtime_required") is not True:
        errors.append("F0 gate must require the same runtime")
    if gate.get("control_runtime_contract_id") != CONTRACT_ID:
        errors.append("Control is not bound to the selected runtime")
    if gate.get("candidate_runtime_contract_id") != CONTRACT_ID:
        errors.append("Candidate is not bound to the selected runtime")

    if errors:
        raise ValueError("; ".join(errors))
    return {
        "contract_id": CONTRACT_ID,
        "contract_sha256": _sha256(path),
        "gate": "F0",
        "passed": True,
        "paid_execution_authorized": False,
    }


def main() -> int:
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CONTRACT
    try:
        print(json.dumps(verify(path), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"F0_RUNTIME_CONTRACT_REJECTED={exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
