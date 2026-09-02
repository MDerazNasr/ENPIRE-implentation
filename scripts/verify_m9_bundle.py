#!/usr/bin/env python3
"""Verify every artifact in an M9 meeting bundle against its manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.delivery import DeliveryError, verify_artifact_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    arguments = parser.parse_args()
    try:
        artifacts = verify_artifact_manifest(arguments.bundle)
    except DeliveryError as error:
        print(f"M9 bundle verification failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "verified",
                "bundle": str(arguments.bundle.resolve()),
                "artifact_count": len(artifacts),
                "artifacts": [item.to_dict() for item in artifacts],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
