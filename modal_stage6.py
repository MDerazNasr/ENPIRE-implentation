"""Reproducible Modal gates and Candidate-C launcher for Stage 6.

The full Candidate is intentionally a separate function from the integration
gate and smoke.  Run it only after the smoke's measured projection is under
Modal's 24-hour limit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import modal


APP_NAME = "enpire-stage6-modal-multiprocess"
GPU = "RTX-PRO-6000"
PROJECT_ROOT = "/opt/qualia"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/workspace"
ACTOR = f"{WORKSPACE}/checkpoints/stage1-step-500-actor"
NORM_STATS = f"{PROJECT_ROOT}/norm_stats.json"
EXPECTED_ACTOR_SIZE = 10_015_912_759
EXPECTED_ACTOR_SHA256 = (
    "b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3"
)
EXPECTED_NORM_SHA256 = (
    "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
)


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
        "cd /opt/RLinf && git checkout c90951a0c799a750cb5294ed10587c61cc2af8bf",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1",
        "cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = c90951a0c799a750cb5294ed10587c61cc2af8bf",
    )
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "tmp/fresh-chain-20260807/norm_stats.json",
        NORM_STATS,
        copy=True,
    )
    .add_local_file(
        "tmp/fresh-chain-20260807/evidence/stage5d-control-b-complete/d1_runs.jsonl",
        f"{PROJECT_ROOT}/control_d1_runs.jsonl",
        copy=True,
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_environment() -> dict[str, str]:
    return {
        **os.environ,
        "RLINF_HOME": RLINF_HOME,
        "MODAL_ADAPTER_ROOT": PROJECT_ROOT,
        "STAGE1_CHECKPOINT": ACTOR,
        "NORM_STATS_PATH": NORM_STATS,
        "WANDB_PROJECT": "qualia-rlt-d1",
        "WANDB_MODE": "offline",
        "WANDB_DIR": f"{WORKSPACE}/wandb",
        "HF_HOME": f"{WORKSPACE}/cache/huggingface",
        "HF_DATASETS_CACHE": f"{WORKSPACE}/cache/huggingface/datasets",
        "D1_SEED": "2026",
        "GPU_HOURLY_PRICE_USD": "3.03",
        "EMBODIED_PATH": f"{RLINF_HOME}/examples/embodiment",
        "PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}",
        "PYTHONUNBUFFERED": "1",
        "QUALIA_MODAL_MULTIPROCESS": "1",
        "QUALIA_MODAL_MP_START_METHOD": "spawn",
        "QUALIA_MODAL_RENDER_DEVICE": "pci:0000:00:00.0",
        "QUALIA_MODAL_VULKAN_ICD": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "QUALIA_MODAL_THREADS_PER_WORKER": "1",
        "VK_ICD_FILENAMES": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "LP_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }


def _verify_inputs() -> dict[str, object]:
    actor_file = Path(ACTOR) / "model_state_dict/full_weights.pt"
    if not actor_file.is_file():
        raise FileNotFoundError(f"Stage-1 actor missing: {actor_file}")
    if actor_file.stat().st_size != EXPECTED_ACTOR_SIZE:
        raise RuntimeError(f"Stage-1 actor size mismatch: {actor_file.stat().st_size}")
    actor_sha = _sha256(actor_file)
    if actor_sha != EXPECTED_ACTOR_SHA256:
        raise RuntimeError(f"Stage-1 actor SHA mismatch: {actor_sha}")
    norm_sha = _sha256(Path(NORM_STATS))
    if norm_sha != EXPECTED_NORM_SHA256:
        raise RuntimeError(f"norm-stats SHA mismatch: {norm_sha}")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=RLINF_HOME, text=True
    ).strip()
    if revision != "c90951a0c799a750cb5294ed10587c61cc2af8bf":
        raise RuntimeError(f"RLinf revision mismatch: {revision}")
    return {
        "actor_size": EXPECTED_ACTOR_SIZE,
        "actor_sha256": actor_sha,
        "norm_stats_sha256": norm_sha,
        "rlinf_commit": revision,
    }


def _prepare_results() -> Path:
    results = Path(WORKSPACE) / "results"
    results.mkdir(parents=True, exist_ok=True)
    ledger = results / "d1_runs.jsonl"
    if not ledger.exists():
        ledger.write_bytes(Path(f"{PROJECT_ROOT}/control_d1_runs.jsonl").read_bytes())
    return results


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=65536,
    timeout=60 * 60,
    volumes={WORKSPACE: workspace},
)
def adapter_gate() -> dict[str, object]:
    inputs = _verify_inputs()
    completed = subprocess.run(
        [f"{RLINF_HOME}/.venv/bin/python", f"{PROJECT_ROOT}/scripts/modal_adapter_gate.py"],
        env=_runtime_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout, flush=True)
    if completed.returncode != 0:
        raise RuntimeError(f"adapter gate failed with exit {completed.returncode}")
    marker = next(
        line.split("=", 1)[1]
        for line in completed.stdout.splitlines()
        if line.startswith("QUALIA_MODAL_ADAPTER_GATE=")
    )
    result = json.loads(marker)
    result["inputs"] = inputs
    return result


def _run_profile(profile: str, run_id: str) -> int:
    _verify_inputs()
    results = _prepare_results()
    command = [
        f"{RLINF_HOME}/.venv/bin/python",
        "-m",
        "agent.d1_launcher",
        "--config",
        f"{PROJECT_ROOT}/configs/d1/{profile}",
        "--results-root",
        str(results),
        "--run-id",
        run_id,
        "--execute",
        "--acknowledge-paid-run",
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=_runtime_environment())
    workspace.commit()
    if completed.returncode != 0:
        raise RuntimeError(f"RLinf profile failed with exit {completed.returncode}")
    return completed.returncode


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=98304,
    timeout=60 * 60 * 4,
    volumes={WORKSPACE: workspace},
)
def smoke() -> int:
    return _run_profile(
        "stage2_6_candidate_modal_multiprocess_smoke.yaml",
        "stage6-candidate-c-modal-multiprocess-smoke-seed2026-r3",
    )


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=131072,
    timeout=60 * 60 * 24,
    volumes={WORKSPACE: workspace},
)
def candidate() -> int:
    return _run_profile(
        "stage2_6_candidate_modal_multiprocess.yaml",
        "stage6-candidate-c-modal-multiprocess-seed2026",
    )


@app.local_entrypoint()
def main(target: str = "gate") -> None:
    if target == "gate":
        print(json.dumps(adapter_gate.remote(), indent=2, sort_keys=True))
    elif target == "smoke":
        smoke.remote()
    elif target == "candidate":
        candidate.remote()
    else:
        raise ValueError("target must be gate, smoke, or candidate")
