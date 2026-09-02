#!/usr/bin/env python3
"""Write D1 readiness, and publish a canonical pack only from valid inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from supervisor.d1_pack_builder import (
    DEFAULT_BUILD_SPEC,
    DEFAULT_PACK_OUTPUT,
    DEFAULT_READINESS_OUTPUT,
    D1PackBuildError,
    atomic_write,
    build_canonical_pack,
    current_readiness_payload,
    pack_bytes,
    readiness_bytes,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--source", type=Path, default=DEFAULT_BUILD_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_PACK_OUTPUT)
    parser.add_argument(
        "--readiness-output", type=Path, default=DEFAULT_READINESS_OUTPUT
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="write the canonical pack only if every strict publication gate passes",
    )
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()

    payload = current_readiness_payload(
        repository, source_path=arguments.source, output_path=arguments.output
    )
    pack = None
    build_error = None
    if (repository / arguments.source).is_file():
        try:
            pack = build_canonical_pack(
                repository, source_path=arguments.source, output_path=arguments.output
            )
        except D1PackBuildError as error:
            build_error = str(error)
            payload["status"] = "blocked"
            payload["blockers"].append(
                {
                    "code": "strict_build_validation_failed",
                    "category": "packaging",
                    "detail": build_error,
                    "evidence": [arguments.source.as_posix()],
                }
            )
        else:
            payload["status"] = "ready"
            payload["canonical_pack_claimed"] = bool(arguments.publish)
            payload["blockers"] = []

    if arguments.publish and pack is not None and build_error is None:
        atomic_write(repository / arguments.output, pack_bytes(pack))
        payload["canonical_pack_exists"] = True
        payload["canonical_pack_claimed"] = True
        for role in payload["artifact_role_coverage"]:
            role["canonical_artifact_materialized"] = True

    readiness_path = repository / arguments.readiness_output
    atomic_write(readiness_path, readiness_bytes(payload))

    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    raise SystemExit(0 if payload["status"] == "ready" else 2)


if __name__ == "__main__":
    main()
