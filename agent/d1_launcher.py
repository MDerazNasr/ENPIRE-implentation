"""Safe D1 command planner and explicitly gated paid-run launcher."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from agent.d1_config import (
    D1ConfigError,
    RLINF_COMMIT,
    build_d1_command,
    load_d1_config,
    resolve_d1_config,
    validate_required_paths,
)
from agent.provenance import append_jsonl, create_manifest, utc_now, write_json
from agent.resources import CostTracker, resource_snapshot


SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _float_environment(name: str) -> float:
    value = os.environ.get(name)
    if not value:
        raise D1ConfigError(f"required environment variable is not set: {name}")
    try:
        parsed = float(value)
    except ValueError as error:
        raise D1ConfigError(f"{name} must be a number") from error
    if parsed <= 0:
        raise D1ConfigError(f"{name} must be positive")
    return parsed


def _prior_cumulative_cost(ledger_path: Path) -> float:
    if not ledger_path.exists():
        return 0.0
    total = 0.0
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            total += float(record.get("run_cost_usd") or record.get("final_cost_usd") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            raise D1ConfigError(f"invalid cumulative cost ledger: {ledger_path}")
    return total


def prepare_run(
    config_path: Path,
    results_root: Path,
    run_id: str,
    project_root: Path,
    hourly_price_usd: float | None,
) -> tuple[dict, list[str], Path, Path, dict]:
    if not SAFE_RUN_ID.fullmatch(run_id):
        raise D1ConfigError(
            "run ID must be 1-128 characters using letters, numbers, '.', '_', or '-'"
        )
    config = resolve_d1_config(load_d1_config(config_path))
    run_dir = results_root / "d1" / run_id
    command, cwd = build_d1_command(config, run_dir)
    manifest = create_manifest(
        config=config,
        config_path=config_path,
        command=command,
        cwd=cwd,
        run_dir=run_dir,
        project_root=project_root,
        hourly_price_usd=hourly_price_usd,
    )
    return config, command, cwd, run_dir, manifest


def _execute(
    config: dict,
    command: list[str],
    cwd: Path,
    run_dir: Path,
    manifest: dict,
    results_root: Path,
    hourly_price_usd: float,
) -> int:
    validate_required_paths(config)
    if manifest["rlinf_commit_actual"] != RLINF_COMMIT:
        raise D1ConfigError(
            "RLinf checkout mismatch: "
            f"expected {RLINF_COMMIT}, got {manifest['rlinf_commit_actual']}"
        )
    ledger_path = results_root / "d1_runs.jsonl"
    prior_cost = _prior_cumulative_cost(ledger_path)
    tracker = CostTracker(
        hourly_price_usd=hourly_price_usd,
        max_cost_usd=float(config["budget"]["max_cost_usd"]),
        thresholds_usd=[float(v) for v in config["budget"]["report_thresholds_usd"]],
        initial_cost_usd=prior_cost,
    )
    if tracker.cap_reached():
        raise D1ConfigError(
            f"cumulative D1 spend ${prior_cost:.2f} already meets the "
            f"${tracker.max_cost_usd:.2f} cap"
        )
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "manifest.json", manifest)
    (run_dir / "command.sh").write_text(shlex.join(command) + "\n")
    manifest.update(status="running", started_at=utc_now())
    write_json(run_dir / "manifest.json", manifest)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env={**os.environ, "SAPIEN_RENDER_SYSTEM": "egl"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def copy_output() -> None:
        assert process.stdout is not None
        with (run_dir / "run.log").open("w") as handle:
            for line in process.stdout:
                sys.stdout.write(line)
                handle.write(line)
                handle.flush()

    output_thread = threading.Thread(target=copy_output, daemon=True)
    output_thread.start()
    resource_path = run_dir / "resources.jsonl"
    event_path = run_dir / "events.jsonl"
    while process.poll() is None:
        snapshot = resource_snapshot(run_dir)
        snapshot["estimated_run_cost_usd"] = round(tracker.run_cost(), 6)
        snapshot["estimated_cumulative_cost_usd"] = round(tracker.cost(), 6)
        append_jsonl(resource_path, snapshot)
        for threshold in tracker.crossed_thresholds():
            event = {"at": utc_now(), "type": "cost_threshold", "usd": threshold}
            append_jsonl(event_path, event)
            print(f"D1 COST UPDATE: cumulative run estimate crossed ${threshold:.2f}")
        if tracker.cap_reached():
            append_jsonl(
                event_path,
                {"at": utc_now(), "type": "cost_cap", "usd": tracker.cost()},
            )
            process.terminate()
            break
        time.sleep(float(config.get("monitor_interval_seconds", 10)))

    try:
        return_code = process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait()
    output_thread.join(timeout=5)
    elapsed = time.monotonic() - tracker.started_monotonic
    run_cost = tracker.run_cost()
    cumulative_cost = tracker.cost()
    manifest.update(
        status="complete" if return_code == 0 else "failed",
        finished_at=utc_now(),
        exit_code=return_code,
        elapsed_seconds=elapsed,
        run_cost_usd=run_cost,
        cumulative_cost_usd=cumulative_cost,
        final_cost_usd=run_cost,
    )
    write_json(run_dir / "manifest.json", manifest)
    append_jsonl(ledger_path, manifest)
    return return_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-paid-run", action="store_true")
    args = parser.parse_args(argv)
    if args.acknowledge_paid_run and not args.execute:
        parser.error("--acknowledge-paid-run is valid only with --execute")
    if args.execute and not args.acknowledge_paid_run:
        parser.error("--execute requires --acknowledge-paid-run")

    project_root = Path(__file__).resolve().parents[1]
    results_root = (
        args.results_root
        if args.results_root.is_absolute()
        else project_root / args.results_root
    )
    hourly_price = _float_environment("GPU_HOURLY_PRICE_USD") if args.execute else None
    try:
        config, command, cwd, run_dir, manifest = prepare_run(
            args.config,
            results_root,
            args.run_id,
            project_root,
            hourly_price,
        )
        if not args.execute:
            print(json.dumps(manifest, indent=2, sort_keys=True))
            print(f"cwd: {cwd}")
            print(shlex.join(command))
            print("DRY RUN ONLY: pass --execute --acknowledge-paid-run to launch")
            return 0
        return _execute(
            config, command, cwd, run_dir, manifest, results_root, hourly_price
        )
    except D1ConfigError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
