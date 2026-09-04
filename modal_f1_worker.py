"""Deployed least-authority Modal implementation of the M7 worker RPC."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any

import modal


APP_NAME = "enpire-f1-worker-rpc-v1"
WORKER_ID = "modal-rtx-pro-6000-f1"
RUNTIME_CONTRACT_ID = "enpire-matched-scientific-runtime-v1"
PROJECT_ROOT = "/opt/qualia"
IMAGE_ENVIRONMENT = {"PYTHONPATH": PROJECT_ROOT}
WORKSPACE = "/workspace"
STATE_ROOT = Path(WORKSPACE) / "f1-worker-rpc"
RUNTIME_CONTRACT_PATH = Path(PROJECT_ROOT) / "runtime-contract.json"
GPU = "RTX-PRO-6000"
CPU_CORES = 16
MEMORY_MIB = 96 * 1024
PROBE_SECONDS = 15
GPU_PRICE_USD_PER_SECOND = 0.000842
CPU_PRICE_USD_PER_CORE_SECOND = 0.0000131
MEMORY_PRICE_USD_PER_GIB_SECOND = 0.00000222
IMAGE_PLATFORM_DIGEST = (
    "sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7"
)
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
F1_NAMESPACE_MARKER = "enpire-f1-minimal-supervisor-v1"


app = modal.App(
    APP_NAME,
    tags={"project": "enpire", "phase": "f1-worker-acceptance"},
)
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)

control_image = (
    modal.Image.debian_slim(python_version="3.11")
    .env(IMAGE_ENVIRONMENT)
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
    .add_local_file(
        "results/runtime-qualification/f0/runtime-contract.json",
        str(RUNTIME_CONTRACT_PATH),
        copy=True,
    )
)

scientific_image = (
    modal.Image.from_registry(
        f"nvidia/cuda@{IMAGE_PLATFORM_DIGEST}",
        add_python="3.11",
    )
    .entrypoint([])
    .env(IMAGE_ENVIRONMENT)
    .apt_install(
        "git",
        "git-lfs",
        "curl",
        "wget",
        "unzip",
        "build-essential",
        "cmake",
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender1",
        "libvulkan1=1.3.204.1-2",
        "vulkan-tools=1.3.204.0+dfsg1-1",
        "mesa-vulkan-drivers=23.2.1-1ubuntu3.1~22.04.4",
        "libegl1",
        "libgles2",
        "libglvnd0",
        "libx11-6",
        "libx11-xcb1",
        "libxcb1",
        "libgbm1",
    )
    .run_commands(
        "git clone https://github.com/RLinf/RLinf.git /opt/RLinf",
        f"cd /opt/RLinf && git checkout {RLINF_COMMIT}",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1",
        f"cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = {RLINF_COMMIT}",
    )
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
    .add_local_file(
        "results/runtime-qualification/f0/runtime-contract.json",
        str(RUNTIME_CONTRACT_PATH),
        copy=True,
    )
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _install_f1_supervisor_namespace() -> None:
    """Load required submodules without executing the broad package facade."""
    existing = sys.modules.get("supervisor")
    if existing is not None:
        if getattr(existing, "_enpire_f1_namespace", None) != F1_NAMESPACE_MARKER:
            raise RuntimeError("unexpected supervisor package was preloaded")
        return
    package = types.ModuleType("supervisor")
    package.__package__ = "supervisor"
    package.__path__ = [f"{PROJECT_ROOT}/supervisor"]
    package.__spec__ = ModuleSpec("supervisor", loader=None, is_package=True)
    package._enpire_f1_namespace = F1_NAMESPACE_MARKER
    sys.modules["supervisor"] = package


def _runtime_contract() -> tuple[dict[str, Any], str]:
    raw = RUNTIME_CONTRACT_PATH.read_bytes()
    contract = json.loads(raw)
    if contract.get("contract_id") != RUNTIME_CONTRACT_ID:
        raise RuntimeError("bundled runtime contract ID mismatch")
    return contract, _sha256(raw)


def _state_path(trial_id: str) -> Path:
    return STATE_ROOT / "state" / f"{trial_id}.json"


def _read_state(trial_id: str) -> dict[str, Any] | None:
    path = _state_path(trial_id)
    return json.loads(path.read_text()) if path.is_file() else None


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path(state["trial_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(_canonical(state) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "worker_id": WORKER_ID,
        "trial_id": state["trial_id"],
        "state": state["state"],
        "contract_hash": state["contract_hash"],
        "heartbeat_count": state["heartbeat_count"],
        "evidence_hash": state.get("evidence_hash"),
    }


def _require_trial(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"trial_id", "contract_hash"}:
        raise RuntimeError("trial payload fields are invalid")
    state = _read_state(payload["trial_id"])
    if state is None:
        raise RuntimeError("trial is not prepared")
    if state["contract_hash"] != payload["contract_hash"]:
        raise RuntimeError("trial contract hash mismatch")
    return state


def _poll(state: dict[str, Any]) -> dict[str, Any]:
    if state["state"] != "running":
        return state
    call = modal.FunctionCall.from_id(state["function_call_id"])
    try:
        result = call.get(timeout=0)
    except TimeoutError:
        return state
    except modal.exception.OutputExpiredError:
        state["state"] = "lost"
        state["finished_at"] = _timestamp()
        _write_state(state)
        return state
    if not isinstance(result, dict) or set(result) != {"evidence", "artifacts"}:
        raise RuntimeError("GPU probe returned a malformed result")
    from supervisor.contracts import TrialEvidence

    evidence = TrialEvidence.from_dict(result["evidence"])
    contract = state["contract"]
    for field in (
        "campaign_id",
        "trial_id",
        "arm_id",
        "parent_commit",
        "candidate_commit",
        "rlinf_commit",
        "config_hash",
        "command_hash",
        "seed",
        "reset_set_hash",
        "evaluator_version",
    ):
        if getattr(evidence, field) != contract[field]:
            raise RuntimeError(f"GPU probe evidence {field} mismatch")
    if evidence.elapsed_seconds > contract["max_wall_time_seconds"]:
        raise RuntimeError("GPU probe evidence exceeded wall-time contract")
    artifacts = result["artifacts"]
    if not isinstance(artifacts, dict):
        raise RuntimeError("GPU probe artifacts are malformed")
    expected = {item["artifact_id"]: item for item in evidence.to_dict()["artifacts"]}
    if set(artifacts) != set(expected):
        raise RuntimeError("GPU probe artifact inventory mismatch")
    for artifact_id, encoded in artifacts.items():
        raw = base64.b64decode(encoded, validate=True)
        item = expected[artifact_id]
        if len(raw) != item["size_bytes"] or _sha256(raw) != item["sha256"]:
            raise RuntimeError("GPU probe artifact digest mismatch")
    state["evidence"] = evidence.to_dict()
    state["evidence_hash"] = evidence.fingerprint()
    state["artifacts"] = artifacts
    state["state"] = "completed" if evidence.status.value == "complete" else "failed"
    state["finished_at"] = _timestamp()
    _write_state(state)
    return state


@app.function(
    image=scientific_image,
    gpu=GPU,
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    timeout=300,
    volumes={WORKSPACE: workspace},
)
def bounded_gpu_probe(contract_value: dict[str, Any], runtime_hash: str) -> dict[str, Any]:
    """Run only the baked-in bounded CUDA/renderer telemetry probe."""
    _install_f1_supervisor_namespace()
    from supervisor.contracts import ArtifactRef, TrialEvidence
    from supervisor.workers import RunContract

    runtime, expected_runtime_hash = _runtime_contract()
    if runtime_hash != expected_runtime_hash:
        raise RuntimeError("runtime contract hash mismatch")
    contract = RunContract.from_dict(contract_value)
    if contract.rlinf_commit != RLINF_COMMIT:
        raise RuntimeError("RLinf contract mismatch")
    rlinf_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd="/opt/RLinf", text=True
    ).strip()
    if rlinf_revision != RLINF_COMMIT:
        raise RuntimeError("RLinf checkout mismatch")
    environment = {
        **os.environ,
        "VK_ICD_FILENAMES": runtime["scientific_stack"]["vulkan_icd"],
    }
    vulkan = subprocess.run(
        ["vulkaninfo", "--summary"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )
    if vulkan.returncode != 0 or "llvmpipe" not in vulkan.stdout.lower():
        raise RuntimeError("Mesa llvmpipe Vulkan gate failed")

    started_at = _timestamp()
    probe_source = r'''
import json
import platform
import subprocess
import time
from importlib.metadata import version

import torch

started = time.monotonic()
samples = []
matrix = torch.randn((4096, 4096), device="cuda", dtype=torch.float16)
while time.monotonic() - started < PROBE_SECONDS:
    matrix = matrix @ matrix
    matrix = matrix / matrix.abs().amax().clamp_min(1)
    torch.cuda.synchronize()
    query = subprocess.check_output([
        "nvidia-smi",
        "--query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ], text=True).strip()
    timestamp, name, uuid, total, used, utilization, power = [
        item.strip() for item in query.split(",", 6)
    ]
    samples.append({
        "timestamp": timestamp,
        "gpu_name": name,
        "gpu_uuid": uuid,
        "memory_total_mib": float(total),
        "memory_used_mib": float(used),
        "utilization_gpu_percent": float(utilization),
        "power_draw_watts": float(power),
    })
properties = torch.cuda.get_device_properties(0)
print(json.dumps({
    "python": platform.python_version(),
    "torch": torch.__version__,
    "cuda_runtime": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "gpu_name": properties.name,
    "gpu_memory_bytes": properties.total_memory,
    "sapien": version("sapien"),
    "maniskill": version("mani-skill"),
    "elapsed_seconds": time.monotonic() - started,
    "samples": samples,
}, sort_keys=True, separators=(",", ":")))
'''.replace("PROBE_SECONDS", repr(PROBE_SECONDS))
    probe_process = subprocess.run(
        ["/opt/RLinf/.venv/bin/python", "-c", probe_source],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=PROBE_SECONDS + 60,
        check=False,
    )
    if probe_process.returncode != 0:
        raise RuntimeError(f"CUDA probe failed: {probe_process.stderr[-1000:]}")
    probe = json.loads(probe_process.stdout)
    if probe["python"] != runtime["container"]["python"]:
        raise RuntimeError(f"Python version mismatch: {probe['python']}")
    if probe["torch"] != runtime["container"]["torch"]:
        raise RuntimeError(f"Torch version mismatch: {probe['torch']}")
    if not probe["cuda_available"]:
        raise RuntimeError("CUDA is unavailable")
    if "RTX PRO 6000" not in probe["gpu_name"]:
        raise RuntimeError(f"unexpected GPU: {probe['gpu_name']}")
    if probe["gpu_memory_bytes"] < runtime["provider"]["minimum_gpu_memory_bytes"]:
        raise RuntimeError("GPU memory is below the runtime contract")
    if probe["sapien"] != runtime["scientific_stack"]["sapien"]:
        raise RuntimeError("SAPIEN version mismatch")
    if probe["maniskill"] != "3.0.0b22":
        raise RuntimeError("ManiSkill version mismatch")
    samples = probe["samples"]
    elapsed = probe["elapsed_seconds"]
    finished_at = _timestamp()
    estimated_cost = elapsed * (
        GPU_PRICE_USD_PER_SECOND
        + CPU_CORES * CPU_PRICE_USD_PER_CORE_SECOND
        + 96 * MEMORY_PRICE_USD_PER_GIB_SECOND
    )
    telemetry = {
        "schema_version": 1,
        "runtime_contract_id": RUNTIME_CONTRACT_ID,
        "runtime_contract_sha256": runtime_hash,
        "image_platform_digest": IMAGE_PLATFORM_DIGEST,
        "python": probe["python"],
        "torch": probe["torch"],
        "cuda_runtime": probe["cuda_runtime"],
        "rlinf_commit": rlinf_revision,
        "sapien": probe["sapien"],
        "maniskill": probe["maniskill"],
        "samples": samples,
    }
    cost = {
        "schema_version": 1,
        "kind": "rate_times_measured_function_runtime_estimate",
        "elapsed_seconds": elapsed,
        "estimated_provider_cost_usd": estimated_cost,
        "rates_checked_at": runtime["provider_lifecycle"]["pricing_checked_at"],
        "actual_billing_record": "must be reconciled by the coordinator",
    }
    log = {
        "probe": "bounded CUDA matrix and llvmpipe Vulkan acceptance",
        "started_at": started_at,
        "finished_at": finished_at,
        "sample_count": len(samples),
        "vulkan_summary_sha256": _sha256(vulkan.stdout.encode("utf-8")),
    }
    contents = {
        "gpu-telemetry": _canonical(telemetry) + b"\n",
        "provider-cost-estimate": _canonical(cost) + b"\n",
        "probe-log": _canonical(log) + b"\n",
    }
    refs = [
        ArtifactRef.from_dict(
            {
                "artifact_id": artifact_id,
                "kind": artifact_id,
                "uri": f"worker://{contract.trial_id}/{artifact_id}",
                "sha256": _sha256(content),
                "size_bytes": len(content),
            },
            f"probe artifact {artifact_id}",
        )
        for artifact_id, content in sorted(contents.items())
    ]
    evidence = TrialEvidence.from_dict(
        {
            "schema_version": 1,
            "campaign_id": contract.campaign_id,
            "trial_id": contract.trial_id,
            "arm_id": contract.arm_id,
            "parent_commit": contract.parent_commit,
            "candidate_commit": contract.candidate_commit,
            "rlinf_commit": contract.rlinf_commit,
            "config_hash": contract.config_hash,
            "command_hash": contract.command_hash,
            "seed": contract.seed,
            "reset_set_hash": contract.reset_set_hash,
            "evaluator_version": contract.evaluator_version,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "complete",
            "exit_code": 0,
            "elapsed_seconds": elapsed,
            "gpu_cost_usd": format(estimated_cost, ".12f"),
            "llm_cost_usd": "0",
            "metrics": {
                "gpu_peak_utilization_percent": max(
                    item["utilization_gpu_percent"] for item in samples
                ),
                "gpu_peak_memory_used_mib": max(
                    item["memory_used_mib"] for item in samples
                ),
            },
            "metric_errors": [],
            "artifacts": [item.to_dict() for item in refs],
        }
    )
    return {
        "evidence": evidence.to_dict(),
        "artifacts": {
            artifact_id: base64.b64encode(content).decode("ascii")
            for artifact_id, content in contents.items()
        },
    }


@app.function(
    image=control_image,
    cpu=0.25,
    memory=512,
    timeout=60,
    max_containers=1,
    volumes={WORKSPACE: workspace},
)
def rpc(request_value: dict[str, Any]) -> dict[str, Any]:
    """Handle exactly one allowlisted lifecycle operation."""
    _install_f1_supervisor_namespace()
    from supervisor.canonical import fingerprint
    from supervisor.modal_worker_rpc import WorkerRpcRequest
    from supervisor.workers import RunContract

    workspace.reload()
    runtime, runtime_hash = _runtime_contract()
    request = WorkerRpcRequest.from_dict(request_value)
    if request.worker_id != WORKER_ID:
        raise RuntimeError("worker identity mismatch")
    if (
        request.runtime_contract_id != RUNTIME_CONTRACT_ID
        or request.runtime_contract_sha256 != runtime_hash
    ):
        raise RuntimeError("runtime identity mismatch")
    action = request.action
    payload = request.payload

    if action == "prepare":
        if set(payload) != {"contract"}:
            raise RuntimeError("prepare payload fields are invalid")
        contract = RunContract.from_dict(payload["contract"])
        if contract.rlinf_commit != runtime["scientific_stack"]["rlinf_commit"]:
            raise RuntimeError("prepare RLinf identity mismatch")
        expected_command_hash = fingerprint(
            {
                "app": APP_NAME,
                "function": "bounded_gpu_probe",
                "operation": "bounded CUDA matrix and llvmpipe Vulkan acceptance",
                "probe_seconds": PROBE_SECONDS,
            }
        )
        if (
            contract.campaign_id != "f1-worker-rpc-acceptance-v1"
            or contract.arm_id != "f1-engineering-only"
            or contract.trial_id
            not in {"f1-complete-probe", "f1-active-cancel-probe"}
            or contract.parent_commit != contract.candidate_commit
            or contract.config_hash != runtime_hash
            or contract.command_hash != expected_command_hash
            or contract.seed != 2026
            or contract.reset_set_hash
            != hashlib.sha256(b"f1-no-scientific-reset-set").hexdigest()
            or contract.evaluator_version != "f1-evaluation-forbidden-v1"
            or contract.max_wall_time_seconds != 300
            or float(contract.max_gpu_cost_usd) > 0.379416
        ):
            raise RuntimeError("prepare contract is outside the F1 acceptance profile")
        state = _read_state(contract.trial_id)
        contract_hash = contract.fingerprint()
        if state is None:
            state = {
                "schema_version": 1,
                "trial_id": contract.trial_id,
                "contract": contract.to_dict(),
                "contract_hash": contract_hash,
                "runtime_contract_sha256": runtime_hash,
                "state": "prepared",
                "heartbeat_count": 0,
                "evidence_hash": None,
                "function_call_id": None,
                "created_at": _timestamp(),
            }
            _write_state(state)
        elif state["contract_hash"] != contract_hash:
            raise RuntimeError("trial ID is already bound to another contract")
        result = {"snapshot": _snapshot(state)}
    elif action == "launch":
        state = _require_trial(payload)
        if state["state"] == "prepared":
            call = bounded_gpu_probe.spawn(state["contract"], runtime_hash)
            state["function_call_id"] = call.object_id
            state["state"] = "running"
            state["launched_at"] = _timestamp()
            _write_state(state)
        result = {"snapshot": _snapshot(state)}
    elif action in {"status", "heartbeat"}:
        state = _poll(_require_trial(payload))
        if action == "heartbeat" and state["state"] in {"prepared", "running"}:
            state["heartbeat_count"] += 1
            _write_state(state)
        result = {"snapshot": _snapshot(state)}
    elif action == "cancel":
        state = _require_trial(payload)
        if state["state"] == "running":
            modal.FunctionCall.from_id(state["function_call_id"]).cancel(
                terminate_containers=True
            )
            state["state"] = "cancelled"
            state["finished_at"] = _timestamp()
            _write_state(state)
        elif state["state"] == "prepared":
            state["state"] = "cancelled"
            state["finished_at"] = _timestamp()
            _write_state(state)
        result = {"snapshot": _snapshot(state)}
    elif action == "fetch_evidence":
        state = _poll(_require_trial(payload))
        if state["state"] not in {"completed", "failed"} or "evidence" not in state:
            raise RuntimeError("terminal evidence is unavailable")
        result = {"evidence": state["evidence"]}
    elif action == "fetch_artifact":
        expected = {"trial_id", "contract_hash", "artifact_id", "offset", "length"}
        if set(payload) != expected:
            raise RuntimeError("artifact payload fields are invalid")
        state = _read_state(payload["trial_id"])
        if state is None or state["contract_hash"] != payload["contract_hash"]:
            raise RuntimeError("artifact trial identity mismatch")
        if state["state"] not in {"completed", "failed"}:
            raise RuntimeError("artifact is unavailable before terminal evidence")
        artifact_id = payload["artifact_id"]
        encoded = state.get("artifacts", {}).get(artifact_id)
        if encoded is None:
            raise RuntimeError("artifact is not in the terminal inventory")
        raw = base64.b64decode(encoded, validate=True)
        offset = payload["offset"]
        length = payload["length"]
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(length, bool)
            or not isinstance(length, int)
            or length < 1
            or length > 262144
            or offset >= len(raw)
        ):
            raise RuntimeError("artifact byte range is invalid")
        result = {
            "artifact_chunk": {
                "artifact_id": artifact_id,
                "offset": offset,
                "total_size_bytes": len(raw),
                "sha256": _sha256(raw),
                "data_b64": base64.b64encode(raw[offset : offset + length]).decode(
                    "ascii"
                ),
            }
        }
    else:
        raise RuntimeError("unsupported worker RPC action")

    workspace.commit()
    return {"schema_version": 1, "request_id": request.request_id, "result": result}
