#!/usr/bin/env python3
"""Validate one M6 actor-objective plugin and emit a canonical JSON record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.objective_validation import evaluate_objective_plugin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--require-behavior-change", action="store_true")
    arguments = parser.parse_args()
    plugin = Path(arguments.plugin)
    result = evaluate_objective_plugin(
        plugin,
        display_path=arguments.plugin,
        require_behavior_change=arguments.require_behavior_change,
    )
    print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
