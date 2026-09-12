#!/usr/bin/env python3
"""Run the frozen G0 evaluator contract and append an anchored result."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "supervisor").is_dir() else HERE.parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import canonical_json, fingerprint
from supervisor.evaluator_integrity import EpisodeBatch, ResetSetArtifact, evaluate_episode_batches


TOP_LEVEL_KEYS = {
    "schema_version", "reset_set", "expected_seeds", "incumbent_commit",
    "candidate_commit", "batches", "evaluator_version",
    "evaluator_source_hash", "evaluator_environment_hash",
}
BATCH_KEYS = {
    "trial_id", "condition", "seed", "candidate_commit", "reset_set_hash",
    "reset_ids", "success_once",
}


def evaluate_input(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_KEYS:
        raise ValueError("evaluator input fields are invalid")
    if value["schema_version"] != 1:
        raise ValueError("evaluator input schema version is unsupported")
    raw_batches = value["batches"]
    if not isinstance(raw_batches, list):
        raise ValueError("evaluator batches must be a list")
    parsed = []
    for raw in raw_batches:
        if not isinstance(raw, dict) or set(raw) != BATCH_KEYS:
            raise ValueError("episode batch fields are invalid")
        parsed.append(EpisodeBatch.create(**raw))
    return evaluate_episode_batches(
        reset_set=ResetSetArtifact.from_dict(value["reset_set"]),
        expected_seeds=value["expected_seeds"],
        incumbent_commit=value["incumbent_commit"],
        candidate_commit=value["candidate_commit"],
        batches=parsed,
        evaluator_version=value["evaluator_version"],
        evaluator_source_hash=value["evaluator_source_hash"],
        evaluator_environment_hash=value["evaluator_environment_hash"],
    )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_anchored(ledger: Path, anchor: Path, result: dict) -> dict:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if ledger.exists() != anchor.exists():
            raise ValueError("evaluation ledger and trusted anchor presence mismatch")
        records = []
        previous = None
        if ledger.exists():
            for index, line in enumerate(ledger.read_text(encoding="utf-8").splitlines()):
                record = json.loads(line)
                if set(record) != {"sequence", "previous_hash", "result", "record_hash"}:
                    raise ValueError("evaluation ledger record fields are invalid")
                body = {"sequence": index, "previous_hash": previous, "result": record["result"]}
                if record["sequence"] != index or record["previous_hash"] != previous or record["record_hash"] != fingerprint(body):
                    raise ValueError("evaluation ledger chain is invalid")
                previous = record["record_hash"]
                records.append(record)
        if anchor.exists():
            trusted = json.loads(anchor.read_text(encoding="utf-8"))
            if trusted != {"sequence_count": len(records), "head_hash": previous}:
                raise ValueError("evaluation ledger trusted anchor mismatch")
        body = {"sequence": len(records), "previous_hash": previous, "result": result}
        record = {**body, "record_hash": fingerprint(body)}
        with ledger.open("ab") as output:
            output.write((canonical_json(record) + "\n").encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        _atomic_write(anchor, (canonical_json({"sequence_count": len(records) + 1, "head_hash": record["record_hash"]}) + "\n").encode("utf-8"))
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--anchor", type=Path)
    args = parser.parse_args()
    if bool(args.ledger) != bool(args.anchor):
        parser.error("--ledger and --anchor must be supplied together")
    result = evaluate_input(json.loads(args.input.read_text(encoding="utf-8")))
    if args.ledger:
        append_anchored(args.ledger, args.anchor, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
