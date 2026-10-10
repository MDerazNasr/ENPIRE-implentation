"""Dependency-free validation helpers for the staged checkpoint artifact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


STAGE_SCHEMA_VERSION = 1
STAGE_STATUS_COMPLETE = "complete_valid_checkpoint_stage"


class E1CheckpointStageError(ValueError):
    """Raised when staged checkpoint evidence is missing or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_valid_stage_receipt(
    receipt_path: Path,
    checkpoint_path: Path,
    *,
    expected_checkpoint: Mapping[str, object],
) -> dict[str, object]:
    """Load a complete non-authorizing receipt and rehash the staged bytes."""

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise E1CheckpointStageError("staging receipt is missing or invalid") from error
    if not isinstance(receipt, dict):
        raise E1CheckpointStageError("staging receipt must be an object")
    if receipt.get("schema_version") != STAGE_SCHEMA_VERSION:
        raise E1CheckpointStageError("staging receipt schema version mismatch")
    if receipt.get("status") != STAGE_STATUS_COMPLETE:
        raise E1CheckpointStageError("staging receipt is not complete and valid")
    authority = receipt.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise E1CheckpointStageError("staging receipt must be explicitly non-authorizing")
    if receipt.get("checkpoint") != dict(expected_checkpoint):
        raise E1CheckpointStageError("staged checkpoint identity mismatch")
    if receipt.get("checkpoint_path") != str(checkpoint_path):
        raise E1CheckpointStageError("staged checkpoint path mismatch")
    if not checkpoint_path.is_file():
        raise E1CheckpointStageError("staged checkpoint file is missing")
    if checkpoint_path.stat().st_size != expected_checkpoint["size_bytes"]:
        raise E1CheckpointStageError("staged checkpoint size mismatch")
    if sha256_file(checkpoint_path) != expected_checkpoint["sha256"]:
        raise E1CheckpointStageError("staged checkpoint SHA-256 mismatch")
    return receipt


def bounded_error(error: BaseException) -> dict[str, str]:
    """Return a bounded error record without serializing provider objects."""

    message = " ".join(str(error).split())[:500]
    return {"message": message or "no error message", "type": type(error).__name__}
