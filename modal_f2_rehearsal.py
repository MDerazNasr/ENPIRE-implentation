"""Fixed, non-promotable F2 matched-runtime rehearsal on Modal.

This application has no arbitrary command or profile input.  Its only GPU
operation runs the two frozen one-step arm profiles followed by the existing
two-process schedule/replay-resume micro-gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import modal


APP_NAME = "enpire-f2-matched-runtime-rehearsal-v1"
GPU = "RTX-PRO-6000"
CPU_CORES = 16
MEMORY_MIB = 96 * 1024
FUNCTION_TIMEOUT_SECONDS = 9_000
PROJECT_ROOT = "/opt/qualia"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/workspace"
ACTOR = f"{WORKSPACE}/checkpoints/stage1-step-500-actor"
NORM_STATS = f"{PROJECT_ROOT}/norm_stats.json"
RUNTIME_CONTRACT_PATH = Path(PROJECT_ROOT) / "runtime-contract.json"
RUNTIME_CONTRACT_ID = "enpire-matched-scientific-runtime-v1"
IMAGE_PLATFORM_DIGEST = (
    "sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7"
)
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
EXPECTED_ACTOR_SIZE = 10_015_912_759
EXPECTED_ACTOR_SHA256 = (
    "b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3"
)
EXPECTED_NORM_SHA256 = (
    "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
)
GPU_PRICE_USD_PER_SECOND = 0.000842
CPU_PRICE_USD_PER_CORE_SECOND = 0.0000131
MEMORY_PRICE_USD_PER_GIB_SECOND = 0.00000222
SELECTED_RUNTIME_USD_PER_SECOND = (
    GPU_PRICE_USD_PER_SECOND
    + CPU_CORES * CPU_PRICE_USD_PER_CORE_SECOND
    + (MEMORY_MIB / 1024) * MEMORY_PRICE_USD_PER_GIB_SECOND
)

CONTROL_RUN_ID = "f2-control-rehearsal-seed2026-attempt1"
CANDIDATE_RUN_ID = "f2-candidate-rehearsal-seed2026-attempt1"
RESUME_SOURCE_RUN_ID = "f2-resume-source-seed2026-attempt1"
RESUME_CONTINUATION_RUN_ID = "f2-resume-continuation-seed2026-attempt1"


app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "f2-rehearsal"})
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)

image = (
    modal.Image.from_registry(
        f"nvidia/cuda@{IMAGE_PLATFORM_DIGEST}", add_python="3.11"
    )
    .entrypoint([])
    .env({"PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}"})
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
        "libxext6",
        "libgbm1",
    )
    .run_commands(
        "git clone https://github.com/RLinf/RLinf.git /opt/RLinf",
        f"cd /opt/RLinf && git checkout {RLINF_COMMIT}",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1",
        f"cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = {RLINF_COMMIT}",
    )
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "configs/d1/assets/maniskill_peginsertionside_joint.norm_stats.json",
        NORM_STATS,
        copy=True,
    )
    .add_local_file(
        "results/runtime-qualification/f0/runtime-contract.json",
        str(RUNTIME_CONTRACT_PATH),
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
        "GPU_HOURLY_PRICE_USD": f"{SELECTED_RUNTIME_USD_PER_SECOND * 3600:.6f}",
        "EMBODIED_PATH": f"{RLINF_HOME}/examples/embodiment",
        "PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}",
        "PYTHONUNBUFFERED": "1",
        "QUALIA_MODAL_MULTIPROCESS": "1",
        "QUALIA_MODAL_MP_START_METHOD": "spawn",
        "QUALIA_MODAL_RENDER_DEVICE": "pci:0000:00:00.0",
        "QUALIA_MODAL_VULKAN_ICD": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "QUALIA_MODAL_THREADS_PER_WORKER": "1",
        "QUALIA_RLT_RESUME_STATE": "1",
        "VK_ICD_FILENAMES": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "LP_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }


def _verify_runtime_and_inputs() -> dict[str, Any]:
    runtime_raw = RUNTIME_CONTRACT_PATH.read_bytes()
    runtime = json.loads(runtime_raw)
    if runtime.get("contract_id") != RUNTIME_CONTRACT_ID:
        raise RuntimeError("runtime contract identity mismatch")
    actor_file = Path(ACTOR) / "model_state_dict/full_weights.pt"
    if not actor_file.is_file() or actor_file.stat().st_size != EXPECTED_ACTOR_SIZE:
        raise RuntimeError("canonical Stage-1 actor is missing or has wrong size")
    actor_sha = _sha256(actor_file)
    if actor_sha != EXPECTED_ACTOR_SHA256:
        raise RuntimeError("canonical Stage-1 actor hash mismatch")
    norm_sha = _sha256(Path(NORM_STATS))
    if norm_sha != EXPECTED_NORM_SHA256:
        raise RuntimeError("normalization-stat hash mismatch")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=RLINF_HOME, text=True
    ).strip()
    if revision != RLINF_COMMIT:
        raise RuntimeError("RLinf revision mismatch")
    vulkan = subprocess.run(
        ["vulkaninfo", "--summary"],
        env=_runtime_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    if vulkan.returncode != 0 or "llvmpipe" not in vulkan.stdout.lower():
        raise RuntimeError("Mesa llvmpipe Vulkan gate failed")
    probe = subprocess.check_output(
        [
            f"{RLINF_HOME}/.venv/bin/python",
            "-c",
            "import json,platform,torch; from importlib.metadata import version; p=torch.cuda.get_device_properties(0); print(json.dumps({'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':p.name,'gpu_memory_bytes':p.total_memory,'maniskill':version('mani-skill'),'sapien':version('sapien')}))",
        ],
        text=True,
        env=_runtime_environment(),
    )
    observed = json.loads(probe)
    expected = {
        "python": "3.11.14",
        "torch": "2.8.0+cu128",
        "cuda": "12.8",
        "gpu": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        "maniskill": "3.0.0b22",
        "sapien": "3.0.1",
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            raise RuntimeError(f"runtime {key} mismatch: {observed.get(key)!r}")
    if int(observed["gpu_memory_bytes"]) < 96_000_000_000:
        raise RuntimeError("GPU memory is below the F0 minimum")
    return {
        "runtime_contract_sha256": hashlib.sha256(runtime_raw).hexdigest(),
        "actor_size_bytes": EXPECTED_ACTOR_SIZE,
        "actor_sha256": actor_sha,
        "norm_stats_sha256": norm_sha,
        "rlinf_commit": revision,
        "observed_runtime": observed,
    }


def _ensure_ray_head() -> None:
    ray = f"{RLINF_HOME}/.venv/bin/ray"
    status = subprocess.run(
        [ray, "status"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if status.returncode == 0:
        return
    started = subprocess.run(
        [
            ray,
            "start",
            "--head",
            "--include-dashboard=false",
            "--disable-usage-stats",
            "--num-cpus=16",
        ],
        env={**os.environ, "RAY_USAGE_STATS_ENABLED": "0"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(started.stdout, flush=True)
    if started.returncode != 0:
        raise RuntimeError("explicit Ray head failed")
    subprocess.run([ray, "status"], check=True)


def _run_profile(profile: str, run_id: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
    run_dir = Path(WORKSPACE) / "results/d1" / run_id
    if run_dir.exists():
        raise RuntimeError(f"fixed F2 run directory already exists: {run_dir}")
    command = [
        f"{RLINF_HOME}/.venv/bin/python",
        "-m",
        "agent.d1_launcher",
        "--config",
        f"{PROJECT_ROOT}/configs/d1/{profile}",
        "--results-root",
        f"{WORKSPACE}/results",
        "--run-id",
        run_id,
        "--execute",
        "--acknowledge-paid-run",
    ]
    environment = _runtime_environment()
    if extra:
        environment.update(extra)
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=PROJECT_ROOT, env=environment)
    finally:
        workspace.commit()
    if completed.returncode != 0:
        raise RuntimeError(f"F2 profile {profile} failed with exit {completed.returncode}")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    return {
        "profile": profile,
        "run_id": run_id,
        "elapsed_seconds": time.monotonic() - started,
        "manifest": manifest,
    }


def _checkpoint(run_id: str, step: int) -> Path:
    return (
        Path(WORKSPACE)
        / "results/d1"
        / run_id
        / "maniskill_rlt_stage2_ac_mlp/checkpoints"
        / f"global_step_{step}"
    )


def _audit_checkpoint(run_id: str, step: int) -> dict[str, Any]:
    from agent.rlt_resume_state import audit_state_file

    root = _checkpoint(run_id, step)
    required = (
        "actor/dcp_checkpoint/.metadata",
        "actor/model_state_dict/full_weights.pt",
        "actor/sac_components/target_model/checkpoint_rank_0.pt",
        "actor/sac_components/replay_buffer/rank_0/trajectory_index.json",
        "actor/sac_components/rlt_schedule_state/rank_0.json",
    )
    inventory = {}
    for relative in required:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"checkpoint is incomplete: {path}")
        inventory[relative] = path.stat().st_size
    state = audit_state_file(
        root / "actor/sac_components/rlt_schedule_state/rank_0.json",
        expected_step=step,
        expected_rank=0,
        expected_world_size=1,
        require_replay_rng=True,
    )
    return {"path": str(root), "files": inventory, "rlt_schedule_state": state}


def _resume_gate() -> dict[str, Any]:
    from agent.metrics import parse_metrics

    common = {
        "SCHEDULE_GATE_MAX_STEPS": "1",
        "SCHEDULE_GATE_SAVE_INTERVAL": "1",
        "SCHEDULE_GATE_RESUME_DIR": "null",
    }
    source_run = _run_profile(
        "stage2_6_schedule_resume_gate.yaml", RESUME_SOURCE_RUN_ID, common
    )
    source = _audit_checkpoint(RESUME_SOURCE_RUN_ID, 1)
    source_state = source["rlt_schedule_state"]
    if source_state["counters"]["update_step"] != 1:
        raise RuntimeError("resume source did not record one update")
    source_metrics = parse_metrics(
        (Path(WORKSPACE) / "results/d1" / RESUME_SOURCE_RUN_ID / "run.log").read_text()
    )
    if source_metrics.get("rlt/update_step") != [0.0]:
        raise RuntimeError("resume source did not begin at update zero")
    if source_metrics.get("actor/actor_weight_in_warmup") != [1.0]:
        raise RuntimeError("resume source did not exercise warm-up weights")
    continuation_run = _run_profile(
        "stage2_6_schedule_resume_gate.yaml",
        RESUME_CONTINUATION_RUN_ID,
        {
            "SCHEDULE_GATE_MAX_STEPS": "2",
            "SCHEDULE_GATE_SAVE_INTERVAL": "2",
            "SCHEDULE_GATE_RESUME_DIR": str(_checkpoint(RESUME_SOURCE_RUN_ID, 1)),
        },
    )
    continuation = _audit_checkpoint(RESUME_CONTINUATION_RUN_ID, 2)
    continuation_state = continuation["rlt_schedule_state"]
    if continuation_state["counters"]["update_step"] != 2:
        raise RuntimeError("resumed counter did not reach two updates")
    if continuation_state["schedule_fingerprint"] != source_state["schedule_fingerprint"]:
        raise RuntimeError("schedule fingerprint changed across resume")
    if (
        continuation_state["counters"]["total_transitions_added"]
        < source_state["counters"]["total_transitions_added"]
    ):
        raise RuntimeError("transition counter regressed across resume")
    if not continuation_state.get("replay_generator_state_present"):
        raise RuntimeError("resumed sidecar has no replay RNG state")
    log = (
        Path(WORKSPACE) / "results/d1" / RESUME_CONTINUATION_RUN_ID / "run.log"
    ).read_text()
    if "QUALIA_RLT_RESUME_STATE=" not in log:
        raise RuntimeError("resume restore marker is missing")
    continuation_metrics = parse_metrics(log)
    if continuation_metrics.get("rlt/update_step") != [1.0]:
        raise RuntimeError("continuation did not resume at update one")
    if continuation_metrics.get("actor/actor_weight_in_warmup") != [0.0]:
        raise RuntimeError("continuation did not enter online weights")
    return {
        "source_run": source_run,
        "source_checkpoint": source,
        "continuation_run": continuation_run,
        "continuation_checkpoint": continuation,
        "source_metrics": source_metrics,
        "continuation_metrics": continuation_metrics,
        "known_limit": "simulator state is not claimed bitwise-identical across processes",
    }


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    max_containers=1,
    volumes={WORKSPACE: workspace},
)
def run_fixed_rehearsal() -> dict[str, Any]:
    started = time.monotonic()
    inputs = _verify_runtime_and_inputs()
    _ensure_ray_head()
    control = _run_profile("f2_control_rehearsal.yaml", CONTROL_RUN_ID)
    control["checkpoint"] = _audit_checkpoint(CONTROL_RUN_ID, 1)
    candidate = _run_profile("f2_candidate_rehearsal.yaml", CANDIDATE_RUN_ID)
    candidate["checkpoint"] = _audit_checkpoint(CANDIDATE_RUN_ID, 1)
    resume = _resume_gate()
    elapsed = time.monotonic() - started
    result = {
        "schema_version": 1,
        "status": "pass",
        "claim_scope": "F2 runtime rehearsal only; no policy comparison or promotion",
        "inputs": inputs,
        "control": control,
        "candidate": candidate,
        "resume": resume,
        "elapsed_seconds": elapsed,
        "estimated_runtime_resource_cost_usd": elapsed
        * SELECTED_RUNTIME_USD_PER_SECOND,
        "segmentation_decision_basis": "allow only predeclared step-boundary segmentation with native checkpoint plus strict sidecar; simulator state is not bitwise continuous",
    }
    output = Path(WORKSPACE) / "results/runtime-qualification/f2/attempt-1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    workspace.commit()
    print(f"ENPIRE_F2_RESULT={json.dumps(result, sort_keys=True)}", flush=True)
    return result


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(run_fixed_rehearsal.spawn().get(), indent=2, sort_keys=True))
