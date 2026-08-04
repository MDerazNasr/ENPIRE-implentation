#!/usr/bin/env python3
"""No-GPU subprocess fixture for the M5 D1 backend integration tests/demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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
    parser.add_argument("--fixture-execute", action="store_true")
    arguments = parser.parse_args()
    if not arguments.fixture_execute:
        parser.error("fixture execution requires --fixture-execute")
    config = json.loads(arguments.config.read_text(encoding="utf-8"))
    command = json.loads(arguments.logical_command_json)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        parser.error("logical command must be a JSON string list")
    run_directory = arguments.results_root / "d1" / arguments.run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    started_at = timestamp()
    wandb_run_id = re.sub(r"[^A-Za-z0-9_-]", "-", arguments.run_id)
    wandb_url = f"https://wandb.ai/fixture/qualia-rlt/runs/{wandb_run_id}"
    success = float(config.get("fixture_success_rate", 0.5))
    episode_length = float(config.get("fixture_episode_length", 40))
    log_text = (
        "Evaluation\n"
        f"success_once={success} successful_episode_length={episode_length}\n"
        "Training/Other\n"
        "actor_loss=0.25\n"
        f"wandb: View run at {wandb_url}\n"
    )
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
    (run_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
