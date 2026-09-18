from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import hydra
import mani_skill
import omegaconf
import sapien
import torch
from openpi.shared import normalize


def main() -> None:
    norm_path = Path("/opt/enpire-assets/norm_stats.json")
    norm_stats = normalize.load(norm_path.parent)
    vulkan = subprocess.run(
        ["vulkaninfo", "--summary"],
        check=False,
        capture_output=True,
        text=True,
    )
    vulkan_text = vulkan.stdout + vulkan.stderr
    from agent import metrics, rlt_resume_state

    result = {
        "cuda": torch.version.cuda,
        "cuda_probe": float((torch.ones(1, device="cuda") + 3).item()),
        "gpu": torch.cuda.get_device_name(0),
        "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
        "hydra": hydra.__version__,
        "maniskill": importlib.metadata.version("mani-skill"),
        "metrics_module": metrics.__file__,
        "norm_stats_sha256": hashlib.sha256(norm_path.read_bytes()).hexdigest(),
        "omegaconf": omegaconf.__version__,
        "openpi_norm_loader_keys": sorted(norm_stats),
        "policy_loaded": False,
        "python": sys.version.split()[0],
        "resume_state_module": rlt_resume_state.__file__,
        "rlinf_commit": subprocess.run(
            ["git", "-C", "/opt/RLinf", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "sapien": sapien.__version__,
        "scientific_evaluation_executed": False,
        "simulator_step_executed": False,
        "torch": torch.__version__,
        "vulkan_llvmpipe": "llvmpipe" in vulkan_text.lower(),
        "vulkan_returncode": vulkan.returncode,
    }
    assert result["cuda_probe"] == 4.0
    assert result["rlinf_commit"] == "c90951a0c799a750cb5294ed10587c61cc2af8bf"
    assert result["openpi_norm_loader_keys"] == ["actions", "state"]
    assert result["vulkan_llvmpipe"]
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
