"""Resource snapshots and deterministic D1 cost-threshold accounting."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CostTracker:
    hourly_price_usd: float
    max_cost_usd: float
    thresholds_usd: list[float]
    initial_cost_usd: float = 0.0
    started_monotonic: float = field(default_factory=time.monotonic)
    _reported: set[float] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._reported.update(
            value for value in self.thresholds_usd if value <= self.initial_cost_usd
        )

    def cost(self, now: float | None = None) -> float:
        elapsed = (now if now is not None else time.monotonic()) - self.started_monotonic
        return self.initial_cost_usd + max(0.0, elapsed) / 3600.0 * self.hourly_price_usd

    def run_cost(self, now: float | None = None) -> float:
        return self.cost(now) - self.initial_cost_usd

    def crossed_thresholds(self, now: float | None = None) -> list[float]:
        current = self.cost(now)
        crossed = [
            value
            for value in self.thresholds_usd
            if value <= current and value not in self._reported
        ]
        self._reported.update(crossed)
        return crossed

    def cap_reached(self, now: float | None = None) -> bool:
        return self.cost(now) >= self.max_cost_usd

    def seconds_until_cap(self) -> float:
        if self.hourly_price_usd <= 0:
            return float("inf")
        remaining = max(0.0, self.max_cost_usd - self.cost())
        return remaining / self.hourly_price_usd * 3600.0


def _nvidia_snapshot() -> list[dict[str, Any]]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 4:
            gpus.append(
                {
                    "name": parts[0],
                    "memory_total_mib": float(parts[1]),
                    "memory_used_mib": float(parts[2]),
                    "utilization_percent": float(parts[3]),
                }
            )
    return gpus


def resource_snapshot(path: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(path)
    return {
        "timestamp_unix": time.time(),
        "gpus": _nvidia_snapshot(),
        "disk_total_bytes": disk.total,
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
    }
