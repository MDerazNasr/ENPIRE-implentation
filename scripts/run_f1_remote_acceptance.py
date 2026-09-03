#!/usr/bin/env python3
"""Create the immutable no-launch F1 Modal worker acceptance preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.modal_worker_rpc import F1_APP_NAME, F1_FUNCTION_NAME  # noqa: E402
from supervisor.workers import RunContract  # noqa: E402


DEFAULT_PROFILE = ROOT / "results/runtime-qualification/f1/profile.json"
DEFAULT_OUTPUT = ROOT / "results/runtime-qualification/f1/preflight.json"
RUNTIME_CONTRACT = ROOT / "results/runtime-qualification/f0/runtime-contract.json"
MODAL_PYTHON = Path("/opt/homebrew/Cellar/modal/1.5.3_1/libexec/bin/python")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _contract(head: str, profile: dict[str, Any], trial_id: str) -> RunContract:
    fixed_command = {
        "app": profile["app_name"],
        "function": profile["probe_function"],
        "operation": "bounded CUDA matrix and llvmpipe Vulkan acceptance",
        "probe_seconds": profile["live_probe"]["probe_seconds"],
    }
    return RunContract.create(
        campaign_id="f1-worker-rpc-acceptance-v1",
        trial_id=trial_id,
        arm_id="f1-engineering-only",
        parent_commit=head,
        candidate_commit=head,
        rlinf_commit="c90951a0c799a750cb5294ed10587c61cc2af8bf",
        config_hash=profile["runtime_contract_sha256"],
        command_hash=fingerprint(fixed_command),
        seed=2026,
        reset_set_hash=hashlib.sha256(b"f1-no-scientific-reset-set").hexdigest(),
        evaluator_version="f1-evaluation-forbidden-v1",
        max_wall_time_seconds=profile["live_probe"]["function_timeout_seconds"],
        max_gpu_cost_usd="0.379416",
    )


def build_preflight(profile_path: Path) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text())
    if profile["schema_version"] != 1:
        raise ValueError("F1 profile schema_version must be 1")
    if profile["app_name"] != F1_APP_NAME or profile["rpc_function"] != F1_FUNCTION_NAME:
        raise ValueError("F1 profile endpoint differs from the fixed client")
    if profile["approval"] != {
        "deployment_authorized": False,
        "gpu_execution_authorized": False,
        "explicit_approval_required": True,
    }:
        raise ValueError("F1 profile approval boundary is invalid")
    if _git("status", "--porcelain"):
        raise ValueError("F1 preflight requires a clean worktree")
    head = _git("rev-parse", "HEAD")
    runtime_hash = _sha256(RUNTIME_CONTRACT)
    if runtime_hash != profile["runtime_contract_sha256"]:
        raise ValueError("F0 runtime contract hash drifted")
    source_hashes = {
        relative: _sha256(ROOT / relative) for relative in profile["source_paths"]
    }
    if not MODAL_PYTHON.is_file():
        raise ValueError("pinned Modal client interpreter is unavailable")
    imported = subprocess.run(
        [
            str(MODAL_PYTHON),
            "-c",
            "import modal, modal_f1_worker; print(modal.__version__); print(modal_f1_worker.APP_NAME)",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    ).stdout.splitlines()
    if imported != [profile["deployment"]["modal_client_version"], F1_APP_NAME]:
        raise ValueError("Modal client or application import identity mismatch")
    contracts = [
        _contract(head, profile, "f1-complete-probe").to_dict(),
        _contract(head, profile, "f1-active-cancel-probe").to_dict(),
    ]
    return {
        "schema_version": 1,
        "status": "ready_for_explicit_approval",
        "claim_scope": profile["claim_scope"],
        "profile": profile,
        "profile_sha256": _sha256(profile_path),
        "head": head,
        "runtime_contract_sha256": runtime_hash,
        "source_hashes": source_hashes,
        "source_bundle_sha256": fingerprint(source_hashes),
        "deployment": {
            "argv": [
                profile["deployment"]["modal_client"],
                "deploy",
                "--strategy",
                profile["deployment"]["strategy"],
                "modal_f1_worker.py",
            ],
            "app": F1_APP_NAME,
            "rpc_function": F1_FUNCTION_NAME,
            "probe_function": profile["probe_function"],
        },
        "contracts": contracts,
        "required_live_checks": [
            "prepare",
            "heartbeat",
            "launch",
            "coordinator_restart_status",
            "fetch_evidence",
            "fetch_artifact_digest",
            "active_cancel",
            "late_cancelled_status",
            "identity_spoof_rejection",
            "tagged_provider_billing",
        ],
        "execution_authorized": False,
        "gpu_execution_authorized": False,
        "promotion_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        payload = build_preflight(args.profile.resolve())
        content = canonical_json(payload) + "\n"
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.resolve().write_text(content)
        print(canonical_json({
            "status": payload["status"],
            "profile_sha256": payload["profile_sha256"],
            "source_bundle_sha256": payload["source_bundle_sha256"],
            "maximum_total_provider_cost_usd": payload["profile"]["billing"]["maximum_total_provider_cost_usd"],
            "execution_authorized": False,
        }))
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"F1_PREFLIGHT_REJECTED={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
