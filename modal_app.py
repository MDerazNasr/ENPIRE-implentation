"""Modal launcher for an interactive ENPIRE/RLinf GPU workspace.

Run ``modal run modal_app.py`` for a GPU diagnostic, or start an interactive
shell with ``modal shell modal_app.py::instance``.
"""

from __future__ import annotations

import subprocess

import modal


APP_NAME = "enpire-rlinf"
GPU = "RTX-PRO-6000"
PROJECT_ROOT = "/root/enpire"
PERSISTENT_ROOT = "/workspace"

app = modal.App(APP_NAME)

# Keep large cloned repositories, downloaded models, and datasets between
# container starts. Files written outside /workspace are ephemeral.
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=True)

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
        "build-essential",
        "libgl1",
        "libvulkan1",
        "vulkan-tools",
    )
    .uv_pip_install("pyyaml", "psutil")
    # Mount only source/configuration. Large results and tmp trees stay local.
    .add_local_dir("agent", f"{PROJECT_ROOT}/agent", copy=True)
    .add_local_dir("configs", f"{PROJECT_ROOT}/configs", copy=True)
    .add_local_dir("scripts", f"{PROJECT_ROOT}/scripts", copy=True)
    .add_local_dir("docs", f"{PROJECT_ROOT}/docs", copy=True)
    .add_local_dir("tests", f"{PROJECT_ROOT}/tests", copy=True)
    .add_local_file("README.md", f"{PROJECT_ROOT}/README.md", copy=True)
)


@app.function(
    image=image,
    gpu=GPU,
    cpu=8,
    memory=32768,
    timeout=60 * 60 * 8,
    volumes={PERSISTENT_ROOT: workspace},
)
def instance() -> None:
    """Verify the provisioned GPU and persistent workspace."""
    subprocess.run(["nvidia-smi"], check=True)
    subprocess.run(
        ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    print(f"Project source: {PROJECT_ROOT}")
    print(f"Persistent storage: {PERSISTENT_ROOT}")


@app.local_entrypoint()
def main() -> None:
    instance.remote()
