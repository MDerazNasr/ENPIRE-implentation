#!/usr/bin/env python3
"""Harness-owned, no-process validation for a materialized D1 config."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.d1_config import (  # noqa: E402
    build_d1_command,
    load_d1_config,
    resolve_d1_config,
    validate_d1_config,
)
from supervisor.canonical import canonical_json, fingerprint  # noqa: E402


PLACEHOLDERS = {
    "RLINF_HOME": "/opt/enpire-d0/rlinf",
    "STAGE1_CHECKPOINT": "/opt/enpire-d0/stage1",
    "NORM_STATS_PATH": "/opt/enpire-d0/norm_stats.json",
    "WANDB_PROJECT": "enpire-d0-no-call",
    "D1_SEED": "2026",
}


def inspect_config(path: Path, *, dry_resolve: bool) -> dict:
    config = load_d1_config(path)
    validate_d1_config(config)
    result = {
        "schema_version": 1,
        "status": "passed",
        "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dry_resolved": dry_resolve,
        "process_launched": False,
    }
    if dry_resolve:
        resolved = resolve_d1_config(config, PLACEHOLDERS)
        command, cwd = build_d1_command(resolved, Path("/opt/enpire-d0/results"))
        result.update(
            resolved_config_hash=fingerprint(resolved),
            logical_command_hash=fingerprint(command),
            logical_command=command,
            logical_cwd=str(cwd),
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-resolve", action="store_true")
    args = parser.parse_args()
    print(canonical_json(inspect_config(args.config, dry_resolve=args.dry_resolve)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

