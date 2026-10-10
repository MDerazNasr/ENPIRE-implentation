"""Credential-independent v10 replacement evaluation for E1 shards 1 through 3.

The exact checkpoint must first be staged and verified by the separate CPU
staging app. This GPU app has no AWS secret, cannot download a checkpoint, and
cannot duplicate the already-complete shard 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import modal

from supervisor.e1_sharded_evaluation import (
    evaluator_contract_sha256,
    parse_final_eval_metrics,
    shard_spec,
)
from e1_staged_checkpoint_runtime import (
    bounded_error,
    load_valid_stage_receipt,
    sha256_file,
)


APP_NAME = "enpire-g0-e1-l40s-sharded-evaluation-v5"
GPU = "L40S"
CPU_CORES = 16
MEMORY_MIB = 96 * 1024
FUNCTION_TIMEOUT_SECONDS = 3600
MAX_REMAINING_SHARD_GPU_RUNTIME_COST_USD = "5.853600"
PROJECT_ROOT = "/opt/qualia"
E1_RUNTIME_ROOT = f"{PROJECT_ROOT}/e1_runtime"
RLINF_HOME = "/opt/RLinf"
WORKSPACE = "/workspace"
RESULTS_ROOT = f"{WORKSPACE}/e1-l40s-results"
RUN_REVISION = 10
ALLOWED_SHARDS = (1, 2, 3)
NORM_STATS = f"{PROJECT_ROOT}/norm_stats.json"
DEVELOPMENT_RESETS = f"{PROJECT_ROOT}/development-resets.json"
DEVELOPMENT_RESET_FINGERPRINT = (
    "e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161"
)
EVALUATOR_CONTRACT_SHA256 = "ee979edef79b84440bfac0b6f0a787315af71b69252be64cfea06465935dd256"
BASE_IMAGE_ID = "im-66ku0dbczWNQDgPWv97XNc"
STAGE_RECEIPT = Path(RESULTS_ROOT) / "step-2000-stage-v4-terminal.json"
STAGED_CHECKPOINT = Path(
    f"{WORKSPACE}/e1-checkpoints/step-2000-stage-v4/"
    "actor/model_state_dict/full_weights.pt"
)
CHECKPOINT = {
    "sha256": "4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146",
    "size_bytes": 10015912662,
    "step": 2000,
    "version_id": "LvdNrl8pPsbD6s9tdJ8.__.1V2B00077",
}
GPU_PRICE_USD_PER_HOUR = "1.951200"


app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "g0-e1-v10"})
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)
image = (
    modal.Image.from_id(BASE_IMAGE_ID)
    .entrypoint([])
    .env({"PYTHONPATH": f"{E1_RUNTIME_ROOT}:{PROJECT_ROOT}:{RLINF_HOME}"})
    .pip_install("modal==1.5.4")
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("e1_runtime", E1_RUNTIME_ROOT, copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_dir("supervisor", f"{PROJECT_ROOT}/supervisor", copy=True)
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


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_CORES,
    memory=MEMORY_MIB,
    ephemeral_disk=512 * 1024,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    retries=0,
    single_use_containers=True,
    volumes={WORKSPACE: workspace},
)
def evaluate_shard(shard_index: int) -> dict[str, object]:
    shard = shard_spec(shard_index)
    if shard.index not in ALLOWED_SHARDS:
        raise RuntimeError("v10 permits only replacement shards 1 through 3")
    actual_contract_sha256 = evaluator_contract_sha256(Path(PROJECT_ROOT))
    if actual_contract_sha256 != EVALUATOR_CONTRACT_SHA256:
        raise RuntimeError("evaluator contract source identity mismatch")

    run_id = f"g0-e1-l40s-step-2000-v{RUN_REVISION}-shard-{shard.index}"
    run_dir = Path(RESULTS_ROOT) / "d1" / run_id
    receipt_path = (
        Path(RESULTS_ROOT)
        / f"step-2000-v{RUN_REVISION}-shard-{shard.index}-terminal.json"
    )
    if run_dir.exists() or receipt_path.exists():
        raise RuntimeError("create-only v10 shard destination already exists")

    started = time.monotonic()
    failure: BaseException | None = None
    receipt: dict[str, object] = {
        "authority": {
            "additional_shard_authorized": False,
            "checkpoint_retry_authorized": False,
            "e2_authorized": False,
            "policy_promotion_authorized": False,
        },
        "checkpoint": CHECKPOINT,
        "claim_scope": "one development shard only; no aggregation, selection, or promotion",
        "evaluator_source_sha256": EVALUATOR_CONTRACT_SHA256,
        "exit_code": None,
        "manifest": None,
        "metric": None,
        "reset_set_sha256": DEVELOPMENT_RESET_FINGERPRINT,
        "schema_version": 1,
        "shard": shard.to_dict(),
        "status": "failed_before_or_during_development_shard",
    }
    try:
        stage_receipt = load_valid_stage_receipt(
            STAGE_RECEIPT,
            STAGED_CHECKPOINT,
            expected_checkpoint=CHECKPOINT,
        )
        receipt["stage_receipt_sha256"] = sha256_file(STAGE_RECEIPT)
        receipt["staged_checkpoint_status"] = stage_receipt["status"]
        environment = {
            **os.environ,
            "RLINF_HOME": RLINF_HOME,
            "QUALIA_PROJECT_ROOT": PROJECT_ROOT,
            "STAGE1_CHECKPOINT": str(STAGED_CHECKPOINT.parents[1]),
            "NORM_STATS_PATH": NORM_STATS,
            "DEVELOPMENT_RESET_PATH": DEVELOPMENT_RESETS,
            "DEVELOPMENT_RESET_SHA256": DEVELOPMENT_RESET_FINGERPRINT,
            "QUALIA_DEVELOPMENT_RESET_OFFSET": str(shard.offset),
            "QUALIA_DEVELOPMENT_RESET_COUNT": str(shard.count),
            "WANDB_PROJECT": "qualia-rlt-d1",
            "WANDB_MODE": "offline",
            "WANDB_DIR": f"{WORKSPACE}/wandb",
            "HF_HOME": f"{WORKSPACE}/cache/huggingface",
            "HF_DATASETS_CACHE": f"{WORKSPACE}/cache/huggingface/datasets",
            "GPU_HOURLY_PRICE_USD": GPU_PRICE_USD_PER_HOUR,
            "PYTHONPATH": f"{E1_RUNTIME_ROOT}:{PROJECT_ROOT}:{RLINF_HOME}",
            "QUALIA_MODAL_THREADS_PER_WORKER": "1",
            "QUALIA_E1_FROZEN_DEVELOPMENT": "1",
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.run(
            [
                f"{RLINF_HOME}/.venv/bin/python",
                "-m",
                "agent.d1_launcher",
                "--config",
                f"{PROJECT_ROOT}/configs/d1/e1_checkpoint_evaluation_shard.yaml",
                "--results-root",
                RESULTS_ROOT,
                "--run-id",
                run_id,
                "--execute",
                "--acknowledge-paid-run",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
        )
        receipt["exit_code"] = process.returncode
        manifest_path = run_dir / "manifest.json"
        log_path = run_dir / "run.log"
        if manifest_path.is_file():
            receipt["manifest"] = json.loads(manifest_path.read_text())
        if process.returncode:
            raise RuntimeError(f"checkpoint evaluation exited {process.returncode}")
        if not log_path.is_file():
            raise RuntimeError("checkpoint evaluation log is missing")
        receipt["metric"] = parse_final_eval_metrics(
            log_path.read_text(errors="replace")
        )
        receipt["status"] = "complete_valid_development_shard"
    except BaseException as error:
        failure = error
        receipt["error"] = bounded_error(error)
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with receipt_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        workspace.commit()
    if failure is not None:
        raise RuntimeError("v10 shard failed; inspect terminal receipt") from None
    return receipt


@app.local_entrypoint()
def main(shard_index: int, acknowledge_detached_run: bool = False):
    shard = shard_spec(shard_index)
    if shard.index not in ALLOWED_SHARDS:
        raise RuntimeError("v10 permits only replacement shards 1 through 3")
    if not acknowledge_detached_run:
        raise RuntimeError("detached launch acknowledgement is required")
    call = evaluate_shard.spawn(shard.index)
    print(
        json.dumps(
            {
                "app_name": APP_NAME,
                "function_call_id": call.object_id,
                "max_remaining_shard_gpu_runtime_cost_usd": (
                    MAX_REMAINING_SHARD_GPU_RUNTIME_COST_USD
                ),
                "run_revision": RUN_REVISION,
                "shard": shard.to_dict(),
                "status": "launched_detached",
                "step": 2000,
            },
            indent=2,
            sort_keys=True,
        )
    )
