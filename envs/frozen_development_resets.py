"""Fail-closed batching for the public G0 development reset artifact."""

from __future__ import annotations

import json
from pathlib import Path

from supervisor.evaluator_integrity import ResetSetArtifact


class FrozenDevelopmentResetError(ValueError):
    """Raised when a development reset schedule is invalid or exhausted."""


class FrozenDevelopmentResetSchedule:
    """Yield the exact 256 frozen development episode seeds once, in order."""

    def __init__(
        self,
        artifact: ResetSetArtifact,
        *,
        expected_sha256: str,
        batch_size: int,
    ) -> None:
        if artifact.role != "development":
            raise FrozenDevelopmentResetError(
                "only the public development reset artifact is permitted"
            )
        if artifact.fingerprint() != expected_sha256:
            raise FrozenDevelopmentResetError("development reset fingerprint mismatch")
        if batch_size <= 0 or len(artifact.reset_ids) % batch_size:
            raise FrozenDevelopmentResetError(
                "development reset count must be divisible by the environment batch"
            )
        self.artifact = artifact
        self.batch_size = int(batch_size)
        self._cursor = 0

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        expected_sha256: str,
        batch_size: int,
    ) -> "FrozenDevelopmentResetSchedule":
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            artifact = ResetSetArtifact.from_dict(value)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise FrozenDevelopmentResetError(
                f"invalid development reset artifact: {error}"
            ) from error
        return cls(
            artifact,
            expected_sha256=expected_sha256,
            batch_size=batch_size,
        )

    @property
    def fingerprint(self) -> str:
        return self.artifact.fingerprint()

    @property
    def consumed(self) -> int:
        return self._cursor

    @property
    def complete(self) -> bool:
        return self._cursor == len(self.artifact.reset_ids)

    def next_batch(self) -> list[int]:
        end = self._cursor + self.batch_size
        if end > len(self.artifact.reset_ids):
            raise FrozenDevelopmentResetError(
                "frozen development reset schedule is exhausted"
            )
        values = list(self.artifact.reset_ids[self._cursor:end])
        self._cursor = end
        return values
