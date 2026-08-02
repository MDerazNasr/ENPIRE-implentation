"""Create local, secret-free provenance records for D1 runs."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git_revision(repo: Path) -> str | None:
    if not repo.is_dir():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    command: list[str],
    cwd: Path,
    run_dir: Path,
    project_root: Path,
    hourly_price_usd: float | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "experiment_id": config["experiment_id"],
        "condition": config["condition"],
        "project_commit": git_revision(project_root),
        "project_start_commit": config.get("project_start_commit"),
        "rlinf_commit_expected": config["expected_rlinf_commit"],
        "rlinf_commit_actual": git_revision(cwd),
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256_file(config_path),
        "resolved_config": dict(config),
        "command": command,
        "working_directory": str(cwd),
        "run_directory": str(run_dir.resolve()),
        "host": platform.node(),
        "platform": platform.platform(),
        "hourly_price_usd": hourly_price_usd,
        "wandb_run_url": None,
        "status": "planned",
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "elapsed_seconds": None,
        "final_cost_usd": None,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
