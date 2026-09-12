#!/usr/bin/env python3
"""Verify two pinned reset captures are byte-identical and emit a receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_g0_reset_sets import validate_capture
from supervisor.canonical import fingerprint


def build_receipt(first: Path, second: Path, rlinf_commit: str, maniskill_commit: str) -> dict:
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    if first_bytes != second_bytes:
        raise ValueError("reset captures are not byte-identical")
    value = json.loads(first_bytes)
    development, final, materialization = validate_capture(value, rlinf_commit, maniskill_commit)
    payload = {
        "schema_version": 1,
        "status": "source_derived_repeat_passed_runtime_confirmation_pending",
        "capture_file_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "capture_semantic_sha256": fingerprint(value),
        "development_sha256": development.fingerprint(),
        "final_sha256": final.fingerprint(),
        "development_ordered_ids_sha256": hashlib.sha256(
            json.dumps(list(development.reset_ids), separators=(",", ":")).encode()
        ).hexdigest(),
        "final_ordered_ids_sha256": hashlib.sha256(
            json.dumps(list(final.reset_ids), separators=(",", ":")).encode()
        ).hexdigest(),
        "materialization_receipt_sha256": materialization["sha256"],
        "byte_identical": True,
        "simulator_runtime_reset_confirmed": False,
        "policy_evaluation_executed": False,
        "gpu_execution_authorized": False,
        "promotion_executed": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--expected-rlinf-commit", required=True)
    parser.add_argument("--expected-maniskill-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    receipt = build_receipt(
        args.first, args.second, args.expected_rlinf_commit, args.expected_maniskill_commit
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
