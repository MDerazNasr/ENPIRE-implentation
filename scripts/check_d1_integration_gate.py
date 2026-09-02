#!/usr/bin/env python3
"""Audit a D1 repository and replay its Stage-7 pack without modifying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from supervisor.d1_gate import (
    DEFAULT_PACK_PATH,
    D1GateStatus,
    run_d1_integration_gate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d1-repository", required=True, type=Path)
    parser.add_argument("--pack-relative-path", type=Path, default=DEFAULT_PACK_PATH)
    arguments = parser.parse_args()
    result = run_d1_integration_gate(
        arguments.d1_repository,
        pack_relative_path=arguments.pack_relative_path,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    raise SystemExit(0 if result.status == D1GateStatus.READY else 2)


if __name__ == "__main__":
    main()
