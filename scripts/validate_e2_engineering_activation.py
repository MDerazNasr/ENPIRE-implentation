#!/usr/bin/env python3
"""Fail closed unless the approved E2 source package is exactly present."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "results/agent-supervisor/g0/e2-engineering-gate-approval-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> dict[str, object]:
    record = json.loads(APPROVAL.read_text(encoding="utf-8"))
    if record.get("status") != "approved_fixed_engineering_gate":
        raise RuntimeError("E2 approval status is invalid")
    authority = record.get("authority", {})
    if authority.get("fixed_gpu_execution_authorized") is not True:
        raise RuntimeError("fixed E2 execution is not authorized")
    forbidden = (
        "automatic_retry_authorized", "additional_seed_authorized",
        "additional_arm_authorized", "final_reset_access_authorized",
        "scientific_e2_claim_authorized", "policy_promotion_authorized",
    )
    if any(authority.get(key) is not False for key in forbidden):
        raise RuntimeError("E2 approval grants forbidden authority")
    source_commit = record["source_commit"]
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT, check=True, capture_output=True,
    )
    mismatches = {
        relative: {"expected": expected, "actual": sha256(ROOT / relative)}
        for relative, expected in record["source_files"].items()
        if sha256(ROOT / relative) != expected
    }
    if mismatches:
        raise RuntimeError(f"approved E2 source mismatch: {mismatches}")
    scope = record["fixed_scope"]
    if scope["arms"] != ["control", "candidate"] or scope["seed"] != 2026:
        raise RuntimeError("approved E2 allocation mismatch")
    if scope["maximum_resource_cost_usd"] != "338.298720":
        raise RuntimeError("approved E2 resource ceiling mismatch")
    return {
        "status": "ready_for_modal_cpu_preflight",
        "approval_path": str(APPROVAL.relative_to(ROOT)),
        "source_commit": source_commit,
        "verified_source_files": len(record["source_files"]),
        "maximum_resource_cost_usd": scope["maximum_resource_cost_usd"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
