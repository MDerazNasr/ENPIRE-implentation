#!/usr/bin/env python3
"""Create one canonical E1 baseline metric from four complete shard receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from supervisor.canonical import fingerprint
from supervisor.e1_sharded_evaluation import aggregate_shard_receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in args.receipt]
    payload = aggregate_shard_receipts(receipts)
    envelope = {"payload": payload, "sha256": fingerprint(payload)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
