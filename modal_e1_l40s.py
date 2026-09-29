"""Bounded E1 development-checkpoint evaluation on one Modal L40S.

Each invocation accepts one frozen checkpoint step, downloads only that
checkpoint's evaluation weight file at its exact S3 version, verifies its
recorded size and SHA-256, and runs the existing evaluation-only entrypoint.
No retry, training, final-reset access, or checkpoint selection is available.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import modal


APP_NAME = "enpire-g0-e1-l40s-evaluation-v1"
GPU = "L40S"
CPU_CORES = 16
MEMORY_MIB = 96 * 1024
FUNCTION_TIMEOUT_SECONDS = 3600
PROJECT_ROOT = "/opt/qualia"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/workspace"
RESULTS_ROOT = f"{WORKSPACE}/e1-l40s-results"
NORM_STATS = f"{PROJECT_ROOT}/norm_stats.json"
DEVELOPMENT_RESETS = f"{PROJECT_ROOT}/development-resets.json"
DEVELOPMENT_RESET_FINGERPRINT = (
    "e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161"
)
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
BUCKET = "enpire-g0-evaluator-evidencebucket-atlpylr0fwjq"
PREFIX = "runs/g0-e1-stage1-seed2026-v1/checkpoints"
GPU_PRICE_USD_PER_HOUR = "1.951200"
AWS_ENVIRONMENT = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

CHECKPOINTS = {
    250: {
        "size": 10015912662,
        "sha256": "f95c7112bbd25a714e477a448273b16fa564c8e8c184a5f765b1cbfc8d23a211",
        "version_id": "J8K7_nDRR7zh17ZbbQmmUYc4Yq3_GpSR",
    },
    500: {
        "size": 10015912662,
        "sha256": "e98bdd8c5b01c84a72e1018e57cb664547859c172eb402d9b4865292835e82b0",
        "version_id": "LWi.kYdNvi_beY7TjYgI0cKwmWZ.N6fR",
    },
    1000: {
        "size": 10015912662,
        "sha256": "72a05acadba9602d18ba8a8c43458ec7d76f4c8514fb83a1ca86fa7343850d61",
        "version_id": "zjDLRQXH7Xe1o_y5pBAYG1Fx_gN21ytp",
    },
    2000: {
        "size": 10015912662,
        "sha256": "4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146",
        "version_id": "LvdNrl8pPsbD6s9tdJ8.__.1V2B00077",
    },
}


def _required_aws_secret() -> modal.Secret:
    missing = [name for name in AWS_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        raise RuntimeError("temporary read-only AWS credentials are required")
    return modal.Secret.from_dict({name: os.environ[name] for name in AWS_ENVIRONMENT})


app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "g0-e1"})
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
    )
    .entrypoint([])
    .env({"PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}"})
    .apt_install(
        "git", "git-lfs", "curl", "wget", "unzip", "build-essential", "cmake",
        "libgl1", "libglib2.0-0", "libsm6", "libxext6", "libxrender1",
        "libvulkan1", "vulkan-tools", "mesa-vulkan-drivers", "libegl1",
        "libgles2", "libglvnd0", "libx11-6", "libx11-xcb1", "libxcb1",
        "libxext6", "libgbm1",
    )
    .run_commands(
        "git clone https://github.com/RLinf/RLinf.git /opt/RLinf",
        f"cd /opt/RLinf && git checkout {RLINF_COMMIT}",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1 boto3",
        f"cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = {RLINF_COMMIT}",
    )
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "configs/d1/assets/maniskill_peginsertionside_joint.norm_stats.json",
        NORM_STATS,
        copy=True,
    )
    .add_local_file(
        "results/agent-supervisor/g0/reset-sets/development.json",
        DEVELOPMENT_RESETS,
        copy=True,
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(step: int, destination: Path) -> dict[str, object]:
    import boto3

    spec = CHECKPOINTS[step]
    key = f"{PREFIX}/global_step_{step}/actor/model_state_dict/full_weights.pt"
    destination.parent.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    boto3.client("s3", region_name="us-west-2").download_file(
        BUCKET,
        key,
        str(destination),
        ExtraArgs={"VersionId": str(spec["version_id"])},
    )
    size = destination.stat().st_size
    digest = _sha256(destination)
    if size != spec["size"] or digest != spec["sha256"]:
        raise RuntimeError("downloaded checkpoint weight identity mismatch")
    return {
        "bucket": BUCKET,
        "key": key,
        "version_id": spec["version_id"],
        "size_bytes": size,
        "sha256": digest,
        "elapsed_seconds": time.monotonic() - started,
    }


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    ephemeral_disk=80 * 1024,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    retries=0,
    single_use_containers=True,
    secrets=[_required_aws_secret()],
    volumes={WORKSPACE: workspace},
)
def evaluate(step: int) -> dict[str, object]:
    if step not in CHECKPOINTS:
        raise ValueError("step must be exactly one of 250, 500, 1000, or 2000")
    checkpoint = Path(f"/tmp/e1-checkpoint-{step}/actor/model_state_dict/full_weights.pt")
    download = _download(step, checkpoint)
    run_id = f"g0-e1-l40s-step-{step}-v1"
    run_dir = Path(RESULTS_ROOT) / "d1" / run_id
    if run_dir.exists():
        raise RuntimeError("create-only evaluation destination already exists")
    environment = {
        **os.environ,
        "RLINF_HOME": RLINF_HOME,
        "QUALIA_PROJECT_ROOT": PROJECT_ROOT,
        "STAGE1_CHECKPOINT": str(checkpoint.parents[1]),
        "NORM_STATS_PATH": NORM_STATS,
        "DEVELOPMENT_RESET_PATH": DEVELOPMENT_RESETS,
        "DEVELOPMENT_RESET_SHA256": DEVELOPMENT_RESET_FINGERPRINT,
        "WANDB_PROJECT": "qualia-rlt-d1",
        "WANDB_MODE": "offline",
        "WANDB_DIR": f"{WORKSPACE}/wandb",
        "HF_HOME": f"{WORKSPACE}/cache/huggingface",
        "HF_DATASETS_CACHE": f"{WORKSPACE}/cache/huggingface/datasets",
        "GPU_HOURLY_PRICE_USD": GPU_PRICE_USD_PER_HOUR,
        "PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}",
        "QUALIA_MODAL_THREADS_PER_WORKER": "1",
        "PYTHONUNBUFFERED": "1",
    }
    started = time.monotonic()
    process = subprocess.run(
        [
            f"{RLINF_HOME}/.venv/bin/python",
            "-m", "agent.d1_launcher",
            "--config", f"{PROJECT_ROOT}/configs/d1/e1_checkpoint_evaluation.yaml",
            "--results-root", RESULTS_ROOT,
            "--run-id", run_id,
            "--execute", "--acknowledge-paid-run",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
    receipt = {
        "schema_version": 1,
        "step": step,
        "gpu": GPU,
        "download": download,
        "elapsed_seconds": time.monotonic() - started,
        "exit_code": process.returncode,
        "manifest": manifest,
        "claim_scope": "development checkpoint evaluation only; no selection or promotion",
    }
    receipt_path = Path(RESULTS_ROOT) / f"step-{step}-terminal.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    workspace.commit()
    if process.returncode:
        raise RuntimeError(f"checkpoint evaluation failed with exit {process.returncode}")
    return receipt


@app.local_entrypoint()
def main(step: int):
    if step not in CHECKPOINTS:
        raise ValueError("--step must be 250, 500, 1000, or 2000")
    print(json.dumps(evaluate.remote(step), indent=2, sort_keys=True))
