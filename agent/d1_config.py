"""Load, validate, and resolve D1 experiment profiles without RLinf imports."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
RLINF_COMMIT = "c90951a0c799a750cb5294ed10587c61cc2af8bf"
PROJECT_START_COMMIT = "8c5abfcd04e8b4a155f82e8b3537169169ef8337"
PLACEHOLDER_WORDS = ("changeme", "placeholder", "todo", "path/to")
VARIABLE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "experiment_id",
    "stage",
    "condition",
    "rlinf_config",
    "expected_rlinf_commit",
    "required_paths",
    "hydra_overrides",
    "evaluation",
    "scientific_values",
    "budget",
}


class D1ConfigError(ValueError):
    """Raised when a D1 profile violates the frozen Stage-0 contract."""


def load_d1_config(path: Path) -> dict[str, Any]:
    """Load a JSON-compatible YAML profile and validate its contract."""

    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise D1ConfigError(
            f"{path}: D1 profiles must be JSON-compatible YAML: {error}"
        ) from error
    if not isinstance(config, dict):
        raise D1ConfigError(f"{path}: top-level value must be an object")
    validate_d1_config(config)
    return config


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def validate_d1_config(config: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_TOP_LEVEL - config.keys())
    if missing:
        raise D1ConfigError(f"missing required fields: {missing}")
    if config["schema_version"] != SCHEMA_VERSION:
        raise D1ConfigError(f"schema_version must be {SCHEMA_VERSION}")
    if config["expected_rlinf_commit"] != RLINF_COMMIT:
        raise D1ConfigError(f"expected_rlinf_commit must be pinned to {RLINF_COMMIT}")
    if config["condition"] not in {
        "pilot",
        "scientific_stage1",
        "smoke",
        "reference",
        "control",
        "candidate",
    }:
        raise D1ConfigError(f"unsupported condition: {config['condition']!r}")
    if not isinstance(config["required_paths"], dict) or not config["required_paths"]:
        raise D1ConfigError("required_paths must be a non-empty object")
    if not isinstance(config["hydra_overrides"], list) or not all(
        isinstance(value, str) and "=" in value for value in config["hydra_overrides"]
    ):
        raise D1ConfigError("hydra_overrides must contain key=value strings")
    evaluation = config["evaluation"]
    if not isinstance(evaluation, dict):
        raise D1ConfigError("evaluation must be an object")
    if config["stage"] == "stage2" and evaluation.get("fixed_reset_state_ids") is not True:
        raise D1ConfigError("Stage-2 evaluation must use fixed reset state IDs")
    budget = config["budget"]
    if not isinstance(budget, dict):
        raise D1ConfigError("budget must be an object")
    max_cost = budget.get("max_cost_usd")
    if not isinstance(max_cost, (int, float)) or not 0 < float(max_cost) <= 25:
        raise D1ConfigError("max_cost_usd must be positive and may not exceed $25")
    thresholds = budget.get("report_thresholds_usd")
    if thresholds != sorted(set(thresholds or [])):
        raise D1ConfigError("report thresholds must be unique and increasing")
    if any(float(value) <= 0 or float(value) > float(max_cost) for value in thresholds):
        raise D1ConfigError("report thresholds must be within the run cost cap")
    for value in _walk_strings(config):
        lowered = value.lower()
        if any(word in lowered for word in PLACEHOLDER_WORDS):
            raise D1ConfigError(f"placeholder value is forbidden: {value!r}")
    if any("expert_takeover.enable=true" in value for value in config["hydra_overrides"]):
        raise D1ConfigError("D1 expert takeover must remain disabled")


def referenced_environment(config: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for value in _walk_strings(config):
        names.update(VARIABLE.findall(value))
    return names


def resolve_environment(value: Any, environment: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if not environment.get(name):
                raise D1ConfigError(f"required environment variable is not set: {name}")
            return environment[name]

        return VARIABLE.sub(replace, value)
    if isinstance(value, list):
        return [resolve_environment(item, environment) for item in value]
    if isinstance(value, dict):
        return {key: resolve_environment(item, environment) for key, item in value.items()}
    return value


def resolve_d1_config(
    config: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    resolved = resolve_environment(dict(config), environment or os.environ)
    validate_d1_config(resolved)
    return resolved


def validate_required_paths(config: Mapping[str, Any]) -> None:
    failures: list[str] = []
    for label, spec in config["required_paths"].items():
        if not isinstance(spec, dict) or "path" not in spec or "kind" not in spec:
            failures.append(f"{label}: expected path/kind object")
            continue
        path = Path(spec["path"])
        kind = spec["kind"]
        if kind == "directory":
            valid = path.is_dir()
        elif kind == "file":
            valid = path.is_file()
        else:
            valid = False
        if not valid:
            failures.append(f"{label}: expected {kind} at {path}")
    if failures:
        raise D1ConfigError("required path validation failed: " + "; ".join(failures))


def build_d1_command(config: Mapping[str, Any], run_dir: Path) -> tuple[list[str], Path]:
    rlinf_home = Path(config["required_paths"]["rlinf_home"]["path"])
    command = [
        str(rlinf_home / ".venv/bin/python"),
        str(rlinf_home / "examples/embodiment/train_embodied_agent.py"),
        "--config-path",
        str(rlinf_home / "examples/embodiment/config"),
        "--config-name",
        config["rlinf_config"],
        *config["hydra_overrides"],
        f"runner.logger.log_path={run_dir}",
    ]
    return command, rlinf_home


def scientific_diff(
    control: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, tuple[Any, Any]]:
    """Return changed scientific values; used to enforce the one-factor boundary."""

    keys = set(control["scientific_values"]) | set(candidate["scientific_values"])
    return {
        key: (control["scientific_values"].get(key), candidate["scientific_values"].get(key))
        for key in sorted(keys)
        if control["scientific_values"].get(key) != candidate["scientific_values"].get(key)
    }
