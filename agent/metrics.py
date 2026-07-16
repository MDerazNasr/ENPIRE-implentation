"""Normalize the metrics emitted by an RLinf training subprocess.

This module deliberately has no RLinf imports. Phase 1 treats the upstream
training system as an external process and reads only the artifacts it emits.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
METRIC = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_.\-/]*)="
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[-+]?inf|nan)",
    re.IGNORECASE,
)


def _clean_line(line: str) -> str:
    return ANSI_ESCAPE.sub("", line).replace("\r", "\n")


def parse_metrics(text: str) -> dict[str, list[float]]:
    """Parse the tqdm lines and rich metric tables used by the RLT example.

    TODO(Phase 1): replace this text parser with RLinf's stable structured
    metrics file once its exact emitted path and schema are pinned upstream.
    Until then, raw logs are retained beside every normalized metrics file.
    """

    histories: dict[str, list[float]] = {}
    section: str | None = None
    section_markers = {
        "Environment": "environment",
        "Evaluation": "eval",
        "Training/Other": "training",
        "Replay Buffer": "replay",
        "Time": "time",
    }

    for raw_line in _clean_line(text).splitlines():
        for marker, prefix in section_markers.items():
            if marker in raw_line and "Metric Table" not in raw_line:
                section = prefix
                break

        for match in METRIC.finditer(raw_line):
            key = match.group("key")
            if section and "/" not in key:
                key = f"{section}/{key}"
            histories.setdefault(key, []).append(float(match.group("value")))

    return histories


def _last_metric(
    histories: dict[str, list[float]], candidates: Iterable[str]
) -> tuple[str | None, float | None]:
    for key in candidates:
        values = histories.get(key)
        if values:
            return key, values[-1]
    return None, None


def summarize_metrics(histories: dict[str, list[float]]) -> dict[str, Any]:
    """Select the success and loss values used by the Phase 1 rule."""

    success_key, success = _last_metric(
        histories,
        ("eval/success_once", "success_once", "environment/success_once"),
    )
    loss_key, loss = _last_metric(
        histories,
        (
            "train/loss",
            "sac/actor_loss",
            "actor/bc_loss",
            "sac/critic_loss",
            "training/actor_loss",
            "training/bc_loss",
            "training/critic_loss",
            "actor_loss",
            "bc_loss",
            "critic_loss",
            "loss",
        ),
    )
    if loss is None:
        fallback = [
            key
            for key, values in histories.items()
            if values and (key.endswith("/loss") or key.endswith("_loss"))
        ]
        if fallback:
            loss_key = fallback[0]
            loss = histories[loss_key][-1]

    return {
        "success_key": success_key,
        "success": success,
        "loss_key": loss_key,
        "loss": loss,
    }
