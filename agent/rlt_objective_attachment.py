"""Opt-in live attachment of the M6 objective to pinned RLinf."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent.rlt_objective_seam import (
    PINNED_FILES,
    SEAM_CONTRACT_VERSION,
    WORKER_PATH,
    audit_rlinf_objective_seam,
)
from supervisor.canonical import require_safe_relative_path, require_sha256
from supervisor.objective_validation import (
    OBJECTIVE_CONTRACT_VERSION,
    OBJECTIVE_FUNCTION,
    OBJECTIVE_RELATIVE_PATH,
    validate_actor_objective_source,
)


ATTACHMENT_MODE = "sitecustomize-rlt-loss-mixin-v1"
INSTALLATION_PREFIX = "QUALIA_RLT_OBJECTIVE_ATTACHMENT="


class RLTObjectiveAttachmentError(ValueError):
    """Raised when the live objective cannot be attached without ambiguity."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class LiveActorObjectiveAdapter:
    """Invoke an M6 plugin while enforcing the frozen live tensor boundary."""

    plugin: Callable[[Any, Any, Any], Any]

    def combine(self, actor_loss: Any, bc_loss: Any, bc_weight: float) -> Any:
        import torch

        result = self.plugin(actor_loss, bc_loss, bc_weight)
        if not isinstance(result, torch.Tensor):
            raise RLTObjectiveAttachmentError(
                "live actor-objective plugin must return a torch.Tensor"
            )
        if result.ndim != 0:
            raise RLTObjectiveAttachmentError(
                "live actor-objective plugin must return a rank-0 tensor"
            )
        if result.device != actor_loss.device or result.dtype != actor_loss.dtype:
            raise RLTObjectiveAttachmentError(
                "live actor-objective plugin changed objective dtype or device"
            )
        if (actor_loss.requires_grad or bc_loss.requires_grad) and not result.requires_grad:
            raise RLTObjectiveAttachmentError(
                "live actor-objective plugin disconnected the autograd graph"
            )
        if not bool(torch.isfinite(result.detach()).item()):
            raise RLTObjectiveAttachmentError(
                "live actor-objective plugin returned a non-finite tensor"
            )
        return result


def _load_plugin(path: Path, expected_sha256: str) -> Callable[[Any, Any, Any], Any]:
    if not path.is_file():
        raise RLTObjectiveAttachmentError(f"objective plugin is not a file: {path}")
    actual_hash = _sha256(path)
    if actual_hash != expected_sha256:
        raise RLTObjectiveAttachmentError(
            f"objective plugin hash mismatch: expected {expected_sha256}, got {actual_hash}"
        )
    issues = validate_actor_objective_source(path.read_bytes())
    if issues:
        details = "; ".join(f"{item.code}:{item.message}" for item in issues)
        raise RLTObjectiveAttachmentError(f"objective plugin violates M6 ABI: {details}")
    spec = importlib.util.spec_from_file_location(
        f"qualia_live_objective_{actual_hash[:12]}", path
    )
    if spec is None or spec.loader is None:
        raise RLTObjectiveAttachmentError("objective plugin loader is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin = getattr(module, OBJECTIVE_FUNCTION, None)
    if not callable(plugin):
        raise RLTObjectiveAttachmentError("objective plugin function is unavailable")
    return plugin


def _required_value(value: str | Path | None, environment_name: str) -> str:
    resolved = str(value) if value is not None else os.environ.get(environment_name, "")
    if not resolved:
        raise RLTObjectiveAttachmentError(
            f"required objective attachment value is missing: {environment_name}"
        )
    return resolved


def install_patch(
    *,
    rlinf_root: str | Path | None = None,
    plugin_path: str | Path | None = None,
    objective_sha256: str | None = None,
    contract_version: str | None = None,
    display_path: str | None = None,
) -> bool:
    """Verify and install the pinned objective overlay once in this process."""

    root = Path(_required_value(rlinf_root, "RLINF_HOME")).resolve()
    objective = Path(
        _required_value(plugin_path, "QUALIA_RLT_OBJECTIVE_PLUGIN")
    ).resolve()
    expected_hash = require_sha256(
        _required_value(objective_sha256, "QUALIA_RLT_OBJECTIVE_SHA256"),
        "objective source hash",
    )
    contract = _required_value(
        contract_version, "QUALIA_RLT_OBJECTIVE_CONTRACT_VERSION"
    )
    if contract != OBJECTIVE_CONTRACT_VERSION:
        raise RLTObjectiveAttachmentError(
            f"unsupported objective contract: {contract!r}"
        )
    relative = require_safe_relative_path(
        display_path
        or os.environ.get("QUALIA_RLT_OBJECTIVE_DISPLAY_PATH")
        or OBJECTIVE_RELATIVE_PATH,
        "objective display path",
    )

    seam = audit_rlinf_objective_seam(root)
    plugin = _load_plugin(objective, expected_hash)

    from rlinf.models.embodiment.base_policy import ForwardType
    from rlinf.scheduler import Worker
    from rlinf.workers.actor.fsdp_rlt_ac_policy_worker import RLTACLossMixin

    adapter_hash = _sha256(Path(__file__))
    marker = {
        "adapter_sha256": adapter_hash,
        "attachment_mode": ATTACHMENT_MODE,
        "installed_target": "RLTACLossMixin.forward_actor",
        "objective_contract_version": contract,
        "objective_relative_path": relative,
        "objective_sha256": expected_hash,
        "rlinf_commit": seam["rlinf_commit"],
        "rlinf_worker_sha256": PINNED_FILES[WORKER_PATH],
        "seam_contract_version": SEAM_CONTRACT_VERSION,
    }
    prior = getattr(RLTACLossMixin, "_qualia_objective_attachment", None)
    if prior is not None:
        if prior == marker:
            return False
        raise RLTObjectiveAttachmentError(
            "an incompatible live actor-objective patch is already installed"
        )

    adapter = LiveActorObjectiveAdapter(plugin=plugin)

    def forward_actor(self, batch):
        use_crossq = self.cfg.algorithm.get("q_head_type", "default") == "crossq"

        curr_obs = batch["curr_obs"]
        reference_dropout_prob = float(
            self.cfg.algorithm.get("reference_dropout_prob", 0.0)
        )
        pi, log_pi, _ = self.model(
            forward_type=ForwardType.SAC,
            obs=curr_obs,
            apply_reference_dropout=True,
            reference_dropout_prob=reference_dropout_prob,
        )
        if log_pi.ndim == 1:
            log_pi = log_pi.unsqueeze(-1)
        log_pi = log_pi.sum(dim=-1, keepdim=True)

        if not use_crossq:
            all_qf_pi = self.model(
                forward_type=ForwardType.SAC_Q,
                obs=curr_obs,
                actions=pi,
                detach_encoder=True,
            )
        else:
            all_qf_pi, _ = self.model(
                forward_type=ForwardType.CROSSQ_Q,
                obs=curr_obs,
                actions=pi,
                next_obs=None,
                next_actions=None,
                detach_encoder=True,
            )

        num_q_values = all_qf_pi.shape[-1]
        metrics = {
            f"q_value_{q_id}": all_qf_pi[..., q_id].mean().item()
            for q_id in range(num_q_values)
        }
        qf_pi = self._q1(all_qf_pi)
        metrics["q_pi"] = qf_pi.mean().item()

        ref_chunk = self._ref_chunk(curr_obs)
        bc_loss, rlt_metrics = self._bc_metrics(
            pi=pi,
            actions=batch["actions"],
            ref_chunk=ref_chunk,
            intervene_flags=batch.get("intervene_flags", None),
        )
        metrics.update(rlt_metrics)

        entropy = -log_pi.mean()
        bc_weight, q_weight, weight_metrics = self._actor_objective_weights()
        q_actor_loss = -q_weight * qf_pi.mean()
        actor_loss = adapter.combine(q_actor_loss, bc_loss, bc_weight)
        metrics.update(weight_metrics)
        metrics["action_ref_abs_mean"] = (
            (self._flatten_chunk(pi) - self._flatten_chunk(ref_chunk))
            .abs()
            .mean()
            .detach()
            .item()
        )
        metrics["weighted_q"] = (q_weight * qf_pi.mean()).detach().item()
        metrics["weighted_bc"] = (bc_weight * bc_loss).detach().item()
        metrics["reference_dropout_prob"] = reference_dropout_prob

        return actor_loss, entropy, metrics

    RLTACLossMixin._qualia_objective_original_forward_actor = (
        RLTACLossMixin.forward_actor
    )
    RLTACLossMixin.forward_actor = Worker.timer("forward_actor")(forward_actor)
    RLTACLossMixin._qualia_objective_attachment = marker
    print(INSTALLATION_PREFIX + json.dumps(marker, sort_keys=True), flush=True)
    return True
