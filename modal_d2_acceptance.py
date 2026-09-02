"""Paid, non-promotable Modal worker for the D2 attachment acceptance gate."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import modal


APP_NAME = "enpire-d2-paid-acceptance"
GPU = "RTX-PRO-6000"
CPU_CORES = 16
MEMORY_MIB = 96 * 1024
HARD_TIMEOUT_SECONDS = 1800
PROJECT_ROOT = "/opt/qualia"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/private/tmp/enpire-d2-paid-acceptance"
EXPECTED_RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
EXPECTED_ACTOR_SIZE = 10_015_912_759
EXPECTED_ACTOR_SHA256 = (
    "b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3"
)
EXPECTED_NORM_SHA256 = (
    "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
)
GPU_PRICE_USD_PER_HOUR = "3.0312"
MAX_GPU_COST_USD = Decimal("1.5156")
RESULT_MARKER = "D2_MODAL_ACCEPTANCE_RESULT="


app = modal.App(APP_NAME)
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .entrypoint([])
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
        "libvulkan1",
        "vulkan-tools",
        "mesa-vulkan-drivers",
        "libegl1",
        "libgles2",
        "libglvnd0",
        "libx11-6",
        "libx11-xcb1",
        "libxcb1",
        "libxext6",
        "libgbm1",
    )
    .run_commands(
        "git clone https://github.com/RLinf/RLinf.git /opt/RLinf",
        f"cd /opt/RLinf && git checkout {EXPECTED_RLINF_COMMIT}",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1",
        f"cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = {EXPECTED_RLINF_COMMIT}",
    )
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "modal_d2_acceptance.py",
        f"{PROJECT_ROOT}/modal_d2_acceptance.py",
        copy=True,
    )
    .add_local_file(
        "configs/d1/assets/maniskill_peginsertionside_joint.norm_stats.json",
        f"{PROJECT_ROOT}/norm_stats.json",
        copy=True,
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_runtime(request) -> dict[str, object]:
    for relative, expected in request.source_hashes.items():
        path = Path(PROJECT_ROOT) / relative
        if not path.is_file() or _sha256(path) != expected:
            raise RuntimeError(f"runtime source hash mismatch: {relative}")
    if request.source_bundle_hash != __import__(
        "supervisor.canonical", fromlist=["fingerprint"]
    ).fingerprint(dict(request.source_hashes)):
        raise RuntimeError("runtime source bundle hash mismatch")
    actor = (
        Path(WORKSPACE)
        / "checkpoints/stage1-step-500-actor/model_state_dict/full_weights.pt"
    )
    if not actor.is_file() or actor.stat().st_size != EXPECTED_ACTOR_SIZE:
        raise RuntimeError("Stage-1 actor is missing or has the wrong size")
    if _sha256(actor) != EXPECTED_ACTOR_SHA256:
        raise RuntimeError("Stage-1 actor hash mismatch")
    norm = Path(PROJECT_ROOT) / "norm_stats.json"
    if _sha256(norm) != EXPECTED_NORM_SHA256:
        raise RuntimeError("norm-stat hash mismatch")
    revision = subprocess.check_output(
        ["git", "-C", RLINF_HOME, "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != EXPECTED_RLINF_COMMIT:
        raise RuntimeError("RLinf revision mismatch")
    contract = request.plan["contract"]
    if Decimal(contract["max_gpu_cost_usd"]) > MAX_GPU_COST_USD:
        raise RuntimeError("run contract GPU cap exceeds the D2 acceptance ceiling")
    if contract["max_wall_time_seconds"] > HARD_TIMEOUT_SECONDS:
        raise RuntimeError("run contract wall time exceeds the Modal hard timeout")
    return {
        "actor_sha256": EXPECTED_ACTOR_SHA256,
        "actor_size_bytes": EXPECTED_ACTOR_SIZE,
        "norm_stats_sha256": EXPECTED_NORM_SHA256,
        "rlinf_commit": revision,
        "source_bundle_hash": request.source_bundle_hash,
    }


def _inventory(paths: list[Path]) -> list[dict[str, object]]:
    records = []
    for root in paths:
        if not root.exists():
            continue
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for path in sorted(files):
            records.append(
                {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return records


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    timeout=HARD_TIMEOUT_SECONDS,
    volumes={WORKSPACE: workspace},
)
def execute(payload_b64: str, expected_profile: str) -> dict[str, object]:
    sys.path.insert(0, PROJECT_ROOT)
    from supervisor.canonical import canonical_json
    from supervisor.modal_acceptance import ModalAcceptanceRequest

    request = ModalAcceptanceRequest.from_dict(
        json.loads(base64.b64decode(payload_b64, validate=True))
    )
    verified = _verify_runtime(request)
    plan = request.plan
    config_path = Path(plan["derived_config_path"])
    results_root = Path(plan["results_root"])
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() or Path(plan["manifest_path"]).exists():
        raise RuntimeError("remote acceptance paths already exist")
    config_path.write_bytes(base64.b64decode(request.derived_config_b64, validate=True))
    execution = list(plan["execution_argv"])
    if execution[1:3] != ["-m", "agent.d1_launcher"]:
        raise RuntimeError("remote execution argv is not the D1 launcher")
    execution[0] = f"{RLINF_HOME}/.venv/bin/python"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    environment = {
        **os.environ,
        **config["runtime_environment"],
        "GPU_HOURLY_PRICE_USD": GPU_PRICE_USD_PER_HOUR,
        "PYTHONUNBUFFERED": "1",
    }
    completed = subprocess.run(execution, cwd=PROJECT_ROOT, env=environment)
    manifest_path = Path(plan["manifest_path"])
    log_path = Path(plan["log_path"])
    if not manifest_path.is_file() or not log_path.is_file():
        raise RuntimeError("D1 launcher did not produce terminal artifacts")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["project_commit"] = plan["contract"]["candidate_commit"]
    manifest["modal_attestation"] = {
        "request_hash": request.fingerprint(),
        "expected_profile": expected_profile,
        "runtime": verified,
    }
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    wandb_dir = Path(config["runtime_environment"]["WANDB_DIR"])
    inventory = _inventory([manifest_path.parent, wandb_dir])
    manifest_bytes = manifest_path.read_bytes()
    log_bytes = log_path.read_bytes()
    workspace.commit()
    return {
        "schema_version": 1,
        "request_hash": request.fingerprint(),
        "status": manifest["status"],
        "return_code": int(manifest["exit_code"]),
        "manifest_b64": base64.b64encode(manifest_bytes).decode("ascii"),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "log_b64": base64.b64encode(log_bytes).decode("ascii"),
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "artifact_inventory": inventory,
        "worker": {
            "provider": "Modal",
            "expected_profile": expected_profile,
            "app_name": APP_NAME,
            "hostname": platform.node(),
            "gpu": GPU,
            "cpu_physical_cores": CPU_CORES,
            "memory_mib": MEMORY_MIB,
        },
    }


@app.local_entrypoint()
def main(payload_b64: str, expected_profile: str) -> None:
    result = execute.remote(payload_b64, expected_profile)
    encoded = base64.b64encode(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    print(f"{RESULT_MARKER}{encoded}")
