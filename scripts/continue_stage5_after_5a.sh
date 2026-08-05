#!/usr/bin/env bash
set -euo pipefail

# Guarded Stage-5A -> Stage-5B continuation for a single, already-provisioned
# graphics-capable GPU pod. The script never launches Stage 6.

: "${RLINF_HOME:?Set RLINF_HOME to the pinned RLinf checkout}"
: "${MODEL_PATH:?Set MODEL_PATH to the frozen pi0.5 directory}"
: "${NORM_STATS_PATH:?Set NORM_STATS_PATH to the matched norm_stats.json}"
: "${STAGE5A_LAUNCHER_PID:?Set the active Stage-5A launcher PID}"
: "${STAGE5A_PRESERVER_PID:?Set the active actor-preservation watcher PID}"

PROJECT_ROOT="${PROJECT_ROOT:-/root/qualia/ENPIRE}"
RESULTS_ROOT="${RESULTS_ROOT:-/dev/shm/qualia-stage5/results}"
STAGE5A_RUN_ID="${STAGE5A_RUN_ID:-stage5a-l40s-recovery-250-seed2026-20260804}"
STAGE5B_RUN_ID="${STAGE5B_RUN_ID:-stage5b-l40s-batched16-probe-seed2026-20260804}"
PERSISTENT_ROOT="${PERSISTENT_ROOT:-/workspace}"
GPU_HOURLY_PRICE_USD="${GPU_HOURLY_PRICE_USD:-0.99}"
WANDB_PROJECT="${WANDB_PROJECT:-qualia-rlt-d1}"
D1_SEED="${D1_SEED:-2026}"

STAGE5A_RUN_DIR="${RESULTS_ROOT}/d1/${STAGE5A_RUN_ID}"
STAGE5B_RUN_DIR="${RESULTS_ROOT}/d1/${STAGE5B_RUN_ID}"
STAGE5A_MANIFEST="${STAGE5A_RUN_DIR}/manifest.json"
STAGE5B_MANIFEST="${STAGE5B_RUN_DIR}/manifest.json"
STAGE1_CHECKPOINT="${PERSISTENT_ROOT}/qualia-checkpoints/stage5a-step250/actor"
STAGE1_WEIGHTS="${STAGE1_CHECKPOINT}/model_state_dict/full_weights.pt"
EVIDENCE_ROOT="${PERSISTENT_ROOT}/qualia-evidence"
STATUS_LOG="${EVIDENCE_ROOT}/stage5-continuation.log"
STATUS_FILE="${EVIDENCE_ROOT}/stage5-continuation.status"

mkdir -p "${EVIDENCE_ROOT}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${STATUS_LOG}"
}

finish() {
  code=$?
  if (( code == 0 )); then
    printf 'complete\n' >"${STATUS_FILE}"
    log "Stage 5A and Stage 5B continuation completed; Stage 6 was not launched."
  else
    printf 'failed exit_code=%s\n' "${code}" >"${STATUS_FILE}"
    log "Continuation stopped at a failed gate (exit ${code}); Stage 6 was not launched."
  fi
}
trap finish EXIT

wait_for_pid() {
  pid="$1"
  label="$2"
  log "Waiting for ${label} (PID ${pid})."
  while kill -0 "${pid}" 2>/dev/null; do
    sleep 30
  done
  log "${label} exited."
}

require_complete_manifest() {
  manifest="$1"
  label="$2"
  "${RLINF_HOME}/.venv/bin/python" - "${manifest}" "${label}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
label = sys.argv[2]
data = json.loads(path.read_text())
if data.get("status") != "complete" or data.get("exit_code") != 0:
    raise SystemExit(f"{label} did not complete cleanly: {data.get('status')=} {data.get('exit_code')=}")
print(f"{label} manifest complete: cost=${data.get('run_cost_usd', 0):.6f}")
PY
}

copy_compact_evidence() {
  run_dir="$1"
  destination="$2"
  mkdir -p "${destination}"
  for name in manifest.json command.sh resources.jsonl run.log; do
    if [[ -f "${run_dir}/${name}" ]]; then
      cp "${run_dir}/${name}" "${destination}/${name}"
    fi
  done
  if [[ -d "${run_dir}/wandb" ]]; then
    rm -rf "${destination}/wandb"
    cp -a "${run_dir}/wandb" "${destination}/wandb"
  fi
}

wait_for_pid "${STAGE5A_LAUNCHER_PID}" "Stage 5A launcher"
wait_for_pid "${STAGE5A_PRESERVER_PID}" "Stage 5A preservation watcher"
require_complete_manifest "${STAGE5A_MANIFEST}" "Stage 5A"

weights_size="$(stat -c %s "${STAGE1_WEIGHTS}")"
if (( weights_size < 9000000000 )); then
  log "Final Stage 5A actor is unexpectedly small (${weights_size} bytes)."
  exit 1
fi
weights_sha="$(sha256sum "${STAGE1_WEIGHTS}" | awk '{print $1}')"
log "Verified persistent Stage 5A actor: size=${weights_size} sha256=${weights_sha}."

copy_compact_evidence "${STAGE5A_RUN_DIR}" "${EVIDENCE_ROOT}/stage5a-full"

stage5a_checkpoints="${STAGE5A_RUN_DIR}/maniskill_rlt_stage1_sft_openpi_pi05/checkpoints"
if [[ -d "${stage5a_checkpoints}" ]]; then
  log "Reclaiming verified Stage 5A distributed optimizer checkpoint from RAM."
  rm -rf "${stage5a_checkpoints}"
fi

if pgrep -f 'raylet|gcs_server' >/dev/null 2>&1; then
  log "Stopping stale Ray services after the completed Stage 5A process."
  "${RLINF_HOME}/.venv/bin/ray" stop --force || true
fi

log "Running CUDA, Vulkan, and exact one-environment ManiSkill RGB preflight."
VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json vulkaninfo --summary \
  >"${EVIDENCE_ROOT}/stage5b-preflight-vulkan.txt" 2>&1

env \
  PYTHONPATH="${RLINF_HOME}" \
  VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json \
  SAPIEN_RENDER_SYSTEM=egl \
  MUJOCO_GL=egl \
  PYOPENGL_PLATFORM=egl \
  "${RLINF_HOME}/.venv/bin/python" - \
  >"${EVIDENCE_ROOT}/stage5b-preflight-runtime.txt" 2>&1 <<'PY'
import gymnasium as gym
import torch

from rlinf.envs.maniskill.peg_insertion_side_variants import (
    PEG_INSERTION_SIDE_WIDE_OBSERVER_WIDE_WRIST_ENV_ID,
    register_rlinf_peg_insertion_side_variants,
)

assert torch.cuda.is_available()
x = torch.tensor([2.0], device="cuda")
assert x.square().item() == 4.0

register_rlinf_peg_insertion_side_variants()
env = gym.make(
    PEG_INSERTION_SIDE_WIDE_OBSERVER_WIDE_WRIST_ENV_ID,
    num_envs=1,
    obs_mode="rgb",
    control_mode="pd_joint_delta_pos",
    reward_mode="sparse",
    sim_backend="gpu",
    sim_config={"sim_freq": 100, "control_freq": 10},
    sensor_configs={"width": 384, "height": 384},
)
observation, info = env.reset(seed=2026)
env.step(env.action_space.sample())
env.close()
print("cuda_vulkan_maniskill_preflight=pass")
PY

log "Preflight passed; launching 64 train trajectories as 16x4 and 256 eval trajectories as 16x16."
cd "${PROJECT_ROOT}"
set +e
env \
  RLINF_HOME="${RLINF_HOME}" \
  MODEL_PATH="${MODEL_PATH}" \
  STAGE1_CHECKPOINT="${STAGE1_CHECKPOINT}" \
  NORM_STATS_PATH="${NORM_STATS_PATH}" \
  WANDB_PROJECT="${WANDB_PROJECT}" \
  WANDB_MODE=offline \
  WANDB_DIR=/dev/shm/wandb \
  D1_SEED="${D1_SEED}" \
  GPU_HOURLY_PRICE_USD="${GPU_HOURLY_PRICE_USD}" \
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  "${RLINF_HOME}/.venv/bin/python" -m agent.d1_launcher \
    --config configs/d1/stage2_l40s_cpu_transport_probe.yaml \
    --results-root "${RESULTS_ROOT}" \
    --run-id "${STAGE5B_RUN_ID}" \
    --execute \
    --acknowledge-paid-run \
    >"${PERSISTENT_ROOT}/stage5b-l40s-console.log" 2>&1
stage5b_exit_code=$?
set -e

copy_compact_evidence "${STAGE5B_RUN_DIR}" "${EVIDENCE_ROOT}/stage5b-l40s-batched16-success"
if (( stage5b_exit_code != 0 )); then
  log "Stage 5B launcher failed with exit ${stage5b_exit_code}; compact evidence was preserved."
  exit "${stage5b_exit_code}"
fi
require_complete_manifest "${STAGE5B_MANIFEST}" "Stage 5B"
log "Stage 5B execution-probe evidence preserved; this does not by itself pass the scientific baseline gate."
