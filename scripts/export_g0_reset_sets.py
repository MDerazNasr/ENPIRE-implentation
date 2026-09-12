#!/usr/bin/env python3
"""Validate and materialize reset IDs captured in the pinned simulator environment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import canonical_json, fingerprint, require_git_commit
from supervisor.evaluator_integrity import ResetSetArtifact, validate_reset_pair


CAPTURE_KEYS = {
    "schema_version", "extractor_id", "rlinf_commit", "maniskill_commit",
    "numpy_version", "source_hashes", "development", "final"
}
EXTRACTOR_ID = "rlinf-maniskill-fixed-reset-export-v1"
SOURCE_HASH_KEYS = {
    "project_multiprocess_adapter", "rlinf_environment", "rlinf_config",
    "rlinf_task_variant", "maniskill_base_env", "maniskill_task",
}


def validate_capture(
    value: object, expected_rlinf_commit: str, expected_maniskill_commit: str
) -> tuple[ResetSetArtifact, ResetSetArtifact, dict]:
    if not isinstance(value, dict) or set(value) != CAPTURE_KEYS:
        raise ValueError("reset capture fields are invalid")
    if value["schema_version"] != 1 or value["extractor_id"] != EXTRACTOR_ID:
        raise ValueError("reset capture exporter identity is invalid")
    expected = require_git_commit(expected_rlinf_commit, "expected RLinf commit")
    actual = require_git_commit(value["rlinf_commit"], "captured RLinf commit")
    if actual != expected:
        raise ValueError("captured RLinf commit does not match the frozen commit")
    expected_maniskill = require_git_commit(expected_maniskill_commit, "expected ManiSkill commit")
    actual_maniskill = require_git_commit(value["maniskill_commit"], "captured ManiSkill commit")
    if actual_maniskill != expected_maniskill:
        raise ValueError("captured ManiSkill commit does not match the frozen commit")
    if value["numpy_version"] != "1.26.4":
        raise ValueError("reset capture NumPy version is invalid")
    hashes = value["source_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != SOURCE_HASH_KEYS:
        raise ValueError("reset capture source hashes are invalid")
    for name, digest in hashes.items():
        if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"reset capture source hash is invalid: {name}")
    development = ResetSetArtifact.from_dict(value["development"])
    final = ResetSetArtifact.from_dict(value["final"])
    report = validate_reset_pair(development, final)
    if development.generator_seed != 2026 or final.generator_seed != 2027:
        raise ValueError("reset capture does not use the accepted generator seeds")
    receipt_payload = {
        "schema_version": 1,
        "extractor_id": EXTRACTOR_ID,
        "rlinf_commit": actual,
        "maniskill_commit": actual_maniskill,
        "numpy_version": value["numpy_version"],
        "source_hashes": hashes,
        "capture_sha256": fingerprint(value),
        "validation": report,
        "evaluation_executed": False,
        "promotion_executed": False,
        "gpu_execution_authorized": False,
    }
    return development, final, {"payload": receipt_payload, "sha256": fingerprint(receipt_payload)}


def materialize(
    capture: Path, public_output: Path, final_output: Path,
    expected_rlinf_commit: str, expected_maniskill_commit: str
) -> dict:
    if (public_output.exists() and any(public_output.iterdir())) or final_output.exists():
        raise ValueError("reset artifact output already exists")
    raw = json.loads(capture.read_text(encoding="utf-8"))
    development, final, receipt = validate_capture(raw, expected_rlinf_commit, expected_maniskill_commit)
    public_output.mkdir(parents=True, exist_ok=True)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    (public_output / "development.json").write_text(canonical_json(development.to_dict()) + "\n", encoding="utf-8")
    final_output.write_text(canonical_json(final.to_dict()) + "\n", encoding="utf-8")
    (public_output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--final-output", type=Path, required=True)
    parser.add_argument("--expected-rlinf-commit", required=True)
    parser.add_argument("--expected-maniskill-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(materialize(
        args.capture, args.public_output, args.final_output,
        args.expected_rlinf_commit, args.expected_maniskill_commit
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
