"""Provider-neutral proposal interface and hardened Claude CLI adapter."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    decimal_text,
    fingerprint,
    parse_decimal,
    parse_timestamp,
    require_identifier,
    require_sha256,
    timestamp_text,
)
from supervisor.context import ContextBundle, SYSTEM_INSTRUCTION
from supervisor.proposals import PROPOSAL_SCHEMA_JSON


MAX_PROVIDER_OUTPUT_BYTES = 1_048_576
MAX_REPAIR_FEEDBACK_BYTES = 16_384
MAX_PROVIDER_TIMEOUT_SECONDS = 600


class ProviderError(ContractError):
    """Raised when a proposal provider cannot return a usable envelope."""


class ProviderTimeout(ProviderError):
    """Raised when the bounded provider call times out."""


@dataclass(frozen=True)
class ProcessResult:
    return_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class ProcessTransport(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        input_text: str,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
    ) -> ProcessResult: ...


class SubprocessTransport:
    """Real transport. Tests replace this and never contact Claude."""

    def run(
        self,
        argv: Sequence[str],
        *,
        input_text: str,
        cwd: Path,
        environment: Mapping[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(argv),
                input=input_text,
                cwd=cwd,
                env=dict(environment),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ProviderTimeout(
                f"provider exceeded {timeout_seconds}-second timeout"
            ) from error
        return ProcessResult(
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_seconds=time.monotonic() - started,
        )


@dataclass(frozen=True)
class ProviderCallResult:
    provider: str
    model: str
    started_at: str
    completed_at: str
    response_hash: str
    proposal_payload: Mapping[str, Any]
    reported_cost_usd: str
    input_tokens: int | None
    output_tokens: int | None

    def __post_init__(self) -> None:
        require_identifier(self.provider, "provider_result.provider")
        require_identifier(self.model, "provider_result.model")
        started = parse_timestamp(self.started_at, "provider_result.started_at")
        completed = parse_timestamp(self.completed_at, "provider_result.completed_at")
        if completed < started:
            raise ContractError("provider result completed before it started")
        require_sha256(self.response_hash, "provider_result.response_hash")
        if not isinstance(self.proposal_payload, Mapping):
            raise ContractError("provider result proposal payload must be an object")
        parse_decimal(self.reported_cost_usd, "provider_result.reported_cost_usd")
        for field, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ContractError(
                    f"provider_result.{field} must be a non-negative integer or null"
                )


class ProposalProvider(Protocol):
    name: str

    def generate(
        self,
        context: ContextBundle,
        *,
        model: str,
        max_budget_usd: str,
        timeout_seconds: int,
        repair_feedback: str | None = None,
    ) -> ProviderCallResult: ...


RUNTIME_ENVIRONMENT = frozenset({"PATH", "LANG", "LC_ALL", "TMPDIR"})
PROVIDER_CREDENTIAL_ENVIRONMENT = {
    "anthropic-direct": frozenset({"ANTHROPIC_API_KEY"}),
}


def sanitized_environment(
    environment: Mapping[str, str], *, backend: str = "anthropic-direct"
) -> dict[str, str]:
    try:
        credential_names = PROVIDER_CREDENTIAL_ENVIRONMENT[backend]
    except KeyError as error:
        raise ContractError(f"unsupported Claude credential backend: {backend}") from error
    allowed = RUNTIME_ENVIRONMENT | credential_names
    return {
        name: value
        for name, value in environment.items()
        if name in allowed and isinstance(value, str)
    }


class ClaudeCliProvider:
    name = "claude-cli"

    def __init__(
        self,
        *,
        executable: Path,
        working_directory: Path,
        transport: ProcessTransport | None = None,
        environment: Mapping[str, str] | None = None,
        credential_backend: str = "anthropic-direct",
        effort: str = "medium",
        clock: Callable[[], Any] | None = None,
    ) -> None:
        if not executable.is_absolute():
            raise ContractError("Claude executable must be an absolute path")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ContractError("Claude executable must exist and be executable")
        if not working_directory.is_dir():
            raise ContractError("Claude working directory must exist")
        if effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ContractError("Claude effort is unsupported")
        from datetime import datetime, timezone

        self.executable = executable
        self.working_directory = working_directory
        self.transport = transport or SubprocessTransport()
        self.credential_backend = credential_backend
        source_environment = os.environ if environment is None else environment
        self.environment = sanitized_environment(
            source_environment, backend=credential_backend
        )
        self.effort = effort
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def build_argv(self, *, model: str, max_budget_usd: str) -> tuple[str, ...]:
        model = require_identifier(model, "provider.model")
        budget = decimal_text(
            parse_decimal(max_budget_usd, "provider.max_budget_usd", allow_zero=False)
        )
        return (
            str(self.executable),
            "--print",
            "--bare",
            "--safe-mode",
            "--disable-slash-commands",
            "--no-chrome",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--json-schema",
            PROPOSAL_SCHEMA_JSON,
            "--no-session-persistence",
            "--tools",
            "",
            "--permission-mode",
            "dontAsk",
            "--max-budget-usd",
            budget,
            "--model",
            model,
            "--effort",
            self.effort,
            "--system-prompt",
            SYSTEM_INSTRUCTION,
        )

    def _prompt(self, context: ContextBundle, repair_feedback: str | None) -> str:
        if repair_feedback is None:
            return context.rendered_prompt
        if len(repair_feedback.encode("utf-8")) > MAX_REPAIR_FEEDBACK_BYTES:
            raise ContractError(
                f"repair feedback may not exceed {MAX_REPAIR_FEEDBACK_BYTES} bytes"
            )
        return (
            context.rendered_prompt
            + "\n<repair_request>\n"
            + repair_feedback
            + "\nCorrect only the listed validation failures. Keep the campaign, "
            "base commit, edit mode, and context unchanged.\n</repair_request>\n"
        )

    @staticmethod
    def _strict_json(text: str, message: str) -> Any:
        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant: {value}")

        try:
            return json.loads(text, parse_constant=reject_constant)
        except (json.JSONDecodeError, ValueError) as error:
            raise ProviderError(message) from error

    @staticmethod
    def _tokens(raw: Mapping[str, Any], name: str) -> int | None:
        usage = raw.get("usage")
        if not isinstance(usage, dict):
            return None
        value = usage.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @staticmethod
    def _proposal_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
        structured = raw.get("structured_output")
        if isinstance(structured, dict):
            return structured
        result = raw.get("result")
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            decoded = ClaudeCliProvider._strict_json(
                result, "Claude result is not structured JSON"
            )
            if isinstance(decoded, dict):
                return decoded
        raise ProviderError("Claude envelope does not contain a proposal object")

    def generate(
        self,
        context: ContextBundle,
        *,
        model: str,
        max_budget_usd: str,
        timeout_seconds: int,
        repair_feedback: str | None = None,
    ) -> ProviderCallResult:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise ContractError("provider timeout must be an integer")
        if not 1 <= timeout_seconds <= MAX_PROVIDER_TIMEOUT_SECONDS:
            raise ContractError(
                "provider timeout must be between 1 and "
                f"{MAX_PROVIDER_TIMEOUT_SECONDS} seconds"
            )
        prompt = self._prompt(context, repair_feedback)
        started = self.clock()
        result = self.transport.run(
            self.build_argv(model=model, max_budget_usd=max_budget_usd),
            input_text=prompt,
            cwd=self.working_directory,
            environment=self.environment,
            timeout_seconds=timeout_seconds,
        )
        completed = self.clock()
        if result.return_code != 0:
            stderr_hash = fingerprint(result.stderr)
            raise ProviderError(
                f"Claude exited with {result.return_code}; stderr hash {stderr_hash}"
            )
        if len(result.stdout.encode("utf-8")) > MAX_PROVIDER_OUTPUT_BYTES:
            raise ProviderError("Claude output exceeds the one-MiB envelope limit")
        raw = self._strict_json(result.stdout, "Claude output envelope is not JSON")
        if not isinstance(raw, dict):
            raise ProviderError("Claude output envelope must be an object")
        if raw.get("is_error") is True:
            raise ProviderError("Claude returned an error envelope")
        cost = decimal_text(
            parse_decimal(raw.get("total_cost_usd", "0"), "Claude reported cost")
        )
        return ProviderCallResult(
            provider=self.name,
            model=require_identifier(model, "provider.model"),
            started_at=timestamp_text(started),
            completed_at=timestamp_text(completed),
            response_hash=fingerprint(raw),
            proposal_payload=self._proposal_payload(raw),
            reported_cost_usd=cost,
            input_tokens=self._tokens(raw, "input_tokens"),
            output_tokens=self._tokens(raw, "output_tokens"),
        )


class FakeProposalProvider:
    """Deterministic queued provider for offline tests and demos."""

    name = "fake-provider"

    def __init__(self, responses: Sequence[ProviderCallResult | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        context: ContextBundle,
        *,
        model: str,
        max_budget_usd: str,
        timeout_seconds: int,
        repair_feedback: str | None = None,
    ) -> ProviderCallResult:
        self.calls.append(
            {
                "context_hash": context.context_hash,
                "model": model,
                "max_budget_usd": max_budget_usd,
                "timeout_seconds": timeout_seconds,
                "repair_feedback": repair_feedback,
            }
        )
        if not self._responses:
            raise ProviderError("fake provider has no queued response")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
