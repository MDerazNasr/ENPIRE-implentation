"""Append-only, hash-chained lifecycle event ledger."""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    parse_timestamp,
    require_exact_keys,
    require_identifier,
    require_nonempty_text,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import (
    SCHEMA_VERSION,
    ZERO_HASH,
    CampaignState,
    StringEnum,
    TrialState,
)
from supervisor.state import CAMPAIGN_STATE_MACHINE, TRIAL_STATE_MACHINE, StateMachine


class LedgerCorruption(ContractError):
    """Raised when the ledger is malformed or its hash/state chain is invalid."""


class EntityType(str, Enum):
    CAMPAIGN = "campaign"
    TRIAL = "trial"


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class LedgerEvent:
    schema_version: int
    campaign_id: str
    entity_type: EntityType
    entity_id: str
    sequence: int
    previous_hash: str
    from_state: str
    to_state: str
    actor: str
    at: str
    reason: str
    metadata: Mapping[str, Any]
    event_hash: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor": self.actor,
            "at": self.at,
            "reason": self.reason,
            "metadata": _thaw_json(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "event_hash": self.event_hash}

    @classmethod
    def create(
        cls,
        *,
        campaign_id: str,
        entity_type: EntityType,
        entity_id: str,
        sequence: int,
        previous_hash: str,
        from_state: StringEnum,
        to_state: StringEnum,
        actor: str,
        at: datetime,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> "LedgerEvent":
        canonical_metadata = json.loads(canonical_json(dict(metadata or {})))
        raw = {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": require_identifier(campaign_id, "event.campaign_id"),
            "entity_type": entity_type.value,
            "entity_id": require_identifier(entity_id, "event.entity_id"),
            "sequence": sequence,
            "previous_hash": require_sha256(previous_hash, "event.previous_hash"),
            "from_state": from_state.value,
            "to_state": to_state.value,
            "actor": require_nonempty_text(actor, "event.actor", max_length=256),
            "at": timestamp_text(at),
            "reason": require_nonempty_text(reason, "event.reason"),
            "metadata": canonical_metadata,
        }
        if isinstance(sequence, bool) or sequence <= 0:
            raise ContractError("event.sequence must be a positive integer")
        return cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=raw["campaign_id"],
            entity_type=entity_type,
            entity_id=raw["entity_id"],
            sequence=sequence,
            previous_hash=previous_hash,
            from_state=from_state.value,
            to_state=to_state.value,
            actor=raw["actor"],
            at=raw["at"],
            reason=raw["reason"],
            metadata=_freeze_json(canonical_metadata),
            event_hash=fingerprint(raw),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "LedgerEvent":
        fields = {
            "schema_version",
            "campaign_id",
            "entity_type",
            "entity_id",
            "sequence",
            "previous_hash",
            "from_state",
            "to_state",
            "actor",
            "at",
            "reason",
            "metadata",
            "event_hash",
        }
        data = require_exact_keys(value, "event", fields)
        if data["schema_version"] != SCHEMA_VERSION:
            raise LedgerCorruption(f"event.schema_version must be {SCHEMA_VERSION}")
        try:
            entity_type = EntityType(data["entity_type"])
        except (TypeError, ValueError) as error:
            raise LedgerCorruption("event.entity_type is unsupported") from error
        sequence = data["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise LedgerCorruption("event.sequence must be a positive integer")
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            raise LedgerCorruption("event.metadata must be an object")
        parse_timestamp(data["at"], "event.at")
        canonical_metadata = json.loads(canonical_json(metadata))
        event = cls(
            schema_version=SCHEMA_VERSION,
            campaign_id=require_identifier(data["campaign_id"], "event.campaign_id"),
            entity_type=entity_type,
            entity_id=require_identifier(data["entity_id"], "event.entity_id"),
            sequence=sequence,
            previous_hash=require_sha256(data["previous_hash"], "event.previous_hash"),
            from_state=require_nonempty_text(data["from_state"], "event.from_state"),
            to_state=require_nonempty_text(data["to_state"], "event.to_state"),
            actor=require_nonempty_text(data["actor"], "event.actor", max_length=256),
            at=data["at"],
            reason=require_nonempty_text(data["reason"], "event.reason"),
            metadata=_freeze_json(canonical_metadata),
            event_hash=require_sha256(data["event_hash"], "event.event_hash"),
        )
        if event.event_hash != fingerprint(event.unsigned_dict()):
            raise LedgerCorruption(f"event {event.sequence} hash does not match its contents")
        return event


@dataclass(frozen=True)
class LedgerSnapshot:
    state: StringEnum
    sequence: int
    head_hash: str
    events: tuple[LedgerEvent, ...]


class EventLedger:
    """Single-writer JSONL ledger with locked, fsynced appends."""

    def __init__(
        self,
        path: Path,
        *,
        campaign_id: str,
        entity_type: EntityType,
        entity_id: str,
    ) -> None:
        self.path = path
        self.campaign_id = require_identifier(campaign_id, "ledger.campaign_id")
        self.entity_type = entity_type
        self.entity_id = require_identifier(entity_id, "ledger.entity_id")

    def _machine(self) -> StateMachine:
        return (
            CAMPAIGN_STATE_MACHINE
            if self.entity_type == EntityType.CAMPAIGN
            else TRIAL_STATE_MACHINE
        )

    def _state(self, value: str) -> StringEnum:
        try:
            if self.entity_type == EntityType.CAMPAIGN:
                return CampaignState(value)
            return TrialState(value)
        except ValueError as error:
            raise LedgerCorruption(
                f"unsupported {self.entity_type.value} state: {value!r}"
            ) from error

    def _parse(self, content: str) -> LedgerSnapshot:
        machine = self._machine()
        if not content:
            return LedgerSnapshot(machine.initial, 0, ZERO_HASH, ())
        if not content.endswith("\n"):
            raise LedgerCorruption("ledger ends with a partial JSONL record")
        lines = content.splitlines()
        if any(not line.strip() for line in lines):
            raise LedgerCorruption("ledger contains a blank record")
        events: list[LedgerEvent] = []
        current = machine.initial
        previous_hash = ZERO_HASH
        for index, line in enumerate(lines, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                raise LedgerCorruption(f"ledger record {index} is invalid JSON") from error
            try:
                event = LedgerEvent.from_dict(raw)
            except LedgerCorruption:
                raise
            except ContractError as error:
                raise LedgerCorruption(f"ledger record {index}: {error}") from error
            if event.campaign_id != self.campaign_id:
                raise LedgerCorruption(f"event {index} campaign ID mismatch")
            if event.entity_type != self.entity_type or event.entity_id != self.entity_id:
                raise LedgerCorruption(f"event {index} entity mismatch")
            if event.sequence != index:
                raise LedgerCorruption(f"event {index} sequence mismatch")
            if event.previous_hash != previous_hash:
                raise LedgerCorruption(f"event {index} previous hash mismatch")
            declared_from = self._state(event.from_state)
            target = self._state(event.to_state)
            if declared_from != current:
                raise LedgerCorruption(
                    f"event {index} declares state {declared_from.value!r}, "
                    f"expected {current.value!r}"
                )
            try:
                current = machine.transition(current, target)
            except ContractError as error:
                raise LedgerCorruption(f"event {index}: {error}") from error
            previous_hash = event.event_hash
            events.append(event)
        return LedgerSnapshot(current, len(events), previous_hash, tuple(events))

    def read(
        self,
        *,
        expected_head_hash: str | None = None,
        expected_sequence: int | None = None,
    ) -> LedgerSnapshot:
        if not self.path.exists():
            snapshot = self._parse("")
        else:
            snapshot = self._parse(self.path.read_text(encoding="utf-8"))
        if expected_head_hash is not None:
            require_sha256(expected_head_hash, "expected_head_hash")
            if snapshot.head_hash != expected_head_hash:
                raise LedgerCorruption("ledger head hash does not match its external anchor")
        if expected_sequence is not None:
            if (
                isinstance(expected_sequence, bool)
                or not isinstance(expected_sequence, int)
                or expected_sequence < 0
            ):
                raise ContractError("expected_sequence must be a non-negative integer")
            if snapshot.sequence != expected_sequence:
                raise LedgerCorruption("ledger sequence does not match its external anchor")
        return snapshot

    def append_transition(
        self,
        target: StringEnum,
        *,
        actor: str,
        reason: str,
        at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerEvent:
        expected_type = CampaignState if self.entity_type == EntityType.CAMPAIGN else TrialState
        if not isinstance(target, expected_type):
            raise ContractError(
                f"target must be a {self.entity_type.value} state, got {target!r}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            snapshot = self._parse(handle.read())
            self._machine().transition(snapshot.state, target)
            event = LedgerEvent.create(
                campaign_id=self.campaign_id,
                entity_type=self.entity_type,
                entity_id=self.entity_id,
                sequence=snapshot.sequence + 1,
                previous_hash=snapshot.head_hash,
                from_state=snapshot.state,
                to_state=target,
                actor=actor,
                at=at or datetime.now(timezone.utc),
                reason=reason,
                metadata=metadata,
            )
            handle.seek(0, os.SEEK_END)
            handle.write(canonical_json(event.to_dict()) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return event
