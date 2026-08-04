"""Decimal-safe campaign budget accounting and preflight enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from supervisor.canonical import ContractError, decimal_text, parse_decimal, require_identifier
from supervisor.contracts import ApprovalEnvelope


class BudgetExceeded(ContractError):
    """Raised before work starts when the approved envelope would be exceeded."""


def _seconds(value: int, field: str, *, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{field} must be an integer")
    if value < 0 or (not allow_zero and value == 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise ContractError(f"{field} must be {comparator}")
    return value


@dataclass(frozen=True)
class BudgetRequest:
    wall_time_seconds: int
    gpu_cost_usd: str
    llm_cost_usd: str

    @classmethod
    def create(
        cls,
        *,
        wall_time_seconds: int,
        gpu_cost_usd: str | int | float | Decimal,
        llm_cost_usd: str | int | float | Decimal,
    ) -> "BudgetRequest":
        return cls(
            wall_time_seconds=_seconds(
                wall_time_seconds, "request.wall_time_seconds", allow_zero=False
            ),
            gpu_cost_usd=decimal_text(
                parse_decimal(gpu_cost_usd, "request.gpu_cost_usd")
            ),
            llm_cost_usd=decimal_text(
                parse_decimal(llm_cost_usd, "request.llm_cost_usd")
            ),
        )


@dataclass(frozen=True)
class BudgetUsage:
    trial_id: str
    wall_time_seconds: int
    gpu_cost_usd: str
    llm_cost_usd: str

    @classmethod
    def create(
        cls,
        *,
        trial_id: str,
        wall_time_seconds: int,
        gpu_cost_usd: str | int | float | Decimal,
        llm_cost_usd: str | int | float | Decimal,
    ) -> "BudgetUsage":
        return cls(
            trial_id=require_identifier(trial_id, "usage.trial_id"),
            wall_time_seconds=_seconds(
                wall_time_seconds, "usage.wall_time_seconds", allow_zero=True
            ),
            gpu_cost_usd=decimal_text(parse_decimal(gpu_cost_usd, "usage.gpu_cost_usd")),
            llm_cost_usd=decimal_text(parse_decimal(llm_cost_usd, "usage.llm_cost_usd")),
        )


@dataclass(frozen=True)
class BudgetSnapshot:
    trials_used: int
    wall_time_seconds_used: int
    gpu_cost_usd_used: str
    llm_cost_usd_used: str
    trials_remaining: int
    wall_time_seconds_remaining: int
    gpu_cost_usd_remaining: str
    llm_cost_usd_remaining: str
    exceeded: bool


class BudgetTracker:
    """Tracks completed usage; scheduling reservations arrive in a later milestone."""

    def __init__(self, approval: ApprovalEnvelope) -> None:
        self.approval = approval
        self._usage: list[BudgetUsage] = []

    @property
    def usage(self) -> tuple[BudgetUsage, ...]:
        return tuple(self._usage)

    def _totals(self) -> tuple[int, int, Decimal, Decimal]:
        return (
            len(self._usage),
            sum(item.wall_time_seconds for item in self._usage),
            sum(
                (parse_decimal(item.gpu_cost_usd, "gpu usage") for item in self._usage),
                Decimal(0),
            ),
            sum(
                (parse_decimal(item.llm_cost_usd, "LLM usage") for item in self._usage),
                Decimal(0),
            ),
        )

    def snapshot(self) -> BudgetSnapshot:
        trials, wall_time, gpu_cost, llm_cost = self._totals()
        cap = self.approval.budget
        gpu_remaining = cap.gpu_cost() - gpu_cost
        llm_remaining = cap.llm_cost() - llm_cost
        exceeded = (
            trials > cap.max_trials
            or wall_time > cap.max_wall_time_seconds
            or gpu_remaining < 0
            or llm_remaining < 0
        )
        return BudgetSnapshot(
            trials_used=trials,
            wall_time_seconds_used=wall_time,
            gpu_cost_usd_used=decimal_text(gpu_cost),
            llm_cost_usd_used=decimal_text(llm_cost),
            trials_remaining=max(0, cap.max_trials - trials),
            wall_time_seconds_remaining=max(0, cap.max_wall_time_seconds - wall_time),
            gpu_cost_usd_remaining=decimal_text(max(Decimal(0), gpu_remaining)),
            llm_cost_usd_remaining=decimal_text(max(Decimal(0), llm_remaining)),
            exceeded=exceeded,
        )

    def assert_can_start(self, request: BudgetRequest) -> None:
        trials, wall_time, gpu_cost, llm_cost = self._totals()
        cap = self.approval.budget
        failures: list[str] = []
        if trials + 1 > cap.max_trials:
            failures.append("trial cap")
        if wall_time + request.wall_time_seconds > cap.max_wall_time_seconds:
            failures.append("wall-time cap")
        if gpu_cost + parse_decimal(request.gpu_cost_usd, "request GPU cost") > cap.gpu_cost():
            failures.append("GPU cost cap")
        if llm_cost + parse_decimal(request.llm_cost_usd, "request LLM cost") > cap.llm_cost():
            failures.append("LLM cost cap")
        if failures:
            raise BudgetExceeded("request exceeds approved " + ", ".join(failures))

    def record(self, usage: BudgetUsage) -> BudgetSnapshot:
        if any(item.trial_id == usage.trial_id for item in self._usage):
            raise ContractError(f"usage already recorded for trial {usage.trial_id!r}")
        self._usage.append(usage)
        return self.snapshot()
