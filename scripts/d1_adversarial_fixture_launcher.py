#!/usr/bin/env python3
"""Fault-injection wrapper for bounded D1 subprocess acceptance only."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import m5_fixture_launcher


SCENARIOS = {
    "happy",
    "timeout",
    "missing-artifact",
    "hash-mismatch",
    "cost-overrun",
    "failure-normalization",
}


def scenario_from_run_id(run_id: str) -> str:
    for scenario in SCENARIOS:
        if run_id.startswith(f"d1-{scenario}-"):
            return scenario
    raise ValueError(f"run ID does not select a D1 acceptance scenario: {run_id}")


def mutate_fixture_artifacts(results_root: Path, run_id: str, scenario: str) -> int:
    """Apply one deliberate terminal-artifact fault and return the process code."""

    run_directory = results_root / "d1" / run_id
    manifest_path = run_directory / "manifest.json"
    if scenario == "happy":
        return 0
    if scenario == "missing-artifact":
        manifest_path.unlink()
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if scenario == "hash-mismatch":
        manifest["config_sha256"] = "0" * 64
    elif scenario == "cost-overrun":
        manifest["run_cost_usd"] = 999
        manifest["final_cost_usd"] = 999
    elif scenario == "failure-normalization":
        manifest["status"] = "failed"
        manifest["exit_code"] = 7
    else:
        raise ValueError(f"unsupported post-run D1 acceptance scenario: {scenario}")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 7 if scenario == "failure-normalization" else 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    arguments, _ = parser.parse_known_args()
    scenario = scenario_from_run_id(arguments.run_id)
    if scenario == "timeout":
        time.sleep(30)
        return 0
    m5_fixture_launcher.main()
    return mutate_fixture_artifacts(
        arguments.results_root,
        arguments.run_id,
        scenario,
    )


if __name__ == "__main__":
    raise SystemExit(main())
