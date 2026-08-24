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
import sys
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
        "CANDIDATE_RESUME_DIR": "null",
        "CANDIDATE_MAX_STEPS": "60",
        "CANDIDATE_VAL_CHECK_INTERVAL": "-1",
        "CANDIDATE_SAVE_INTERVAL": "10",
        "GPU_HOURLY_PRICE_USD": "3.03",
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


def _ray_diagnostics() -> str:
    root = Path("/tmp/ray/session_latest/logs")
    chunks: list[str] = []
    for name in ("gcs_server.out", "gcs_server.err", "raylet.out", "raylet.err"):
        path = root / name
        if path.is_file():
            chunks.append(f"===== {path} =====\n{path.read_text(errors='replace')[-12000:]}")
    return "\n".join(chunks) or "Ray created no diagnostic logs"


def _ensure_ray_head() -> None:
    ray = f"{RLINF_HOME}/.venv/bin/ray"
    status = subprocess.run(
        [ray, "status"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if status.returncode == 0:
        print("QUALIA_RAY_HEAD=existing", flush=True)
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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(started.stdout, flush=True)
    if started.returncode != 0:
        print(_ray_diagnostics(), flush=True)
        raise RuntimeError(f"explicit Ray head failed with exit {started.returncode}")
    verified = subprocess.run(
        [ray, "status"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(verified.stdout, flush=True)
    if verified.returncode != 0:
        print(_ray_diagnostics(), flush=True)
        raise RuntimeError("explicit Ray head did not become healthy")
    print("QUALIA_RAY_HEAD=started-and-healthy", flush=True)


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


def _run_profile(
    profile: str,
    run_id: str,
    *,
    extra_environment: dict[str, str] | None = None,
) -> int:
    _ensure_ray_head()
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
    environment = _runtime_environment()
    if extra_environment:
        environment.update(extra_environment)
    try:
        completed = subprocess.run(command, cwd=PROJECT_ROOT, env=environment)
    finally:
        workspace.commit()
    if completed.returncode != 0:
        raise RuntimeError(f"RLinf profile failed with exit {completed.returncode}")
    return completed.returncode


def _checkpoint_path(run_id: str, step: int) -> Path:
    return (
        Path(WORKSPACE)
        / "results/d1"
        / run_id
        / "maniskill_rlt_stage2_ac_mlp/checkpoints"
        / f"global_step_{step}"
    )


def _verify_resume_checkpoint(path: Path, expected_step: int) -> dict[str, object]:
    if path.name != f"global_step_{expected_step}":
        raise RuntimeError(
            f"checkpoint step mismatch: expected {expected_step}, got {path.name}"
        )
    required = (
        "actor/dcp_checkpoint/.metadata",
        "actor/model_state_dict/full_weights.pt",
        "actor/sac_components/target_model/checkpoint_rank_0.pt",
        "actor/sac_components/replay_buffer/rank_0/trajectory_index.json",
        "actor/sac_components/rlt_schedule_state/rank_0.json",
    )
    inventory: dict[str, int] = {}
    for relative in required:
        checkpoint_file = path / relative
        if not checkpoint_file.is_file():
            raise FileNotFoundError(f"resume checkpoint is incomplete: {checkpoint_file}")
        inventory[relative] = checkpoint_file.stat().st_size
    result: dict[str, object] = {
        "checkpoint": str(path),
        "step": expected_step,
        "required_files": inventory,
    }
    schedule_state_path = (
        path / "actor/sac_components/rlt_schedule_state/rank_0.json"
    )
    schedule_state = json.loads(schedule_state_path.read_text())
    expected_schedule = {
        "schema_version": 1,
        "rlinf_commit": "c90951a0c799a750cb5294ed10587c61cc2af8bf",
        "checkpoint_step": expected_step,
        "rank": 0,
    }
    for key, value in expected_schedule.items():
        if schedule_state.get(key) != value:
            raise RuntimeError(
                f"RLT schedule sidecar {key} mismatch: "
                f"{schedule_state.get(key)!r} != {value!r}"
            )
    result["rlt_schedule_state"] = schedule_state
    print(f"QUALIA_MODAL_RESUME_CHECKPOINT={json.dumps(result, sort_keys=True)}")
    return result


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


RESUME_SOURCE_RUN_ID = "stage6-modal-resume-gate-source-seed2026-r1"
RESUME_CONTINUATION_RUN_ID = "stage6-modal-resume-gate-continuation-seed2026-r1"

SCHEDULE_SOURCE_RUN_ID = "stage6r-schedule-resume-source-seed2026-r3"
SCHEDULE_CONTINUATION_RUN_ID = "stage6r-schedule-resume-continuation-seed2026-r3"


def _run_log(run_id: str) -> Path:
    return Path(WORKSPACE) / "results/d1" / run_id / "run.log"


def _schedule_gate_observation(run_id: str, step: int) -> dict[str, object]:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from agent.metrics import parse_metrics

    checkpoint = _verify_resume_checkpoint(_checkpoint_path(run_id, step), step)
    metrics = parse_metrics(_run_log(run_id).read_text())
    return {
        "checkpoint": checkpoint,
        "update_steps": metrics.get("rlt/update_step", []),
        "actor_weight_in_warmup": metrics.get(
            "actor/actor_weight_in_warmup", []
        ),
        "bc_weights": metrics.get("actor/bc_weight", []),
    }


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=98304,
    timeout=60 * 60,
    volumes={WORKSPACE: workspace},
)
def schedule_resume_gate() -> dict[str, object]:
    common = {
        "SCHEDULE_GATE_MAX_STEPS": "1",
        "SCHEDULE_GATE_SAVE_INTERVAL": "1",
        "SCHEDULE_GATE_RESUME_DIR": "null",
    }
    _run_profile(
        "stage2_6_schedule_resume_gate.yaml",
        SCHEDULE_SOURCE_RUN_ID,
        extra_environment=common,
    )
    source = _schedule_gate_observation(SCHEDULE_SOURCE_RUN_ID, 1)
    source_state = source["checkpoint"]["rlt_schedule_state"]
    if source_state["counters"]["update_step"] != 1:
        raise RuntimeError("source sidecar did not record exactly one update")
    if source["update_steps"] != [0.0]:
        raise RuntimeError(f"unexpected source update metrics: {source['update_steps']}")
    if source["actor_weight_in_warmup"] != [1.0]:
        raise RuntimeError("source did not exercise actor-weight warm-up")

    source_path = _checkpoint_path(SCHEDULE_SOURCE_RUN_ID, 1)
    _run_profile(
        "stage2_6_schedule_resume_gate.yaml",
        SCHEDULE_CONTINUATION_RUN_ID,
        extra_environment={
            "SCHEDULE_GATE_MAX_STEPS": "2",
            "SCHEDULE_GATE_SAVE_INTERVAL": "2",
            "SCHEDULE_GATE_RESUME_DIR": str(source_path),
        },
    )
    continuation = _schedule_gate_observation(SCHEDULE_CONTINUATION_RUN_ID, 2)
    continuation_state = continuation["checkpoint"]["rlt_schedule_state"]
    if continuation_state["counters"]["update_step"] != 2:
        raise RuntimeError("continuation sidecar did not record exactly two updates")
    if continuation["update_steps"] != [1.0]:
        raise RuntimeError(
            f"resume reset or skipped the counter: {continuation['update_steps']}"
        )
    if continuation["actor_weight_in_warmup"] != [0.0]:
        raise RuntimeError("continuation did not enter the online actor-weight phase")
    if "QUALIA_RLT_RESUME_STATE=" not in _run_log(
        SCHEDULE_CONTINUATION_RUN_ID
    ).read_text():
        raise RuntimeError("continuation log is missing the explicit restore marker")
    source_transitions = source_state["counters"]["total_transitions_added"]
    continued_transitions = continuation_state["counters"][
        "total_transitions_added"
    ]
    if continued_transitions < source_transitions:
        raise RuntimeError("restored transition total regressed")
    result = {
        "status": "pass",
        "source": source,
        "continuation": continuation,
    }
    output = Path(WORKSPACE) / "results/stage6r-schedule-resume-gate.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    workspace.commit()
    print(f"QUALIA_SCHEDULE_RESUME_GATE={json.dumps(result, sort_keys=True)}")
    return result


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=131072,
    timeout=60 * 60 * 4,
    volumes={WORKSPACE: workspace},
)
def resume_source() -> dict[str, object]:
    _run_profile(
        "stage2_6_candidate_modal_multiprocess_smoke.yaml",
        RESUME_SOURCE_RUN_ID,
    )
    return _verify_resume_checkpoint(
        _checkpoint_path(RESUME_SOURCE_RUN_ID, 1), expected_step=1
    )


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=131072,
    timeout=60 * 60 * 4,
    volumes={WORKSPACE: workspace},
)
def resume_continuation() -> dict[str, object]:
    source = _checkpoint_path(RESUME_SOURCE_RUN_ID, 1)
    source_inventory = _verify_resume_checkpoint(source, expected_step=1)
    _run_profile(
        "stage2_6_candidate_modal_resume_gate.yaml",
        RESUME_CONTINUATION_RUN_ID,
        extra_environment={"RESUME_CHECKPOINT": str(source)},
    )
    continued_inventory = _verify_resume_checkpoint(
        _checkpoint_path(RESUME_CONTINUATION_RUN_ID, 2), expected_step=2
    )
    return {"source": source_inventory, "continued": continued_inventory}


@app.function(
    image=image,
    gpu=GPU,
    cpu=16,
    memory=131072,
    timeout=60 * 60 * 24,
    volumes={WORKSPACE: workspace},
)
def candidate(
    run_id: str = "stage6-candidate-c-modal-multiprocess-seed2026-r4-train-to-60",
    resume_dir: str = "",
    max_steps: int = 60,
    val_check_interval: int = -1,
    save_interval: int = 10,
) -> int:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from agent.d1_modal_schedule import validate_candidate_segment

    resume_step = 0
    if resume_dir:
        resume_path = Path(resume_dir)
        try:
            resume_step = int(resume_path.name.removeprefix("global_step_"))
        except ValueError as error:
            raise ValueError(
                "resume_dir must end in global_step_<integer>"
            ) from error
        _verify_resume_checkpoint(resume_path, expected_step=resume_step)
    validate_candidate_segment(
        resume_step=resume_step,
        max_steps=max_steps,
        val_check_interval=val_check_interval,
        save_interval=save_interval,
    )
    result = _run_profile(
        "stage2_6_candidate_modal_multiprocess.yaml",
        run_id,
        extra_environment={
            "CANDIDATE_RESUME_DIR": resume_dir or "null",
            "CANDIDATE_MAX_STEPS": str(max_steps),
            "CANDIDATE_VAL_CHECK_INTERVAL": str(val_check_interval),
            "CANDIDATE_SAVE_INTERVAL": str(save_interval),
        },
    )
    _verify_resume_checkpoint(_checkpoint_path(run_id, max_steps), max_steps)
    workspace.commit()
    return result


@app.local_entrypoint()
def main(
    target: str = "gate",
    run_id: str = "stage6-candidate-c-modal-multiprocess-seed2026-r4-train-to-60",
    resume_dir: str = "",
    max_steps: int = 60,
    val_check_interval: int = -1,
    save_interval: int = 10,
) -> None:
    if target == "gate":
        print(json.dumps(adapter_gate.spawn().get(), indent=2, sort_keys=True))
    elif target == "smoke":
        smoke.spawn().get()
    elif target == "resume-gate":
        source = resume_source.spawn().get()
        continued = resume_continuation.spawn().get()
        print(
            json.dumps(
                {"source": source, "continued": continued},
                indent=2,
                sort_keys=True,
            )
        )
    elif target == "schedule-resume-gate":
        print(
            json.dumps(
                schedule_resume_gate.spawn().get(), indent=2, sort_keys=True
            )
        )
    elif target == "candidate":
        candidate.spawn(
            run_id=run_id,
            resume_dir=resume_dir,
            max_steps=max_steps,
            val_check_interval=val_check_interval,
            save_interval=save_interval,
        ).get()
    else:
        raise ValueError(
            "target must be gate, smoke, resume-gate, schedule-resume-gate, or candidate"
        )
