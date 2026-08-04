#!/usr/bin/env python3
"""Run the meeting-safe real CPU toy-policy improvement demonstration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import ContractError  # noqa: E402
from supervisor.toy_demo import ToyDemoError, run_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=ROOT)
    arguments = parser.parse_args()
    try:
        result = run_demo(
            root=ROOT,
            repository=arguments.repository,
            output=arguments.output,
        )
    except (ToyDemoError, ContractError) as error:
        print(f"Real policy demo refused to run: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
