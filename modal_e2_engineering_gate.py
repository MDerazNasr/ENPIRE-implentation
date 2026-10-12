"""Fixed two-arm E2 engineering gate on Modal.

The gate trains one control and one candidate from the selected E1 actor, each
in two predeclared 50-step segments, then evaluates the final actors on four
frozen development shards. It cannot access final resets, retry a run, invoke
an agent provider, select a policy, or promote a checkpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import modal

from e1_staged_checkpoint_runtime import (
    bounded_error,
    load_valid_stage_receipt,
    sha256_file,
)
from supervisor.e1_sharded_evaluation import (
    aggregate_shard_receipts,
    evaluator_contract_sha256,
    parse_final_eval_metrics,
    shard_spec,
)


APP_NAME = "enpire-g0-e2-engineering-gate-v2"
PROJECT_ROOT = "/opt/qualia"
E1_RUNTIME_ROOT = f"{PROJECT_ROOT}/e1_runtime"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/workspace"
RESULTS_ROOT = Path(WORKSPACE) / "e2-engineering-gate-v2"
TRAINING_RESULTS_ROOT = RESULTS_ROOT / "training"
EVALUATION_RESULTS_ROOT = RESULTS_ROOT / "evaluation"

TRAIN_GPU = "RTX-PRO-6000"
TRAIN_CPU_CORES = 16
TRAIN_MEMORY_MIB = 128 * 1024
TRAIN_TIMEOUT_SECONDS = 59_400
EVAL_GPU = "L40S"
EVAL_CPU_CORES = 16
EVAL_MEMORY_MIB = 96 * 1024
EVAL_TIMEOUT_SECONDS = 2_700

GPU_PRICE_USD_PER_SECOND = 0.000842
CPU_PRICE_USD_PER_CORE_SECOND = 0.0000131
MEMORY_PRICE_USD_PER_GIB_SECOND = 0.00000222
L40S_PRICE_USD_PER_SECOND = 1.9512 / 3600
TRAIN_RATE_USD_PER_SECOND = (
    GPU_PRICE_USD_PER_SECOND
    + TRAIN_CPU_CORES * CPU_PRICE_USD_PER_CORE_SECOND
    + (TRAIN_MEMORY_MIB / 1024) * MEMORY_PRICE_USD_PER_GIB_SECOND
)
EVAL_RATE_USD_PER_SECOND = (
    L40S_PRICE_USD_PER_SECOND
    + EVAL_CPU_CORES * CPU_PRICE_USD_PER_CORE_SECOND
    + (EVAL_MEMORY_MIB / 1024) * MEMORY_PRICE_USD_PER_GIB_SECOND
)
MAX_TRAIN_COST_USD = 4 * TRAIN_TIMEOUT_SECONDS * TRAIN_RATE_USD_PER_SECOND
MAX_EVAL_COST_USD = 8 * EVAL_TIMEOUT_SECONDS * EVAL_RATE_USD_PER_SECOND
CPU_ONLY_RATE_USD_PER_SECOND = (
    2 * CPU_PRICE_USD_PER_CORE_SECOND + 4 * MEMORY_PRICE_USD_PER_GIB_SECOND
)
MAX_CPU_ONLY_COST_USD = (1_800 + 600) * CPU_ONLY_RATE_USD_PER_SECOND
MAX_GATE_COST_USD = MAX_TRAIN_COST_USD + MAX_EVAL_COST_USD + MAX_CPU_ONLY_COST_USD
BUDGET_CAP_USD = 350.0

IMAGE_PLATFORM_DIGEST = (
    "sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7"
)
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
NORM_STATS = f"{PROJECT_ROOT}/norm_stats.json"
EXPECTED_NORM_SHA256 = (
    "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
)
DEVELOPMENT_RESETS = f"{PROJECT_ROOT}/development-resets.json"
DEVELOPMENT_RESET_SHA256 = (
    "e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161"
)
DEVELOPMENT_RESET_FILE_SHA256 = (
    "c99cf14c7a7d926df5f502d9e5ca00d33c62487bb1ffeea1eae4f15ce47ed489"
)
EVALUATOR_CONTRACT_SHA256 = (
    "ee979edef79b84440bfac0b6f0a787315af71b69252be64cfea06465935dd256"
)

STAGE_RECEIPT = Path(WORKSPACE) / "e1-l40s-results/step-2000-stage-v4-terminal.json"
STAGED_ACTOR = Path(WORKSPACE) / "e1-checkpoints/step-2000-stage-v4/actor"
STAGED_WEIGHTS = STAGED_ACTOR / "model_state_dict/full_weights.pt"
SELECTED_CHECKPOINT = {
    "sha256": "4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146",
    "size_bytes": 10_015_912_662,
    "step": 2000,
    "version_id": "LvdNrl8pPsbD6s9tdJ8.__.1V2B00077",
}

ARMS = {
    "control": {"warmup_bc_weight": "7", "online_bc_weight": "2.5"},
    "candidate": {"warmup_bc_weight": "5.6", "online_bc_weight": "2"},
}
SEGMENTS = {
    1: {"resume_step": 0, "max_steps": 50, "save_interval": 50},
    2: {"resume_step": 50, "max_steps": 100, "save_interval": 100},
}


if MAX_GATE_COST_USD > BUDGET_CAP_USD:
    raise RuntimeError("fixed E2 resource envelope exceeds the approved $350 cap")

app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "g0-e2-engineering"})
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)

image = (
    modal.Image.from_registry(
        f"nvidia/cuda@{IMAGE_PLATFORM_DIGEST}", add_python="3.11"
    )
    .entrypoint([])
    .env({"PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}"})
    .apt_install(
        "git", "git-lfs", "curl", "wget", "unzip", "build-essential", "cmake",
        "libgl1", "libglib2.0-0", "libsm6", "libxext6", "libxrender1",
        "libvulkan1=1.3.204.1-2", "vulkan-tools=1.3.204.0+dfsg1-1",
        "mesa-vulkan-drivers=23.2.1-1ubuntu3.1~22.04.4", "libegl1",
        "libgles2", "libglvnd0", "libx11-6", "libx11-xcb1", "libxcb1",
        "libgbm1",
    )
    .run_commands(
        "git clone https://github.com/RLinf/RLinf.git /opt/RLinf",
        f"cd /opt/RLinf && git checkout {RLINF_COMMIT}",
        "cd /opt/RLinf && UV_TORCH_BACKEND=cu128 bash requirements/install.sh embodied --model openpi --env maniskill_libero --torch 2.8.0 --python 3.11.14 --no-root --no-flash-attn --no-apex --install-rlinf",
        "cd /opt/RLinf && uv pip install --python .venv/bin/python hydra-core==1.3.2 omegaconf==2.3.0 sapien==3.0.1",
        f"cd /opt/RLinf && test \"$(git rev-parse HEAD)\" = {RLINF_COMMIT}",
    )
    .run_commands(
        "cd /opt/RLinf && uv pip install --python .venv/bin/python pyarrow==25.0.1"
    )
    .pip_install("modal==1.5.4")
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("e1_runtime", E1_RUNTIME_ROOT, copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "e1_staged_checkpoint_runtime.py",
        f"{PROJECT_ROOT}/e1_staged_checkpoint_runtime.py",
        copy=True,
    )
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


def _run_id(arm: str, segment: int) -> str:
    return f"g0-e2-{arm}-seed2026-segment{segment}-v1"


def _checkpoint_path(arm: str, segment: int) -> Path:
    step = SEGMENTS[segment]["max_steps"]
    return (
        TRAINING_RESULTS_ROOT / "d1" / _run_id(arm, segment)
        / "maniskill_rlt_stage2_ac_mlp/checkpoints" / f"global_step_{step}"
    )


def _terminal_path(arm: str, segment: int) -> Path:
    return RESULTS_ROOT / f"training-{arm}-segment{segment}-terminal.json"


def _validate_arm_segment(arm: str, segment: int) -> None:
    if arm not in ARMS or segment not in SEGMENTS:
        raise ValueError("only control/candidate and segments 1/2 are permitted")


def _base_environment() -> dict[str, str]:
    return {
        **os.environ,
        "RLINF_HOME": RLINF_HOME,
        "MODAL_ADAPTER_ROOT": PROJECT_ROOT,
        "NORM_STATS_PATH": NORM_STATS,
        "WANDB_PROJECT": "qualia-rlt-d1",
        "WANDB_MODE": "offline",
        "WANDB_DIR": f"{WORKSPACE}/wandb",
        "HF_HOME": f"{WORKSPACE}/cache/huggingface",
        "HF_DATASETS_CACHE": f"{WORKSPACE}/cache/huggingface/datasets",
        "D1_SEED": "2026",
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


def _ensure_ray_head() -> None:
    ray = f"{RLINF_HOME}/.venv/bin/ray"
    if subprocess.run([ray, "status"], capture_output=True).returncode == 0:
        return
    subprocess.run(
        [ray, "start", "--head", "--include-dashboard=false",
         "--disable-usage-stats", "--num-cpus=16"],
        env={**os.environ, "RAY_USAGE_STATS_ENABLED": "0"}, check=True,
    )


def _verify_selected_actor() -> dict[str, Any]:
    receipt = load_valid_stage_receipt(
        STAGE_RECEIPT, STAGED_WEIGHTS, expected_checkpoint=SELECTED_CHECKPOINT
    )
    if sha256_file(Path(NORM_STATS)) != EXPECTED_NORM_SHA256:
        raise RuntimeError("normalization-stat identity mismatch")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=RLINF_HOME, text=True
    ).strip()
    if revision != RLINF_COMMIT:
        raise RuntimeError("RLinf revision mismatch")
    return {
        "checkpoint": SELECTED_CHECKPOINT,
        "stage_receipt_sha256": sha256_file(STAGE_RECEIPT),
        "stage_status": receipt["status"],
    }


def _verify_checkpoint(path: Path, expected_step: int) -> dict[str, Any]:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from agent.rlt_resume_state import audit_state_file

    if path.name != f"global_step_{expected_step}":
        raise RuntimeError("checkpoint step identity mismatch")
    required = (
        "actor/dcp_checkpoint/.metadata",
        "actor/model_state_dict/full_weights.pt",
        "actor/sac_components/target_model/checkpoint_rank_0.pt",
        "actor/sac_components/replay_buffer/rank_0/trajectory_index.json",
        "actor/sac_components/rlt_schedule_state/rank_0.json",
    )
    inventory: dict[str, int] = {}
    for relative in required:
        item = path / relative
        if not item.is_file():
            raise RuntimeError(f"checkpoint is incomplete: {relative}")
        inventory[relative] = item.stat().st_size
    schedule = audit_state_file(
        path / "actor/sac_components/rlt_schedule_state/rank_0.json",
        expected_step=expected_step,
        expected_rank=0,
        expected_world_size=1,
        require_replay_rng=True,
    )
    weights = path / "actor/model_state_dict/full_weights.pt"
    return {
        "path": str(path),
        "step": expected_step,
        "required_files": inventory,
        "rlt_schedule_state": schedule,
        "actor_weights_sha256": sha256_file(weights),
        "actor_weights_size_bytes": weights.stat().st_size,
    }


@app.function(
    image=image, cpu=2, memory=4096, timeout=1800, retries=0,
    single_use_containers=True, volumes={WORKSPACE: workspace},
)
def preflight() -> dict[str, Any]:
    """Validate the immutable inputs and empty destinations without a GPU."""

    receipt_path = RESULTS_ROOT / "preflight.json"
    if receipt_path.exists():
        raise RuntimeError("create-only preflight receipt already exists")
    selected = _verify_selected_actor()
    compatibility = json.loads(
        subprocess.check_output(
            [
                f"{RLINF_HOME}/.venv/bin/python",
                "-c",
                "import json,numpy,pyarrow; print(json.dumps({'numpy':numpy.__version__,'pyarrow':pyarrow.__version__}))",
            ],
            text=True,
        )
    )
    if compatibility != {"numpy": "1.26.4", "pyarrow": "25.0.1"}:
        raise RuntimeError(f"RLinf NumPy/PyArrow compatibility mismatch: {compatibility}")
    if evaluator_contract_sha256(Path(PROJECT_ROOT)) != EVALUATOR_CONTRACT_SHA256:
        raise RuntimeError("evaluator contract source identity mismatch")
    if sha256_file(Path(DEVELOPMENT_RESETS)) != DEVELOPMENT_RESET_FILE_SHA256:
        raise RuntimeError("development reset file identity mismatch")
    forbidden = [
        _terminal_path(arm, segment)
        for arm in ARMS
        for segment in SEGMENTS
    ] + [
        RESULTS_ROOT / f"evaluation-{arm}-shard{index}-terminal.json"
        for arm in ARMS
        for index in range(4)
    ]
    forbidden += [RESULTS_ROOT / "comparison.json", RESULTS_ROOT / "demo-report.md"]
    collisions = [str(path) for path in forbidden if path.exists()]
    if collisions:
        raise RuntimeError(f"E2 create-only destinations already exist: {collisions}")
    stats = os.statvfs(WORKSPACE)
    free_bytes = stats.f_bavail * stats.f_frsize
    if free_bytes < 100 * 1024**3:
        raise RuntimeError("Modal workspace has less than 100 GiB free")
    payload = {
        "schema_version": 1,
        "status": "ready_for_fixed_e2_engineering_gate",
        "account": {
            "provider": "Modal",
            "profile": "deraznasr776",
            "email": "deraznasr776@gmail.com",
        },
        "selected_actor": selected,
        "rlinf_numpy_pyarrow": compatibility,
        "seed": 2026,
        "arms": ARMS,
        "segments": SEGMENTS,
        "development_reset_sha256": DEVELOPMENT_RESET_SHA256,
        "evaluator_contract_sha256": EVALUATOR_CONTRACT_SHA256,
        "free_bytes": free_bytes,
        "resource_ceiling": {
            "training_usd": MAX_TRAIN_COST_USD,
            "evaluation_usd": MAX_EVAL_COST_USD,
            "preflight_and_aggregate_usd": MAX_CPU_ONLY_COST_USD,
            "gate_usd": MAX_GATE_COST_USD,
            "approved_cap_usd": BUDGET_CAP_USD,
        },
        "authority": {
            "gpu_execution_authorized_by_this_receipt": False,
            "retry_authorized": False,
            "final_reset_access_authorized": False,
            "promotion_authorized": False,
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    workspace.commit()
    return payload


@app.function(
    image=image, gpu=TRAIN_GPU, cpu=TRAIN_CPU_CORES, memory=TRAIN_MEMORY_MIB,
    timeout=TRAIN_TIMEOUT_SECONDS, retries=0, single_use_containers=True,
    volumes={WORKSPACE: workspace},
)
def train_segment(arm: str, segment: int) -> dict[str, Any]:
    _validate_arm_segment(arm, segment)
    terminal = _terminal_path(arm, segment)
    run_dir = TRAINING_RESULTS_ROOT / "d1" / _run_id(arm, segment)
    if terminal.exists() or run_dir.exists():
        raise RuntimeError("create-only training destination already exists")
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed_before_or_during_training",
        "arm": arm,
        "segment": segment,
        "seed": 2026,
        "authority": {
            "retry_authorized": False,
            "additional_run_authorized": False,
            "final_reset_access_authorized": False,
            "promotion_authorized": False,
        },
        "resource_ceiling": {
            "timeout_seconds": TRAIN_TIMEOUT_SECONDS,
            "rate_usd_per_second": TRAIN_RATE_USD_PER_SECOND,
            "maximum_usd": TRAIN_TIMEOUT_SECONDS * TRAIN_RATE_USD_PER_SECOND,
        },
    }
    failure: BaseException | None = None
    try:
        selected = _verify_selected_actor()
        spec = SEGMENTS[segment]
        if segment == 1:
            resume_dir = "null"
            actor = STAGED_ACTOR
        else:
            source = _checkpoint_path(arm, 1)
            source_receipt = json.loads(_terminal_path(arm, 1).read_text())
            if source_receipt.get("status") != "complete_valid_training_segment":
                raise RuntimeError("segment 1 terminal receipt is not complete")
            receipt["resume_source"] = _verify_checkpoint(source, 50)
            resume_dir = str(source)
            actor = STAGED_ACTOR
        _ensure_ray_head()
        environment = {
            **_base_environment(),
            "STAGE1_CHECKPOINT": str(actor),
            "GPU_HOURLY_PRICE_USD": f"{TRAIN_RATE_USD_PER_SECOND * 3600:.6f}",
            "CANDIDATE_RESUME_DIR": resume_dir,
            "CANDIDATE_MAX_STEPS": str(spec["max_steps"]),
            "CANDIDATE_SAVE_INTERVAL": str(spec["save_interval"]),
        }
        process = subprocess.run(
            [f"{RLINF_HOME}/.venv/bin/python", "-m", "agent.d1_launcher",
             "--config", f"{PROJECT_ROOT}/configs/d1/e2_engineering_{arm}_seed2026.yaml",
             "--results-root", str(TRAINING_RESULTS_ROOT), "--run-id",
             _run_id(arm, segment), "--execute", "--acknowledge-paid-run"],
            cwd=PROJECT_ROOT, env=environment, check=False,
        )
        receipt["exit_code"] = process.returncode
        if process.returncode:
            raise RuntimeError(f"training exited {process.returncode}")
        receipt["selected_actor"] = selected
        receipt["checkpoint"] = _verify_checkpoint(
            _checkpoint_path(arm, segment), spec["max_steps"]
        )
        receipt["status"] = "complete_valid_training_segment"
    except BaseException as error:
        failure = error
        receipt["error"] = bounded_error(error)
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        terminal.parent.mkdir(parents=True, exist_ok=True)
        with terminal.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        workspace.commit()
    if failure is not None:
        raise RuntimeError("E2 training segment failed; inspect terminal receipt") from None
    return receipt


@app.function(
    image=image, gpu=EVAL_GPU, cpu=EVAL_CPU_CORES, memory=EVAL_MEMORY_MIB,
    timeout=EVAL_TIMEOUT_SECONDS, retries=0, single_use_containers=True,
    volumes={WORKSPACE: workspace},
)
def evaluate_shard(arm: str, shard_index: int) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError("arm must be control or candidate")
    shard = shard_spec(shard_index)
    source = _checkpoint_path(arm, 2)
    training_receipt = json.loads(_terminal_path(arm, 2).read_text())
    if training_receipt.get("status") != "complete_valid_training_segment":
        raise RuntimeError("final training segment is not complete")
    checkpoint = _verify_checkpoint(source, 100)
    actual_contract = evaluator_contract_sha256(Path(PROJECT_ROOT))
    if actual_contract != EVALUATOR_CONTRACT_SHA256:
        raise RuntimeError("evaluator contract source identity mismatch")
    run_id = f"g0-e2-{arm}-seed2026-eval-shard{shard.index}-v1"
    run_dir = EVALUATION_RESULTS_ROOT / "d1" / run_id
    terminal = RESULTS_ROOT / f"evaluation-{arm}-shard{shard.index}-terminal.json"
    if terminal.exists() or run_dir.exists():
        raise RuntimeError("create-only evaluation destination already exists")
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed_before_or_during_development_shard",
        "arm": arm,
        "seed": 2026,
        "shard": shard.to_dict(),
        "checkpoint": {
            "step": 100,
            "sha256": checkpoint["actor_weights_sha256"],
            "version_id": f"modal-volume:{_run_id(arm, 2)}",
        },
        "reset_set_sha256": DEVELOPMENT_RESET_SHA256,
        "evaluator_source_sha256": EVALUATOR_CONTRACT_SHA256,
        "authority": {
            "additional_shard_authorized": False,
            "checkpoint_retry_authorized": False,
            "final_reset_access_authorized": False,
            "policy_promotion_authorized": False,
        },
    }
    failure: BaseException | None = None
    try:
        environment = {
            **_base_environment(),
            "RLINF_HOME": RLINF_HOME,
            "QUALIA_PROJECT_ROOT": PROJECT_ROOT,
            "STAGE1_CHECKPOINT": str(source / "actor"),
            "DEVELOPMENT_RESET_PATH": DEVELOPMENT_RESETS,
            "DEVELOPMENT_RESET_SHA256": DEVELOPMENT_RESET_SHA256,
            "QUALIA_DEVELOPMENT_RESET_OFFSET": str(shard.offset),
            "QUALIA_DEVELOPMENT_RESET_COUNT": str(shard.count),
            "GPU_HOURLY_PRICE_USD": f"{EVAL_RATE_USD_PER_SECOND * 3600:.6f}",
            "PYTHONPATH": f"{E1_RUNTIME_ROOT}:{PROJECT_ROOT}:{RLINF_HOME}",
            "QUALIA_E1_FROZEN_DEVELOPMENT": "1",
        }
        process = subprocess.run(
            [f"{RLINF_HOME}/.venv/bin/python", "-m", "agent.d1_launcher",
             "--config", f"{PROJECT_ROOT}/configs/d1/e1_checkpoint_evaluation_shard.yaml",
             "--results-root", str(EVALUATION_RESULTS_ROOT), "--run-id", run_id,
             "--execute", "--acknowledge-paid-run"],
            cwd=PROJECT_ROOT, env=environment, check=False,
        )
        receipt["exit_code"] = process.returncode
        manifest = run_dir / "manifest.json"
        log = run_dir / "run.log"
        if manifest.is_file():
            receipt["manifest"] = json.loads(manifest.read_text())
        if process.returncode:
            raise RuntimeError(f"evaluation exited {process.returncode}")
        if not log.is_file():
            raise RuntimeError("evaluation log is missing")
        receipt["metric"] = parse_final_eval_metrics(log.read_text(errors="replace"))
        receipt["status"] = "complete_valid_development_shard"
    except BaseException as error:
        failure = error
        receipt["error"] = bounded_error(error)
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        terminal.parent.mkdir(parents=True, exist_ok=True)
        with terminal.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        workspace.commit()
    if failure is not None:
        raise RuntimeError("E2 development shard failed; inspect terminal receipt") from None
    return receipt


@app.function(image=image, cpu=2, memory=4096, timeout=600,
              retries=0, single_use_containers=True, volumes={WORKSPACE: workspace})
def aggregate() -> dict[str, Any]:
    output = RESULTS_ROOT / "comparison.json"
    report = RESULTS_ROOT / "demo-report.md"
    if output.exists() or report.exists():
        raise RuntimeError("create-only aggregate destination already exists")
    aggregates: dict[str, Any] = {}
    for arm in ARMS:
        receipts = [
            json.loads((RESULTS_ROOT / f"evaluation-{arm}-shard{i}-terminal.json").read_text())
            for i in range(4)
        ]
        aggregates[arm] = aggregate_shard_receipts(receipts)
    control = aggregates["control"]["metric"]
    candidate = aggregates["candidate"]["metric"]
    payload = {
        "schema_version": 1,
        "status": "complete_engineering_comparison",
        "claim_scope": "single-seed development engineering evidence; not a scientific E2 conclusion",
        "seed": 2026,
        "arms": aggregates,
        "observed_success_once_delta": candidate["success_once"] - control["success_once"],
        "decision": "inconclusive_single_seed_no_promotion",
        "authority": {
            "additional_runs_authorized": False,
            "final_reset_access_authorized": False,
            "policy_promotion_authorized": False,
        },
        "recording": {
            "manifests_logs_checkpoints_receipts_retained": True,
            "rollout_video_recorded": False,
            "rollout_video_reason": "Modal multiprocess adapter flush_video is intentionally a no-op",
        },
    }
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    report.write_text(
        "# E2 engineering-gate demo\n\n"
        "This is single-seed development evidence, not a promotion decision.\n\n"
        "| Arm | Successes | Trajectories | Success rate |\n"
        "|---|---:|---:|---:|\n"
        f"| Control | {control['num_successes']} | 256 | {control['success_once']:.6f} |\n"
        f"| Candidate | {candidate['num_successes']} | 256 | {candidate['success_once']:.6f} |\n\n"
        f"Observed candidate-control delta: `{payload['observed_success_once_delta']:.6f}`.\n\n"
        "Decision: `inconclusive_single_seed_no_promotion`.\n",
        encoding="utf-8",
    )
    workspace.commit()
    return payload


@app.local_entrypoint()
def main(target: str, arm: str = "", segment: int = 0, shard_index: int = -1) -> None:
    if target == "preflight":
        if arm or segment or shard_index != -1:
            raise ValueError("preflight accepts no arm, segment, or shard")
        call = preflight.spawn()
    elif target == "train":
        _validate_arm_segment(arm, segment)
        call = train_segment.spawn(arm, segment)
    elif target == "evaluate":
        if arm not in ARMS:
            raise ValueError("arm must be control or candidate")
        shard_spec(shard_index)
        call = evaluate_shard.spawn(arm, shard_index)
    elif target == "aggregate":
        if arm or segment or shard_index != -1:
            raise ValueError("aggregate accepts no arm, segment, or shard")
        call = aggregate.spawn()
    else:
        raise ValueError("target must be preflight, train, evaluate, or aggregate")
    print(json.dumps({
        "app_name": APP_NAME,
        "function_call_id": call.object_id,
        "status": "launched_detached",
        "target": target,
        "arm": arm or None,
        "segment": segment or None,
        "shard_index": shard_index if shard_index >= 0 else None,
        "maximum_gate_resource_cost_usd": round(MAX_GATE_COST_USD, 6),
        "budget_cap_usd": BUDGET_CAP_USD,
    }, indent=2, sort_keys=True))
