#!/usr/bin/env python3
"""Attach one M6 candidate and prove a finite non-default PyTorch effect."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_e1_objective_equivalence import (  # noqa: E402
    _load_pinned_worker_with_stubs,
    _worker,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rlinf-root", required=True, type=Path)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--objective-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    import torch

    from agent.rlt_objective_attachment import install_patch
    from supervisor.objective_validation import OBJECTIVE_CONTRACT_VERSION

    mixin, forward_type = _load_pinned_worker_with_stubs(args.rlinf_root)
    native = getattr(mixin.forward_actor, "__wrapped__", mixin.forward_actor)
    installed = install_patch(
        rlinf_root=args.rlinf_root,
        plugin_path=args.plugin,
        objective_sha256=args.objective_sha256,
        contract_version=OBJECTIVE_CONTRACT_VERSION,
    )
    if not installed:
        raise AssertionError("E2 probe requires a newly installed objective patch")
    patched = getattr(mixin.forward_actor, "__wrapped__", mixin.forward_actor)

    fixture = {
        "device": torch.device("cpu"),
        "dtype": torch.float32,
        "shape": (3, 2, 4),
        "weights": (0.45, 2.5),
        "masked": True,
    }
    native_worker, native_batch, native_pi = _worker(
        torch, mixin, forward_type, **fixture
    )
    native_loss, _, _ = native(native_worker, native_batch)
    (native_loss / 4).backward()
    native_gradient = native_pi.grad.detach().clone()

    candidate_worker, candidate_batch, candidate_pi = _worker(
        torch, mixin, forward_type, **fixture
    )
    candidate_loss, _, _ = patched(candidate_worker, candidate_batch)
    (candidate_loss / 4).backward()
    candidate_gradient = candidate_pi.grad.detach().clone()

    value_delta = float((candidate_loss.detach() - native_loss.detach()).item())
    gradient_delta = float(
        (candidate_gradient - native_gradient).abs().max().item()
    )
    if not torch.isfinite(candidate_loss.detach()).item():
        raise AssertionError("E2 candidate produced a non-finite loss")
    if value_delta == 0.0 and gradient_delta == 0.0:
        raise AssertionError("E2 candidate did not change forward or gradient behavior")

    marker = mixin._qualia_objective_attachment
    source_hash = hashlib.sha256(args.plugin.read_bytes()).hexdigest()
    if marker["objective_sha256"] != source_hash:
        raise AssertionError("runtime marker objective hash mismatch")
    record = {
        "attachment": marker,
        "candidate_gradient_max_abs_delta": gradient_delta,
        "candidate_loss": float(candidate_loss.detach().item()),
        "device": "cpu",
        "dtype": "float32",
        "gradient_accumulation": 4,
        "native_loss": float(native_loss.detach().item()),
        "objective_sha256": source_hash,
        "policy_shape": list(fixture["shape"]),
        "schema_version": 1,
        "status": "passed",
        "torch_version": torch.__version__,
        "value_delta": value_delta,
    }
    encoded = json.dumps(record, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
