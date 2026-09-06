#!/usr/bin/env python3
"""Fixed F2 rehearsal for the user-selected Lambda H100 SXM5 host.

The script accepts no arguments. It derives two H100-specific profiles from
the reviewed F2 profiles, changing only runtime provenance, and then runs the
two full-shape steps plus the strict two-process resume micro-gate.
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


PROJECT_ROOT = Path("/opt/qualia")
RLINF_HOME = Path("/opt/RLinf")
WORKSPACE = Path("/workspace")
RESULTS_ROOT = WORKSPACE / "results"
GENERATED_ROOT = WORKSPACE / "f2-h100-generated-configs"
ACTOR = WORKSPACE / "checkpoints/stage1-step-500-actor"
NORM_STATS = PROJECT_ROOT / "configs/d1/assets/norm_stats.json"
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
EXPECTED_ACTOR_SIZE = 10_015_912_759
EXPECTED_ACTOR_SHA256 = "b5bf9384d7e2da674125fb04b26ed8a391bdb0a0a85cf16c71fd02424ee363f3"
EXPECTED_NORM_SHA256 = "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
EXPECTED_GPU = "NVIDIA H100 80GB HBM3"
MINIMUM_GPU_MEMORY_BYTES = 80_000_000_000
INSTANCE_PRICE_USD_PER_HOUR = 4.29
RUNTIME_CONTRACT_ID = "enpire-h100-sxm5-rehearsal-runtime-v1"
CONTROL_RUN_ID = "f2-h100-sxm5-control-seed2026-attempt2"
CANDIDATE_RUN_ID = "f2-h100-sxm5-candidate-seed2026-attempt2"
RESUME_SOURCE_RUN_ID = "f2-h100-sxm5-resume-source-seed2026-attempt2"
RESUME_CONTINUATION_RUN_ID = "f2-h100-sxm5-resume-continuation-seed2026-attempt2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _environment() -> dict[str, str]:
    return {
        **os.environ,
        "RLINF_HOME": str(RLINF_HOME),
        "MODAL_ADAPTER_ROOT": str(PROJECT_ROOT),
        "STAGE1_CHECKPOINT": str(ACTOR),
        "NORM_STATS_PATH": str(NORM_STATS),
        "WANDB_PROJECT": "qualia-rlt-d1",
        "WANDB_MODE": "offline",
        "WANDB_DIR": str(WORKSPACE / "wandb"),
        "HF_HOME": str(WORKSPACE / "cache/huggingface"),
        "HF_DATASETS_CACHE": str(WORKSPACE / "cache/huggingface/datasets"),
        "D1_SEED": "2026",
        "GPU_HOURLY_PRICE_USD": str(INSTANCE_PRICE_USD_PER_HOUR),
        "EMBODIED_PATH": str(RLINF_HOME / "examples/embodiment"),
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
    actor_file = ACTOR / "model_state_dict/full_weights.pt"
    if not actor_file.is_file() or actor_file.stat().st_size != EXPECTED_ACTOR_SIZE:
        raise RuntimeError("canonical Stage-1 actor is missing or has wrong size")
    actor_sha = _sha256(actor_file)
    if actor_sha != EXPECTED_ACTOR_SHA256:
        raise RuntimeError("canonical Stage-1 actor hash mismatch")
    norm_sha = _sha256(NORM_STATS)
    if norm_sha != EXPECTED_NORM_SHA256:
        raise RuntimeError("normalization-stat hash mismatch")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=RLINF_HOME, text=True
    ).strip()
    if revision != RLINF_COMMIT:
        raise RuntimeError("RLinf revision mismatch")
    vulkan = subprocess.run(
        ["vulkaninfo", "--summary"],
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    if vulkan.returncode != 0 or "llvmpipe" not in vulkan.stdout.lower():
        raise RuntimeError("Mesa llvmpipe Vulkan gate failed")
    source = """
import json, platform, torch
from importlib.metadata import version
p = torch.cuda.get_device_properties(0)
x = torch.tensor([2.0], device='cuda').square()
torch.cuda.synchronize()
print(json.dumps({
    'python': platform.python_version(), 'torch': torch.__version__,
    'cuda': torch.version.cuda, 'gpu': p.name,
    'gpu_memory_bytes': p.total_memory, 'cuda_probe': x.item(),
    'maniskill': version('mani-skill'), 'sapien': version('sapien')
}))
"""
    observed = json.loads(
        subprocess.check_output(
            [str(RLINF_HOME / ".venv/bin/python"), "-c", source],
            text=True,
            env=_environment(),
        )
    )
    expected = {
        "python": "3.11.14",
        "torch": "2.8.0+cu128",
        "cuda": "12.8",
        "gpu": EXPECTED_GPU,
        "cuda_probe": 4.0,
        "maniskill": "3.0.0b22",
        "sapien": "3.0.1",
    }
    for key, value in expected.items():
        if observed.get(key) != value:
            raise RuntimeError(f"runtime {key} mismatch: {observed.get(key)!r}")
    if int(observed["gpu_memory_bytes"]) < MINIMUM_GPU_MEMORY_BYTES:
        raise RuntimeError("H100 memory is below the amended minimum")
    return {
        "runtime_contract_id": RUNTIME_CONTRACT_ID,
        "actor_size_bytes": EXPECTED_ACTOR_SIZE,
        "actor_sha256": actor_sha,
        "norm_stats_sha256": norm_sha,
        "rlinf_commit": revision,
        "vulkan": "Mesa llvmpipe",
        "observed_runtime": observed,
    }


def _derived_profile(source_name: str, arm: str) -> Path:
    source_path = PROJECT_ROOT / "configs/d1" / source_name
    profile = json.loads(source_path.read_text())
    expected_arm = "control" if "control" in source_name else "candidate"
    if arm != expected_arm or profile["condition"] != arm:
        raise RuntimeError("source profile arm mismatch")
    provenance = profile["runtime_provenance"]
    if provenance["runtime_contract_id"] != "enpire-matched-scientific-runtime-v1":
        raise RuntimeError("unexpected source runtime contract")
    if provenance["gpu"] != "RTX PRO 6000 Blackwell Server Edition":
        raise RuntimeError("unexpected source GPU provenance")
    provenance["runtime_contract_id"] = RUNTIME_CONTRACT_ID
    provenance["gpu"] = EXPECTED_GPU
    provenance["provider"] = "Lambda Cloud"
    provenance["instance_id"] = "7160d3af448d4925b149ab6e9655344d"
    provenance["region"] = "Georgia, USA"
    provenance["runtime_amendment"] = (
        "user-selected H100 SXM5 replacement; valid for F2 engineering rehearsal "
        "only until the live result supports or rejects a new matched runtime"
    )
    profile["experiment_id"] = f"d1-f2-h100-sxm5-{arm}-rehearsal"
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    target = GENERATED_ROOT / f"{arm}.yaml"
    target.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    return target


def _derived_resume_profile() -> Path:
    source_path = PROJECT_ROOT / "configs/d1/stage2_6_schedule_resume_gate.yaml"
    profile = json.loads(source_path.read_text())
    provenance = profile["runtime_provenance"]
    if provenance["candidate_gpu"] != "RTX PRO 6000 Blackwell Server Edition":
        raise RuntimeError("unexpected resume-gate source GPU provenance")
    provenance["candidate_gpu"] = EXPECTED_GPU
    provenance["runtime_contract_id"] = RUNTIME_CONTRACT_ID
    provenance["provider"] = "Lambda Cloud"
    provenance["instance_id"] = "7160d3af448d4925b149ab6e9655344d"
    provenance["region"] = "Georgia, USA"
    provenance["comparison_limitation"] = (
        "schedule-resume integration gate on the user-selected H100 SXM5; "
        "not a scientific condition result"
    )
    profile["experiment_id"] = "d1-f2-h100-sxm5-schedule-resume-gate"
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    target = GENERATED_ROOT / "resume.yaml"
    target.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    return target


def _ensure_ray_head() -> None:
    ray = str(RLINF_HOME / ".venv/bin/ray")
    status = subprocess.run(
        [ray, "status"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if status.returncode == 0:
        return
    completed = subprocess.run(
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
    print(completed.stdout, flush=True)
    if completed.returncode != 0:
        raise RuntimeError("explicit Ray head failed")
    subprocess.run([ray, "status"], check=True)


def _run_profile(config: Path, run_id: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
    run_dir = RESULTS_ROOT / "d1" / run_id
    if run_dir.exists():
        raise RuntimeError(f"fixed F2 run directory already exists: {run_dir}")
    command = [
        str(RLINF_HOME / ".venv/bin/python"),
        "-m",
        "agent.d1_launcher",
        "--config",
        str(config),
        "--results-root",
        str(RESULTS_ROOT),
        "--run-id",
        run_id,
        "--execute",
        "--acknowledge-paid-run",
    ]
    environment = _environment()
    if extra:
        environment.update(extra)
    started = time.monotonic()
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=environment)
    if completed.returncode != 0:
        raise RuntimeError(f"profile failed with exit {completed.returncode}")
    return {
        "run_id": run_id,
        "config_path": str(config),
        "config_sha256": _sha256(config),
        "elapsed_seconds": time.monotonic() - started,
        "manifest": json.loads((run_dir / "manifest.json").read_text()),
    }


def _checkpoint(run_id: str, step: int) -> Path:
    return (
        RESULTS_ROOT
        / "d1"
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


def _resume_gate(profile: Path) -> dict[str, Any]:
    from agent.metrics import parse_metrics

    source_run = _run_profile(
        profile,
        RESUME_SOURCE_RUN_ID,
        {
            "SCHEDULE_GATE_MAX_STEPS": "1",
            "SCHEDULE_GATE_SAVE_INTERVAL": "1",
            "SCHEDULE_GATE_RESUME_DIR": "null",
        },
    )
    source = _audit_checkpoint(RESUME_SOURCE_RUN_ID, 1)
    source_state = source["rlt_schedule_state"]
    continuation_run = _run_profile(
        profile,
        RESUME_CONTINUATION_RUN_ID,
        {
            "SCHEDULE_GATE_MAX_STEPS": "2",
            "SCHEDULE_GATE_SAVE_INTERVAL": "2",
            "SCHEDULE_GATE_RESUME_DIR": str(_checkpoint(RESUME_SOURCE_RUN_ID, 1)),
        },
    )
    continuation = _audit_checkpoint(RESUME_CONTINUATION_RUN_ID, 2)
    continuation_state = continuation["rlt_schedule_state"]
    source_log = (RESULTS_ROOT / "d1" / RESUME_SOURCE_RUN_ID / "run.log").read_text()
    continuation_log = (
        RESULTS_ROOT / "d1" / RESUME_CONTINUATION_RUN_ID / "run.log"
    ).read_text()
    source_metrics = parse_metrics(source_log)
    continuation_metrics = parse_metrics(continuation_log)
    checks = {
        "source_update_counter": source_state["counters"]["update_step"] == 1,
        "continued_update_counter": continuation_state["counters"]["update_step"] == 2,
        "schedule_fingerprint_equal": source_state["schedule_fingerprint"]
        == continuation_state["schedule_fingerprint"],
        "transitions_non_regressing": continuation_state["counters"]["total_transitions_added"]
        >= source_state["counters"]["total_transitions_added"],
        "replay_rng_present": continuation_state["replay_generator_state_present"],
        "restore_marker_present": "QUALIA_RLT_RESUME_STATE=" in continuation_log,
        "source_metric_starts_zero": source_metrics.get("rlt/update_step") == [0.0],
        "continuation_metric_starts_one": continuation_metrics.get("rlt/update_step") == [1.0],
        "source_warmup": source_metrics.get("actor/actor_weight_in_warmup") == [1.0],
        "continuation_online": continuation_metrics.get("actor/actor_weight_in_warmup") == [0.0],
    }
    if not all(checks.values()):
        raise RuntimeError(f"resume gate failed: {checks}")
    return {
        "checks": checks,
        "source_run": source_run,
        "source_checkpoint": source,
        "continuation_run": continuation_run,
        "continuation_checkpoint": continuation,
        "known_limit": "simulator state is not claimed bitwise-identical across processes",
    }


def main() -> int:
    started = time.monotonic()
    inputs = _verify_runtime_and_inputs()
    control_config = _derived_profile("f2_control_rehearsal.yaml", "control")
    candidate_config = _derived_profile("f2_candidate_rehearsal.yaml", "candidate")
    resume_config = _derived_resume_profile()
    control_json = json.loads(control_config.read_text())
    candidate_json = json.loads(candidate_config.read_text())
    control_science = control_json["scientific_values"]
    candidate_science = candidate_json["scientific_values"]
    diff = {
        key: [control_science.get(key), candidate_science.get(key)]
        for key in sorted(set(control_science) | set(candidate_science))
        if control_science.get(key) != candidate_science.get(key)
    }
    expected_diff = {
        "online_bc_weight": [2.5, 2],
        "warmup_bc_weight": [7, 5.6],
    }
    if diff != expected_diff:
        raise RuntimeError(f"derived arm science differs outside intervention: {diff}")
    _ensure_ray_head()
    control = _run_profile(control_config, CONTROL_RUN_ID)
    control["checkpoint"] = _audit_checkpoint(CONTROL_RUN_ID, 1)
    candidate = _run_profile(candidate_config, CANDIDATE_RUN_ID)
    candidate["checkpoint"] = _audit_checkpoint(CANDIDATE_RUN_ID, 1)
    resume = _resume_gate(resume_config)
    elapsed = time.monotonic() - started
    result = {
        "schema_version": 1,
        "status": "pass",
        "claim_scope": "H100 SXM5 F2 engineering rehearsal only; no policy comparison or promotion",
        "inputs": inputs,
        "scientific_diff": diff,
        "control": control,
        "candidate": candidate,
        "resume": resume,
        "elapsed_seconds": elapsed,
        "instance_price_usd_per_hour": INSTANCE_PRICE_USD_PER_HOUR,
        "in_container_elapsed_cost_usd": elapsed / 3600 * INSTANCE_PRICE_USD_PER_HOUR,
        "segmentation_decision_basis": "allow only identical predeclared step-boundary segmentation with native checkpoint plus strict sidecar; simulator state is not bitwise continuous",
    }
    output = RESULTS_ROOT / "runtime-qualification/f2-h100-sxm5/attempt-2.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"ENPIRE_F2_H100_RESULT={json.dumps(result, sort_keys=True)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
