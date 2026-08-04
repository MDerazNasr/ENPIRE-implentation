#!/usr/bin/env python3
"""No-GPU subprocess fixture for the M5 D1 backend integration tests/demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.objective_validation import (  # noqa: E402
    OBJECTIVE_CONTRACT_VERSION,
    evaluate_objective_plugin,
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--logical-command-json", required=True)
    parser.add_argument("--objective-plugin", type=Path)
    parser.add_argument("--objective-display-path")
    parser.add_argument("--objective-sha256")
    parser.add_argument("--objective-contract-version")
    parser.add_argument("--fixture-execute", action="store_true")
    arguments = parser.parse_args()
    if not arguments.fixture_execute:
        parser.error("fixture execution requires --fixture-execute")
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    command = json.loads(arguments.logical_command_json)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        parser.error("logical command must be a JSON string list")
    objective_arguments = (
        arguments.objective_plugin,
        arguments.objective_display_path,
        arguments.objective_sha256,
        arguments.objective_contract_version,
    )
    if any(item is not None for item in objective_arguments) and not all(
        item is not None for item in objective_arguments
    ):
        parser.error("objective fixture arguments must be all present or all absent")
    objective_result = None
    if arguments.objective_plugin is not None:
        if arguments.objective_contract_version != OBJECTIVE_CONTRACT_VERSION:
            parser.error("objective contract version is unsupported")
        actual_hash = hashlib.sha256(arguments.objective_plugin.read_bytes()).hexdigest()
        if actual_hash != arguments.objective_sha256:
            parser.error("objective source hash mismatch")
        objective_result = evaluate_objective_plugin(
            arguments.objective_plugin,
            display_path=arguments.objective_display_path,
            require_behavior_change=True,
        )
        if not objective_result.passed:
            parser.error("objective plugin failed its runtime contract")
    run_directory = arguments.results_root / "d1" / arguments.run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    started_at = timestamp()
    wandb_run_id = re.sub(r"[^A-Za-z0-9_-]", "-", arguments.run_id)
    wandb_url = f"https://wandb.ai/fixture/qualia-rlt/runs/{wandb_run_id}"
    success_key = (
        "fixture_code_success_rate"
        if objective_result is not None
        else "fixture_success_rate"
    )
    success = float(config.get(success_key, config.get("fixture_success_rate", 0.5)))
    episode_length = float(config.get("fixture_episode_length", 40))
    log_lines = [
        "Evaluation",
        f"success_once={success} successful_episode_length={episode_length}",
        "Training/Other",
        "actor_loss=0.25",
    ]
    if objective_result is not None:
        log_lines.append("objective_behavior_changed=1")
    log_lines.append(f"wandb: View run at {wandb_url}")
    log_text = "\n".join(log_lines) + "\n"
    (run_directory / "run.log").write_text(log_text, encoding="utf-8")
    finished_at = timestamp()
    expected_rlinf = config["expected_rlinf_commit"]
    manifest = {
        "schema_version": 1,
        "created_at": started_at,
        "experiment_id": config["experiment_id"],
        "condition": config["condition"],
        "project_commit": git_head(Path.cwd()),
        "project_start_commit": config.get("project_start_commit"),
        "rlinf_commit_expected": expected_rlinf,
        "rlinf_commit_actual": expected_rlinf,
        "config_path": str(arguments.config),
        "config_sha256": hashlib.sha256(arguments.config.read_bytes()).hexdigest(),
        "resolved_config": config,
        "command": command,
        "working_directory": str(Path.cwd()),
        "run_directory": str(run_directory),
        "host": "m5-fixture",
        "platform": "fixture",
        "hourly_price_usd": 0,
        "wandb_run_url": wandb_url,
        "status": "complete",
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": 0,
        "elapsed_seconds": 0.01,
        "run_cost_usd": 0,
        "final_cost_usd": 0,
    }
    if objective_result is not None:
        manifest.update(
            {
                "objective_sha256": arguments.objective_sha256,
                "objective_contract_version": arguments.objective_contract_version,
                "objective_validation": objective_result.to_dict(),
            }
        )
    (run_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
