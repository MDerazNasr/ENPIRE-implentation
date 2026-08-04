"""Canonical serialization and validation helpers for supervisor contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any


IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
GIT_COMMIT = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class ContractError(ValueError):
    """Raised when versioned supervisor data violates its contract."""


def canonical_json(value: Any) -> str:
    """Return a deterministic JSON representation and reject NaN/Infinity."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ContractError(f"value is not canonical JSON: {error}") from error


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ContractError(
            f"{field} must be 1-128 characters using letters, numbers, '.', '_', or '-'"
        )
    return value


def require_nonempty_text(value: Any, field: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be non-empty text")
    if len(value) > max_length:
        raise ContractError(f"{field} may not exceed {max_length} characters")
    return value


def require_git_commit(value: Any, field: str) -> str:
    if not isinstance(value, str) or not GIT_COMMIT.fullmatch(value):
        raise ContractError(f"{field} must be a full lowercase 40-character Git commit")
    return value


def require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{field} must be a lowercase SHA-256 digest")
    return value


def require_safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ContractError(f"{field} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value == "." or ".." in path.parts:
        raise ContractError(f"{field} must not be absolute or contain '..'")
    return value


def parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be an ISO-8601 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(f"{field} must use UTC")
    return parsed.astimezone(timezone.utc)


def timestamp_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ContractError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_decimal(
    value: Any,
    field: str,
    *,
    allow_zero: bool = True,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ContractError(f"{field} must be a decimal value")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{field} must be finite")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ContractError(f"{field} must be a decimal value") from error
    if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise ContractError(f"{field} must be finite and {comparator}")
    return parsed


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ContractError("decimal value must be finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def require_exact_keys(
    value: Any,
    field: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    optional = optional or set()
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ContractError(f"{field} is missing required fields: {missing}")
    if unknown:
        raise ContractError(f"{field} contains unknown fields: {unknown}")
    return value
