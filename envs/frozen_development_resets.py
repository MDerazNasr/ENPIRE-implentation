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
        offset: int = 0,
        count: int | None = None,
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
        selected_count = len(artifact.reset_ids) - offset if count is None else count
        if offset < 0 or selected_count <= 0:
            raise FrozenDevelopmentResetError(
                "development reset shard offset must be nonnegative and count positive"
            )
        if offset % batch_size or selected_count % batch_size:
            raise FrozenDevelopmentResetError(
                "development reset shard boundaries must align to the environment batch"
            )
        if offset + selected_count > len(artifact.reset_ids):
            raise FrozenDevelopmentResetError(
                "development reset shard exceeds the frozen reset artifact"
            )
        self.artifact = artifact
        self.batch_size = int(batch_size)
        self.offset = int(offset)
        self.count = int(selected_count)
        self._cursor = self.offset
        self._stop = self.offset + self.count

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        expected_sha256: str,
        batch_size: int,
        offset: int = 0,
        count: int | None = None,
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
            offset=offset,
            count=count,
        )

    @property
    def fingerprint(self) -> str:
        return self.artifact.fingerprint()

    @property
    def consumed(self) -> int:
        return self._cursor - self.offset

    @property
    def complete(self) -> bool:
        return self._cursor == self._stop

    def next_batch(self) -> list[int]:
        end = self._cursor + self.batch_size
        if end > self._stop:
            raise FrozenDevelopmentResetError(
                "frozen development reset schedule is exhausted"
            )
        values = list(self.artifact.reset_ids[self._cursor:end])
        self._cursor = end
        return values
