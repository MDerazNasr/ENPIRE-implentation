#!/usr/bin/env python3
"""Rehash every curated artifact in a real toy-policy demo bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.toy_demo import ToyDemoError, verify_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    arguments = parser.parse_args()
    try:
        artifacts = verify_manifest(arguments.bundle)
    except ToyDemoError as error:
        print(f"Real policy bundle verification failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "verified",
                "bundle": str(arguments.bundle.resolve()),
                "artifact_count": len(artifacts),
                "artifacts": [artifact.to_dict() for artifact in artifacts],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
