"""Fail-closed audit of the pinned RLinf RLT actor-objective seam."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Mapping

from agent.d1_config import RLINF_COMMIT


SEAM_CONTRACT_VERSION = "rlinf-rlt-actor-objective-seam-v1"
WORKER_PATH = Path("rlinf/workers/actor/fsdp_rlt_ac_policy_worker.py")
BACKWARD_PATH = Path("rlinf/workers/actor/fsdp_sac_policy_worker.py")
CONFIG_PATH = Path("examples/embodiment/config/maniskill_rlt_stage2_ac_mlp.yaml")

PINNED_FILES = {
    WORKER_PATH: "b2d5032400a63c2592b6175d524cac936c282f5a287e448dbcc5da7ad42d1fc2",
    BACKWARD_PATH: "190165b7bac7c934a3d80eb69ebf65f218925c810c91ae29c22e8b8dea267765",
    CONFIG_PATH: "bb5c01c0db25fcd962b5fa21d2fe60505ed73ed86bb8875e19167378d6456457",
}

REQUIRED_SOURCE = {
    WORKER_PATH: (
        "bc_error = torch.mean(torch.square(pi_chunk - bc_target), dim=-1)",
        "bc_loss = torch.mean(bc_error)",
        "qf_pi = self._q1(all_qf_pi)",
        "bc_weight, q_weight, weight_metrics = self._actor_objective_weights()",
        "actor_loss = -q_weight * qf_pi.mean() + bc_weight * bc_loss",
        "return actor_loss, entropy, metrics",
        "class RLTACFSDPPolicy(RLTACLossMixin, RLTACReplayMixin, EmbodiedSACFSDPPolicy):",
    ),
    BACKWARD_PATH: (
        "actor_loss, entropy, q_metrics = self.forward_actor(batch)",
        "actor_loss = actor_loss / self.gradient_accumulation",
        "actor_loss.backward()",
    ),
    CONFIG_PATH: (
        "loss_type: rlt_ac",
        "q_weight: 1.0",
        "bc_weight: 1.0",
        "warmup_bc_weight: 7.0",
        "warmup_q_weight: 0.05",
        "online_bc_weight: 2.5",
        "online_q_weight: 0.45",
    ),
}


class RLTObjectiveSeamError(ValueError):
    """Raised when a checkout no longer matches the frozen live seam."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_rlinf_objective_seam(
    rlinf_root: Path,
    *,
    expected_files: Mapping[Path, str] = PINNED_FILES,
) -> dict[str, object]:
    """Verify the exact upstream commit, files, and critical source statements."""

    root = rlinf_root.resolve()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RLTObjectiveSeamError(f"cannot resolve RLinf commit at {root}") from error
    if commit != RLINF_COMMIT:
        raise RLTObjectiveSeamError(
            f"RLinf commit mismatch: expected {RLINF_COMMIT}, got {commit}"
        )

    files: dict[str, str] = {}
    for relative, expected_hash in expected_files.items():
        path = root / relative
        if not path.is_file():
            raise RLTObjectiveSeamError(f"pinned seam file missing: {relative}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise RLTObjectiveSeamError(
                f"pinned seam file hash mismatch for {relative}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        source = path.read_text()
        for statement in REQUIRED_SOURCE[relative]:
            if statement not in source:
                raise RLTObjectiveSeamError(
                    f"required seam statement missing from {relative}: {statement}"
                )
        files[str(relative)] = actual_hash

    return {
        "schema_version": 1,
        "seam_contract_version": SEAM_CONTRACT_VERSION,
        "rlinf_commit": commit,
        "files": files,
        "status": "passed",
    }
