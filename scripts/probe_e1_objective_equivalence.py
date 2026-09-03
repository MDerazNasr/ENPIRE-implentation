#!/usr/bin/env python3
"""Prove native/patched RLinf actor-objective equivalence with PyTorch."""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class AttrMap(dict):
    """Small attribute-access mapping for the isolated worker fixture."""

    __getattr__ = dict.__getitem__


def _load_pinned_worker_with_stubs(rlinf_root: Path):
    """Load the exact worker source without installing unrelated RLinf services."""

    class ForwardType:
        SAC = "sac"
        SAC_Q = "sac_q"
        CROSSQ_Q = "crossq_q"

    class Worker:
        @staticmethod
        def timer(_label):
            def decorate(function):
                @functools.wraps(function)
                def wrapped(*args, **kwargs):
                    return function(*args, **kwargs)

                return wrapped

            return decorate

    class EmptyBase:
        pass

    packages = (
        "rlinf",
        "rlinf.algorithms",
        "rlinf.algorithms.rlt",
        "rlinf.data",
        "rlinf.models",
        "rlinf.models.embodiment",
        "rlinf.scheduler",
        "rlinf.utils",
        "rlinf.workers",
        "rlinf.workers.actor",
    )
    for name in packages:
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    modules = {
        "rlinf.algorithms.rlt.transition": {
            "use_simulator_transition_replay": lambda _cfg: False
        },
        "rlinf.data.embodied_io_struct": {"Trajectory": EmptyBase},
        "rlinf.models.embodiment.base_policy": {"ForwardType": ForwardType},
        "rlinf.scheduler": {"Worker": Worker},
        "rlinf.utils.distributed": {"all_reduce_dict": lambda value, **_kwargs: value},
        "rlinf.utils.metric_utils": {
            "append_to_dict": lambda *_args, **_kwargs: None,
            "collect_trajectory_replay_metrics": lambda *_args, **_kwargs: {},
            "compute_split_num": lambda *_args, **_kwargs: 1,
            "trajectory_has_bool_tensor": lambda *_args, **_kwargs: False,
        },
        "rlinf.utils.utils": {"clear_memory": lambda **_kwargs: None},
        "rlinf.workers.actor.async_fsdp_sac_policy_worker": {
            "AsyncEmbodiedSACFSDPPolicy": EmptyBase
        },
        "rlinf.workers.actor.fsdp_sac_policy_worker": {
            "EmbodiedSACFSDPPolicy": EmptyBase
        },
    }
    for name, attributes in modules.items():
        module = sys.modules.get(name) or types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[name] = module

    worker_path = (
        rlinf_root / "rlinf/workers/actor/fsdp_rlt_ac_policy_worker.py"
    )
    module_name = "rlinf.workers.actor.fsdp_rlt_ac_policy_worker"
    spec = importlib.util.spec_from_file_location(module_name, worker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("pinned worker module loader is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.RLTACLossMixin, ForwardType


def _worker(torch, mixin, forward_type, *, device, dtype, shape, weights, masked):
    batch_size, chunks, action_dim = shape
    values = torch.linspace(
        -0.75,
        0.75,
        steps=batch_size * chunks * action_dim,
        device=device,
        dtype=dtype,
    ).reshape(shape)
    pi = values.detach().clone().requires_grad_(True)

    class Model:
        def __call__(self, *, forward_type: object, actions=None, **_kwargs):
            if forward_type == forward_type_enum.SAC:
                log_pi = torch.zeros(
                    (batch_size, chunks), device=device, dtype=dtype
                )
                return pi, log_pi, None
            if forward_type == forward_type_enum.SAC_Q:
                q1 = actions.reshape(batch_size, -1).mean(dim=-1, keepdim=True)
                return torch.cat((q1, q1 * 0.5), dim=-1)
            raise AssertionError(f"unexpected forward type: {forward_type}")

    forward_type_enum = forward_type
    worker = object.__new__(mixin)
    worker.cfg = AttrMap(
        actor=AttrMap(model=AttrMap(num_action_chunks=chunks, action_dim=action_dim)),
        algorithm=AttrMap(
            q_head_type="default",
            reference_dropout_prob=0.0,
            actor_weight_schedule=AttrMap(enable=False),
            q_weight=weights[0],
            bc_weight=weights[1],
        ),
    )
    worker.update_step = 0
    worker.model = Model()
    reference = torch.flip(values, dims=(-1,)).detach()
    actions = (-values).detach()
    flags = None
    if masked:
        flags = torch.zeros(shape, device=device, dtype=torch.bool)
        flags[:, 0, 0] = True
    batch = {
        "curr_obs": {"ref_chunk": reference},
        "actions": actions,
        "intervene_flags": flags,
    }
    return worker, batch, pi


def _run_case(torch, mixin, forward_type, native, patched, case):
    device = torch.device(case["device"])
    dtype = getattr(torch, case["dtype"])
    shape = tuple(case["shape"])
    arguments = dict(
        device=device,
        dtype=dtype,
        shape=shape,
        weights=tuple(case["weights"]),
        masked=case["masked"],
    )
    native_worker, native_batch, native_pi = _worker(
        torch, mixin, forward_type, **arguments
    )
    native_loss, native_entropy, native_metrics = native(native_worker, native_batch)
    (native_loss / case["gradient_accumulation"]).backward()
    native_gradient = native_pi.grad.detach().clone()

    patched_worker, patched_batch, patched_pi = _worker(
        torch, mixin, forward_type, **arguments
    )
    patched_loss, patched_entropy, patched_metrics = patched(
        patched_worker, patched_batch
    )
    (patched_loss / case["gradient_accumulation"]).backward()
    patched_gradient = patched_pi.grad.detach().clone()

    value_diff = float((native_loss.detach() - patched_loss.detach()).abs().float())
    gradient_diff = float(
        (native_gradient - patched_gradient).abs().float().max().item()
    )
    if value_diff != 0.0 or gradient_diff != 0.0:
        raise AssertionError(
            f"equivalence failure for {case['id']}: "
            f"value={value_diff}, gradient={gradient_diff}"
        )
    if native_loss.shape != patched_loss.shape or native_loss.ndim != 0:
        raise AssertionError(f"objective shape mismatch for {case['id']}")
    if native_loss.dtype != patched_loss.dtype or native_loss.device != patched_loss.device:
        raise AssertionError(f"objective dtype/device mismatch for {case['id']}")
    if native_entropy.detach().item() != patched_entropy.detach().item():
        raise AssertionError(f"entropy mismatch for {case['id']}")
    if native_metrics != patched_metrics:
        raise AssertionError(f"metric mismatch for {case['id']}")
    return {
        **case,
        "gradient_max_abs_diff": gradient_diff,
        "loss": float(native_loss.detach().float().item()),
        "objective_rank": native_loss.ndim,
        "value_abs_diff": value_diff,
    }


def _negative_controls(torch):
    from agent.rlt_objective_attachment import (
        LiveActorObjectiveAdapter,
        RLTObjectiveAttachmentError,
    )

    actor = torch.tensor(1.0, requires_grad=True)
    bc = torch.tensor(2.0, requires_grad=True)
    controls = {
        "disconnected": lambda _actor, _bc, _weight: torch.tensor(1.0),
        "non_finite": lambda actor, _bc, _weight: actor * torch.inf,
        "wrong_shape": lambda actor, _bc, _weight: actor.repeat(2),
    }
    passed = []
    for name, plugin in controls.items():
        try:
            LiveActorObjectiveAdapter(plugin).combine(actor, bc, 0.5)
        except RLTObjectiveAttachmentError:
            passed.append(name)
        else:
            raise AssertionError(f"negative control did not fail closed: {name}")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rlinf-root", required=True, type=Path)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--objective-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hermetic-rlinf-stubs", action="store_true")
    args = parser.parse_args()

    import torch

    if args.hermetic_rlinf_stubs:
        RLTACLossMixin, ForwardType = _load_pinned_worker_with_stubs(args.rlinf_root)
    else:
        if str(args.rlinf_root) not in sys.path:
            sys.path.insert(0, str(args.rlinf_root))
        from rlinf.models.embodiment.base_policy import ForwardType
        from rlinf.workers.actor.fsdp_rlt_ac_policy_worker import RLTACLossMixin

    from agent.rlt_objective_attachment import install_patch
    from supervisor.objective_validation import OBJECTIVE_CONTRACT_VERSION

    native = getattr(
        RLTACLossMixin.forward_actor, "__wrapped__", RLTACLossMixin.forward_actor
    )
    installed = install_patch(
        rlinf_root=args.rlinf_root,
        plugin_path=args.plugin,
        objective_sha256=args.objective_sha256,
        contract_version=OBJECTIVE_CONTRACT_VERSION,
    )
    if not installed:
        raise AssertionError("probe requires a newly installed objective patch")
    patched = getattr(
        RLTACLossMixin.forward_actor, "__wrapped__", RLTACLossMixin.forward_actor
    )

    cases = [
        {
            "id": "cpu-float32-single",
            "device": "cpu",
            "dtype": "float32",
            "shape": [1, 1, 2],
            "weights": [1.0, 1.0],
            "masked": False,
            "gradient_accumulation": 1,
        },
        {
            "id": "cpu-float64-masked",
            "device": "cpu",
            "dtype": "float64",
            "shape": [3, 2, 4],
            "weights": [0.45, 2.5],
            "masked": True,
            "gradient_accumulation": 4,
        },
        {
            "id": "cpu-float32-zero-weights",
            "device": "cpu",
            "dtype": "float32",
            "shape": [2, 3, 7],
            "weights": [0.0, 0.0],
            "masked": True,
            "gradient_accumulation": 3,
        },
        {
            "id": "cpu-bfloat16-warmup",
            "device": "cpu",
            "dtype": "bfloat16",
            "shape": [2, 4, 7],
            "weights": [0.05, 7.0],
            "masked": False,
            "gradient_accumulation": 2,
        },
    ]
    if torch.cuda.is_available():
        cases.extend(
            [
                {
                    "id": "cuda-float32-online",
                    "device": "cuda:0",
                    "dtype": "float32",
                    "shape": [4, 3, 7],
                    "weights": [0.45, 2.5],
                    "masked": True,
                    "gradient_accumulation": 4,
                },
                {
                    "id": "cuda-bfloat16-warmup",
                    "device": "cuda:0",
                    "dtype": "bfloat16",
                    "shape": [2, 4, 7],
                    "weights": [0.05, 7.0],
                    "masked": False,
                    "gradient_accumulation": 2,
                },
            ]
        )
    if torch.backends.mps.is_available():
        cases.append(
            {
                "id": "mps-float32-online",
                "device": "mps:0",
                "dtype": "float32",
                "shape": [4, 3, 7],
                "weights": [0.45, 2.5],
                "masked": True,
                "gradient_accumulation": 4,
            }
        )

    results = [
        _run_case(torch, RLTACLossMixin, ForwardType, native, patched, case)
        for case in cases
    ]
    marker = RLTACLossMixin._qualia_objective_attachment
    record = {
        "adapter_sha256": marker["adapter_sha256"],
        "attachment": marker,
        "cases": results,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "hermetic_rlinf_stubs": args.hermetic_rlinf_stubs,
        "mps_available": torch.backends.mps.is_available(),
        "negative_controls_rejected": _negative_controls(torch),
        "objective_sha256": hashlib.sha256(args.plugin.read_bytes()).hexdigest(),
        "rlinf_root": str(args.rlinf_root),
        "schema_version": 1,
        "status": "passed",
        "tolerances": {
            "gradient_max_abs_diff": 0.0,
            "value_abs_diff": 0.0,
        },
        "torch_version": torch.__version__,
    }
    encoded = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
