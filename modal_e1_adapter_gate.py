"""No-policy Modal gate for the E1 frozen observation contract."""

from __future__ import annotations

import json
import os
import subprocess

import modal


APP_NAME = "enpire-g0-e1-observation-gate-v1"
BASE_IMAGE_ID = "im-66ku0dbczWNQDgPWv97XNc"
PROJECT_ROOT = "/opt/qualia"
RLINF_HOME = "/opt/RLinf"
DEVELOPMENT_RESETS = f"{PROJECT_ROOT}/development-resets.json"
DEVELOPMENT_RESET_FINGERPRINT = (
    "e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161"
)


app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "g0-e1-gate"})
image = (
    modal.Image.from_id(BASE_IMAGE_ID)
    .entrypoint([])
    .env({"PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}"})
    .pip_install("modal==1.5.4")
    .add_local_dir("envs", f"{PROJECT_ROOT}/envs", copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_file("sitecustomize.py", f"{PROJECT_ROOT}/sitecustomize.py", copy=True)
    .add_local_file(
        "results/agent-supervisor/g0/reset-sets/development.json",
        DEVELOPMENT_RESETS,
        copy=True,
    )
)


@app.function(
    image=image,
    cpu=16,
    memory=96 * 1024,
    timeout=15 * 60,
    retries=0,
    single_use_containers=True,
)
def observation_gate() -> dict[str, object]:
    environment = {
        **os.environ,
        "RLINF_HOME": RLINF_HOME,
        "PYTHONPATH": f"{PROJECT_ROOT}:{RLINF_HOME}",
        "PYTHONUNBUFFERED": "1",
        "QUALIA_DEVELOPMENT_RESET_PATH": DEVELOPMENT_RESETS,
        "QUALIA_DEVELOPMENT_RESET_SHA256": DEVELOPMENT_RESET_FINGERPRINT,
        "QUALIA_MODAL_MP_START_METHOD": "spawn",
        "QUALIA_MODAL_RENDER_DEVICE": "pci:0000:00:00.0",
        "QUALIA_MODAL_VULKAN_ICD": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "QUALIA_MODAL_THREADS_PER_WORKER": "1",
        "VK_ICD_FILENAMES": "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json",
        "LP_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    completed = subprocess.run(
        [
            f"{RLINF_HOME}/.venv/bin/python",
            f"{PROJECT_ROOT}/scripts/e1_observation_contract_gate.py",
        ],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(completed.stdout, flush=True)
    if completed.returncode:
        raise RuntimeError(f"observation gate failed with exit {completed.returncode}")
    marker = next(
        line.split("=", 1)[1]
        for line in completed.stdout.splitlines()
        if line.startswith("QUALIA_E1_OBSERVATION_GATE=")
    )
    return json.loads(marker)


@app.local_entrypoint()
def main():
    print(json.dumps(observation_gate.remote(), indent=2, sort_keys=True))
