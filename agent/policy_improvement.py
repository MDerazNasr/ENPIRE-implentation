"""Run RLinf, read metrics, apply one Phase 1 rule, and keep or revert.

RLinf remains an external, unmodified training system. This module passes
Hydra overrides to its existing RLT entry point and never imports RLinf code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.metrics import parse_metrics, summarize_metrics
from agent.rules import compare_runs, propose_adjustment


PHASE1_FIELDS = {
    "learning_rate": float,
    "regularization_strength": float,
    "training_iterations": int,
    "episode_steps": int,
}


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    return_code: int
    elapsed_seconds: float
    parameters: dict[str, float]
    metrics: dict[str, list[float]]
    summary: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_phase1_overrides(path: Path) -> dict[str, float | int]:
    """Load the documented four-field YAML subset without adding a dependency."""

    raw: dict[str, str] = {}
    for line_number, original in enumerate(path.read_text().splitlines(), start=1):
        line = original.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"{path}:{line_number}: expected 'field: value'")
        key, value = (part.strip() for part in line.split(":", 1))
        if not key or not value:
            raise ValueError(f"{path}:{line_number}: field and value are required")
        if key in raw:
            raise ValueError(f"{path}:{line_number}: duplicate field {key!r}")
        raw[key] = value

    missing = sorted(PHASE1_FIELDS.keys() - raw.keys())
    unknown = sorted(raw.keys() - PHASE1_FIELDS.keys())
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unknown:
            details.append(f"unknown {unknown}")
        raise ValueError("Phase 1 config must contain exactly four fields: " + "; ".join(details))

    parsed: dict[str, float | int] = {}
    for key, parser in PHASE1_FIELDS.items():
        try:
            parsed[key] = parser(raw[key])
        except ValueError as error:
            raise ValueError(f"invalid value for {key}: {raw[key]!r}") from error

    if any(float(value) <= 0 for value in parsed.values()):
        raise ValueError("all Phase 1 override values must be positive")
    return parsed


def build_rlinf_manifest(
    overrides: dict[str, float | int],
    *,
    rlinf_home: Path,
    model_path: Path,
    dataset_path: Path,
    config_name: str = "maniskill_rlt_stage2_ac_mlp",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Merge Phase 1's four fields into the verified upstream launch template."""

    iterations = int(overrides["training_iterations"])
    episode_steps = int(overrides["episode_steps"])
    return {
        "working_directory": str(rlinf_home),
        "python": str(rlinf_home / ".venv/bin/python"),
        "entrypoint": str(rlinf_home / "examples/embodiment/train_embodied_agent.py"),
        "environment": {
            "EMBODIED_PATH": str(rlinf_home / "examples/embodiment"),
            "PYTHONPATH": str(rlinf_home),
            "RAY_TMPDIR": "/tmp/qualia-ray-{run_id}",
            "SAPIEN_RENDER_SYSTEM": "egl",
        },
        "base_args": [
            "--config-path",
            str(rlinf_home / "examples/embodiment/config"),
            "--config-name",
            config_name,
            "runner.logger.logger_backends=null",
            "runner.only_eval=false",
            f"runner.max_steps={iterations}",
            "runner.val_check_interval=1",
            "runner.save_interval=-1",
            "env.train.total_num_envs=1",
            f"env.train.max_episode_steps={episode_steps}",
            f"env.train.max_steps_per_rollout_epoch={episode_steps}",
            "env.train.rlt_policy_switch.task_mode=critical_phase",
            "env.train.rlt_policy_switch.trigger_mode=always_on",
            "env.train.rlt_policy_switch.expert_takeover.enable=false",
            "env.eval.total_num_envs=1",
            f"env.eval.max_episode_steps={episode_steps}",
            f"env.eval.max_steps_per_rollout_epoch={episode_steps}",
            "env.eval.rlt_policy_switch.task_mode=critical_phase",
            "env.eval.rlt_policy_switch.trigger_mode=always_on",
            "env.eval.rlt_policy_switch.expert_takeover.enable=false",
            f"rollout.rlt_feature_model.model_path={model_path}",
            f"+rollout.rlt_feature_model.openpi_data.norm_stats_path={dataset_path}/norm_stats.json",
            "rollout.expert_model=null",
            "actor.micro_batch_size=1",
            "actor.global_batch_size=1",
            "algorithm.actor_weight_schedule.enable=false",
            "algorithm.update_epoch=1",
            "algorithm.replay_buffer.min_buffer_size=1",
            "algorithm.rlt_schedule.warmup_min_size=1",
            "algorithm.rlt_schedule.warmup_post_collect_updates=1",
            "algorithm.rlt_schedule.train_every_transitions=1",
            "algorithm.rlt_schedule.max_updates_per_train_step=1",
        ],
        "logger_path_override": "runner.logger.log_path",
        "parameters": {
            "learning_rate": {
                "override": "actor.optim.lr",
                "value": float(overrides["learning_rate"]),
            },
            "regularization_strength": {
                "override": "algorithm.bc_weight",
                "value": float(overrides["regularization_strength"]),
            },
        },
        "timeout_seconds": timeout_seconds,
    }


def _format_override(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build_command(
    manifest: dict[str, Any],
    run_id: str,
    run_dir: Path,
    parameters: dict[str, float],
) -> tuple[list[str], Path, dict[str, str]]:
    context = {"run_id": run_id, "run_dir": str(run_dir)}
    working_directory = Path(manifest["working_directory"])
    command = [manifest["python"], manifest["entrypoint"], *manifest["base_args"]]
    command.append(f"{manifest['logger_path_override']}={run_dir}")
    for name, spec in manifest["parameters"].items():
        command.append(f"{spec['override']}={_format_override(parameters[name])}")

    environment = os.environ.copy()
    environment.update(
        {
            key: str(value).format_map(context)
            for key, value in manifest.get("environment", {}).items()
        }
    )
    return command, working_directory, environment


def execute_run(
    manifest: dict[str, Any],
    run_id: str,
    session_dir: Path,
    parameters: dict[str, float],
) -> RunResult:
    run_dir = session_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    command, working_directory, environment = build_command(
        manifest, run_id, run_dir, parameters
    )
    _write_json(
        run_dir / "resolved_config.json",
        {
            "run_id": run_id,
            "created_at": _utc_now(),
            "working_directory": str(working_directory),
            "command": command,
            "parameters": parameters,
        },
    )
    (run_dir / "command.sh").write_text(shlex.join(command) + "\n")

    started = time.monotonic()
    timed_out = threading.Event()
    process = subprocess.Popen(
        command,
        cwd=working_directory,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def terminate_on_timeout() -> None:
        if process.poll() is None:
            timed_out.set()
            process.terminate()

    timer = threading.Timer(float(manifest["timeout_seconds"]), terminate_on_timeout)
    timer.daemon = True
    timer.start()
    log_path = run_dir / "run.log"
    try:
        with log_path.open("w") as log_file:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log_file.write(line)
                    log_file.flush()
            finally:
                process.stdout.close()
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    finally:
        timer.cancel()

    if timed_out.is_set():
        return_code = 124
    elapsed = time.monotonic() - started
    metrics = parse_metrics(log_path.read_text(errors="replace"))
    summary = summarize_metrics(metrics)
    summary.update(
        {
            "return_code": return_code,
            "elapsed_seconds": elapsed,
            "timed_out": timed_out.is_set(),
        }
    )
    _write_json(run_dir / "metrics.json", metrics)
    _write_json(run_dir / "summary.json", summary)
    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        return_code=return_code,
        elapsed_seconds=elapsed,
        parameters=dict(parameters),
        metrics=metrics,
        summary=summary,
    )


def _record(result: RunResult, status: str, decision: str = "") -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "status": status,
        "learning_rate": result.parameters["learning_rate"],
        "regularization_strength": result.parameters["regularization_strength"],
        "success": result.summary.get("success"),
        "loss": result.summary.get("loss"),
        "loss_key": result.summary.get("loss_key"),
        "return_code": result.return_code,
        "elapsed_seconds": round(result.elapsed_seconds, 3),
        "decision": decision,
    }


def _write_run_table(session_dir: Path, records: list[dict[str, Any]]) -> None:
    columns = [
        "run_id",
        "status",
        "learning_rate",
        "regularization_strength",
        "success",
        "loss",
        "loss_key",
        "return_code",
        "elapsed_seconds",
        "decision",
    ]
    with (session_dir / "run_table.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in columns} for row in records)


def _append_run_ledger(
    output_root: Path, session_id: str, records: list[dict[str, Any]]
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "phase1_runs.jsonl").open("a") as handle:
        for record in records:
            payload = {"session_id": session_id, "recorded_at": _utc_now(), **record}
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _finish(
    session_dir: Path,
    output_root: Path,
    session_id: str,
    result: dict[str, Any],
    records: list[dict[str, Any]],
    selected_parameters: dict[str, float] | None,
) -> dict[str, Any]:
    _write_run_table(session_dir, records)
    if selected_parameters is not None:
        _write_json(session_dir / "selected_config.json", selected_parameters)
    _write_json(session_dir / "experiment_summary.json", result)
    _append_run_ledger(output_root, session_id, records)
    return result


def run_experiment(
    manifest: dict[str, Any], output_root: Path, session_id: str
) -> dict[str, Any]:
    session_dir = output_root / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    _write_json(session_dir / "resolved_launch.json", manifest)
    parameters = {
        name: float(spec["value"]) for name, spec in manifest["parameters"].items()
    }

    baseline = execute_run(manifest, "run_000_baseline", session_dir, parameters)
    records = [_record(baseline, "baseline")]
    if baseline.return_code != 0:
        records[0]["decision"] = "run failed; no adjustment launched"
        result = {
            "status": "failed",
            "selected_run": None,
            "reason": records[0]["decision"],
            "records": records,
        }
        return _finish(session_dir, output_root, session_id, result, records, None)

    proposed, trigger_reason = propose_adjustment(parameters, baseline.metrics)
    if trigger_reason is None:
        records[0]["decision"] = "continue: rule did not trigger"
        result = {
            "status": "complete",
            "selected_run": baseline.run_id,
            "reason": records[0]["decision"],
            "records": records,
        }
        return _finish(
            session_dir, output_root, session_id, result, records, baseline.parameters
        )

    adjusted = execute_run(manifest, "run_001_adjusted", session_dir, proposed)
    if adjusted.return_code != 0:
        action, decision = "revert", "adjusted run failed; reverted to baseline"
    else:
        action, decision = compare_runs(baseline.summary, adjusted.summary)
    records[0]["decision"] = trigger_reason
    records.append(_record(adjusted, "kept" if action == "keep" else "reverted", decision))
    selected = adjusted if action == "keep" else baseline
    result = {
        "status": "complete" if adjusted.return_code == 0 else "partial",
        "selected_run": selected.run_id,
        "reason": decision,
        "trigger_reason": trigger_reason,
        "records": records,
    }
    return _finish(
        session_dir, output_root, session_id, result, records, selected.parameters
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/phase1_overrides.yaml")
    )
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--session-id")
    parser.add_argument("--print-command", action="store_true")
    args = parser.parse_args(argv)

    rlinf_home = os.environ.get("RLINF_HOME")
    model_path = os.environ.get("MODEL_PATH")
    dataset_path = os.environ.get("DATASET_PATH")
    missing = [
        name
        for name, value in (
            ("RLINF_HOME", rlinf_home),
            ("MODEL_PATH", model_path),
            ("DATASET_PATH", dataset_path),
        )
        if not value
    ]
    if missing:
        parser.error("required environment variable(s) not set: " + ", ".join(missing))

    overrides = load_phase1_overrides(args.config)
    manifest = build_rlinf_manifest(
        overrides,
        rlinf_home=Path(rlinf_home),
        model_path=Path(model_path),
        dataset_path=Path(dataset_path),
        config_name=os.environ.get(
            "RLINF_CONFIG_NAME", "maniskill_rlt_stage2_ac_mlp"
        ),
        timeout_seconds=int(os.environ.get("RUN_TIMEOUT_SECONDS", "1800")),
    )
    session_id = args.session_id or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    if args.print_command:
        parameters = {
            name: float(spec["value"])
            for name, spec in manifest["parameters"].items()
        }
        command, cwd, _ = build_command(
            manifest,
            "run_000_baseline",
            args.results_root / session_id / "run_000_baseline",
            parameters,
        )
        print(f"cwd: {cwd}")
        print(shlex.join(command))
        return 0

    result = run_experiment(manifest, args.results_root, session_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
